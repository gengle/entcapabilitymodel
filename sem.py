#!/usr/bin/env python3
"""sem.py - a dynamic, self-describing semantic model you can navigate and generate from (std-only).

MODEL      tree | schema | validate [--strict] | show <ref> | export | diff <old.sem> <new.sem>
EDIT       add "L1/L2/L3" [k=v ..] [-p] | set <capability> k=v ..
           entity add <Type> <Name> [k=v ..] | entity set <Name> k=v .. | entity list
           link <Entity> <relation> <target> [k=v ..]   (expose / require are shortcuts) | unlink <Entity> <target>
META       type add <Name> [Parent] | type prop <Type> "key: type [= default]"
           relation add <name> <from|from> <to|to> [inverse=x] [transitive] [no_cycles]
NAVIGATE   neighbors <ref> | closure <ref> <relation> | path <A> <B> | who <ref> | gaps | coverage | impact <Entity>
GENERATE   gen <site|sql|typeql|jsonschema|openapi|mermaid|csv|all> <outdir> [--level N] | yaml <outdir>
<ref> is an entity name, or a capability path / unique capability name.
Model: $SEM_MODEL, else ./model/ (YAML, see semyaml.py) if present, else ./model.sem. A YAML model is read-only
here: EDIT and META commands refuse it, edit its files (or use server.py). `yaml <outdir>` converts any model.
"""
import collections, json, os, re, sys

MODEL = os.environ.get("SEM_MODEL") or ("model" if os.path.isdir("model") else "model.sem")
PROP_RE = re.compile(r'^(\w+):\s*(\w+)(?:\(([^)]*)\))?(?:\s*=\s*("[^"]*"|\S+))?((?:\s+(?:inherit|required))*)\s*$')
REL_RE = re.compile(r'^(\w+)\s+(.+?)(?:\s*\[([^\]]*)\])?\s*$')


def unq(v):
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v


def fmt(v):
    return f'"{v}"' if re.search(r'[^\w.\-]', v) else v


class Prop:
    def __init__(self, name, typ, enum, default, inherit=False, required=False):
        self.name, self.type, self.enum, self.default = name, typ, enum, default
        self.inherit, self.required = inherit, required

    def line(self):
        t = self.type + (f"({','.join(self.enum)})" if self.enum else "")
        return (f"{self.name}: {t}" + (f" = {fmt(self.default)}" if self.default is not None else "")
                + (" inherit" if self.inherit else "") + (" required" if self.required else ""))

    def coerce(self, raw):
        if self.type == "int":
            try:
                return int(raw)
            except ValueError:
                raise ValueError(f"{self.name}: '{raw}' is not an int")
        if self.type == "enum" and raw not in self.enum:
            raise ValueError(f"{self.name}: '{raw}' not in {{{', '.join(self.enum)}}}")
        return raw


def parse_prop(rest, ln=0):
    g = PROP_RE.match(rest.strip())
    if not g:
        raise ValueError(f"line {ln}: bad property '{rest}'")
    name, typ, enum, default, flags = g.groups()
    return Prop(name, typ, enum.split(",") if enum else None, unq(default) if default else None,
                "inherit" in flags, "required" in flags)


class Node:
    def __init__(self, name, parent=None):
        self.name, self.parent, self.children, self.local = name, parent, [], {}

    def path(self):
        parts, n = [], self
        while n.parent is not None:
            parts.append(n.name)
            n = n.parent
        return "/".join(reversed(parts))

    def level(self):
        return self.path().count("/") + 1

    def descendants(self):
        for c in self.children:
            yield c
            yield from c.descendants()


class Entity:
    def __init__(self, etype, name):
        self.type, self.name, self.local, self.rels = etype, name, {}, []


class EType:
    def __init__(self, name, parent=None):
        self.name, self.parent, self.props = name, parent, {}


class RType:
    def __init__(self, name):
        self.name, self.frm, self.to, self.attrs, self.inverse = name, [], [], {}, None
        self.min_level, self.satisfied_by, self.conflicts = None, [], []
        self.transitive = self.no_cycles = False


class Model:
    def __init__(self):
        self.root_name, self.levels, self.props, self.rules = "Capability", {}, {}, {}
        self.etypes, self.rtypes, self.entities, self.top = {}, {}, [], Node("")

    # ---- capability tree
    def all_nodes(self):
        out, stack = [], list(reversed(self.top.children))
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(reversed(n.children))
        return out

    def find(self, path):
        n = self.top
        for part in [p for p in path.split("/") if p]:
            n = next((c for c in n.children if c.name.lower() == part.lower()), None)
            if n is None:
                return None
        return n if n is not self.top else None

    def find_cap(self, text):
        n = self.find(text)
        if n:
            return n, None
        if "/" not in text:
            hits = [x for x in self.all_nodes() if x.name.lower() == text.lower()]
            if len(hits) == 1:
                return hits[0], None
            if len(hits) > 1:
                return None, f"'{text}' is ambiguous: " + ", ".join(h.path() for h in hits)
        return None, f"no such capability '{text}'"

    def depth_limit(self):
        return len(self.levels) if self.levels else 99

    def lvname(self, n):
        return f"L{n.level()} {self.levels.get(n.level(), '')}".strip()

    def resolve(self, node, p):
        if p.name in node.local:
            return p.coerce(node.local[p.name]), "local"
        if p.inherit:
            a = node.parent
            while a is not None and a.parent is not None:
                if p.name in a.local:
                    return p.coerce(a.local[p.name]), f"inherited from {a.path()}"
                a = a.parent
        if p.default is not None:
            return p.coerce(p.default), "root default"
        return None, "unset"

    # ---- entities and types
    def entity(self, name):
        return next((e for e in self.entities if e.name.lower() == name.lower()), None)

    def chain(self, t):
        out = []
        while t and t in self.etypes and t not in out:
            out.append(t)
            t = self.etypes[t].parent
        return out

    def eprop_defs(self, t):
        d = {}
        for name in reversed(self.chain(t)):
            d.update(self.etypes[name].props)
        return d

    def conforms(self, t, names):
        return "*" in names or any(x in names for x in self.chain(t))

    def link(self):
        for e in self.entities:
            for r in e.rels:
                rt = self.rtypes.get(r["verb"])
                if rt is None:
                    r["target"], r["err"] = None, f"unknown relation '{r['verb']}' (defined: {', '.join(self.rtypes) or 'none'})"
                else:
                    r["target"], r["err"] = self.resolve_target(rt, r["text"])

    def resolve_target(self, rt, text):
        err = None
        if "Capability" in rt.to or "*" in rt.to:
            n, err = self.find_cap(text)
            if n:
                return n, None
        e = self.entity(text)
        if e:
            return e, None
        return None, err or f"no such {'/'.join(rt.to)} '{text}'"


def load(path):
    if os.path.isdir(path) or path.endswith((".yaml", ".yml")):
        import semyaml
        return semyaml.load(path, sys.modules[__name__])
    return load_sem(path)


def load_sem(path):
    m, stack, cur, section, et, rt, ent = Model(), [], None, None, None, None, None
    for ln, raw in enumerate(open(path), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        kw, _, rest = raw.strip().partition(" ")
        rest = rest.strip()
        if kw == "root":
            m.root_name, section = rest, "root"
        elif kw == "level" and section == "root":
            k, _, v = rest.partition(" ")
            m.levels[int(k)] = v.strip()
        elif kw == "prop" and section == "root":
            p = parse_prop(rest, ln)
            m.props[p.name] = p
        elif kw == "prop" and section == "etype":
            p = parse_prop(rest, ln)
            et.props[p.name] = p
        elif kw == "rule" and section == "root":
            k, _, v = rest.partition(" ")
            m.rules[k] = v.strip()
        elif kw == "entity_type":
            g = re.match(r'^(\w+)(?:\s*:\s*(\w+))?$', rest)
            if not g:
                raise ValueError(f"line {ln}: bad entity_type '{rest}'")
            section, et = "etype", EType(g.group(1), g.group(2))
            m.etypes[et.name] = et
        elif kw == "relation":
            section, rt = "rel", RType(rest)
            m.rtypes[rt.name] = rt
        elif section == "rel" and kw not in ("capability", "entity"):
            if kw == "from":
                rt.frm = rest.split("|")
            elif kw == "to":
                rt.to = rest.split("|")
            elif kw == "attr":
                p = parse_prop(rest, ln)
                rt.attrs[p.name] = p
            elif kw == "inverse":
                rt.inverse = rest
            elif kw == "min_level":
                rt.min_level = int(rest)
            elif kw == "satisfied_by":
                rt.satisfied_by = rest.split()
            elif kw == "conflicts_with":
                rt.conflicts = rest.split()
            elif kw == "transitive":
                rt.transitive = True
            elif kw == "no_cycles":
                rt.no_cycles = True
            else:
                raise ValueError(f"line {ln}: unknown relation setting '{kw}'")
        elif kw == "entity":
            section = "entity"
            t, _, name = rest.partition(" ")
            ent = Entity(t, name.strip())
            m.entities.append(ent)
        elif kw == "capability":
            section = "cap"
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else m.top
            cur = Node(rest, parent)
            parent.children.append(cur)
            stack.append((indent, cur))
        elif kw == "set" and section in ("cap", "entity"):
            k, _, v = rest.partition("=")
            (cur if section == "cap" else ent).local[k.strip()] = unq(v)
        elif section == "entity":
            g = REL_RE.match(raw.strip())
            attrs = {}
            for tok in re.split(r'[,\s]+', (g.group(3) or "").strip()):
                if tok:
                    k, _, v = tok.partition("=")
                    attrs[k] = v
            ent.rels.append({"verb": kw, "text": g.group(2), "attrs": attrs, "target": None, "err": None})
        else:
            raise ValueError(f"line {ln}: cannot parse '{raw.strip()}'")
    m.link()
    return m


def target_text(r):
    t = r["target"]
    return t.path() if isinstance(t, Node) else (t.name if t is not None else r["text"])


def save(m, path):
    out = [f"root {m.root_name}"] + [f"  level {k} {v}" for k, v in sorted(m.levels.items())]
    out += ["  prop " + p.line() for p in m.props.values()]
    out += [f"  rule {k}" + (f" {v}" if v else "") for k, v in m.rules.items()] + [""]
    for t in m.etypes.values():
        out.append(f"entity_type {t.name}" + (f" : {t.parent}" if t.parent else ""))
        out += ["  prop " + p.line() for p in t.props.values()]
    out.append("")
    for r in m.rtypes.values():
        out += [f"relation {r.name}", f"  from {'|'.join(r.frm)}", f"  to {'|'.join(r.to)}"]
        out += ["  attr " + p.line() for p in r.attrs.values()]
        if r.inverse:
            out.append(f"  inverse {r.inverse}")
        if r.min_level:
            out.append(f"  min_level {r.min_level}")
        if r.satisfied_by:
            out.append("  satisfied_by " + " ".join(r.satisfied_by))
        if r.conflicts:
            out.append("  conflicts_with " + " ".join(r.conflicts))
        out += (["  transitive"] if r.transitive else []) + (["  no_cycles"] if r.no_cycles else [])
    out.append("")

    def emit(n, d):
        out.append("  " * d + f"capability {n.name}")
        for k in m.props:
            if k in n.local:
                out.append("  " * (d + 1) + f"set {k} = {fmt(n.local[k])}")
        for c in n.children:
            emit(c, d + 1)
    for c in m.top.children:
        emit(c, 0)
    out.append("")
    for e in m.entities:
        out.append(f"entity {e.type} {e.name}")
        for k in m.eprop_defs(e.type):
            if k in e.local:
                out.append(f"  set {k} = {fmt(e.local[k])}")
        for k in e.local:
            if k not in m.eprop_defs(e.type):
                out.append(f"  set {k} = {fmt(e.local[k])}")
        for r in e.rels:
            rt = m.rtypes.get(r["verb"])
            kv = []
            for a, v in r["attrs"].items():
                if rt and a in rt.attrs and rt.attrs[a].default == v:
                    continue
                kv.append(f"{a}={v}")
            out.append(f"  {r['verb']} {target_text(r)}" + (f" [{', '.join(kv)}]" if kv else ""))
    open(path, "w").write("\n".join(out) + "\n")


# ------------------------------------------------------------------ semantics
def retired(e):
    return e.local.get("lifecycle") == "retire"


def eprops(m, e):
    return {k: e.local.get(k, p.default) for k, p in m.eprop_defs(e.type).items()}


def provide_verbs(m):
    return {v for rt in m.rtypes.values() for v in rt.satisfied_by}


def providers(m, node, excluded=(), verbs=None):
    verbs = verbs or provide_verbs(m)
    want = {node, *node.descendants()}
    return [e for e in m.entities if e.name not in excluded and not retired(e)
            and any(r["verb"] in verbs and r["target"] in want for r in e.rels)]


def unmet(m, excluded=()):
    out = []
    for e in m.entities:
        if e.name in excluded or retired(e):
            continue
        for r in e.rels:
            rt = m.rtypes.get(r["verb"])
            if rt and rt.satisfied_by and isinstance(r["target"], Node):
                if not providers(m, r["target"], set(excluded) | {e.name}, set(rt.satisfied_by)):
                    out.append((e, r, rt))
    return out


def cid(n):
    return "cap:" + n.path()


def eid(e):
    return "ent:" + e.name


def nid(x):
    return cid(x) if isinstance(x, Node) else eid(x)


def edges(m):
    """(src, label, dst, attrs, inverse_label) for hierarchy and every relation instance."""
    out = []
    for n in m.all_nodes():
        if n.parent.parent is not None:
            out.append((cid(n.parent), "parent_of", cid(n), {}, "child_of"))
    for e in m.entities:
        for r in e.rels:
            rt = m.rtypes.get(r["verb"])
            if r["target"] is not None and rt:
                out.append((eid(e), rt.name, nid(r["target"]), r["attrs"], rt.inverse or f"~{rt.name}"))
    return out


def adjacency(m):
    adj = collections.defaultdict(list)
    for s, lab, d, attrs, inv in edges(m):
        adj[s].append((lab, d, attrs))
        adj[d].append((inv, s, attrs))
    return adj


def validate(m):
    errs, warns = list(getattr(m, "load_errors", [])), []
    limit = m.depth_limit()
    for t in m.etypes.values():
        if t.parent and t.parent not in m.etypes:
            errs.append(f"entity_type {t.name}: unknown parent '{t.parent}'")
        elif len(m.chain(t.name)) != len({*m.chain(t.name)}) or (t.parent and t.name in m.chain(t.parent)):
            errs.append(f"entity_type {t.name}: inheritance cycle")
    known = set(m.etypes) | {"Capability", "*"}
    invs = {}
    for rt in m.rtypes.values():
        for side, names in (("from", rt.frm), ("to", rt.to)):
            if not names:
                errs.append(f"relation {rt.name}: missing '{side}'")
            for x in names:
                if x not in known:
                    errs.append(f"relation {rt.name}: unknown type '{x}' in {side}")
        for x in rt.satisfied_by + rt.conflicts:
            if x not in m.rtypes:
                errs.append(f"relation {rt.name}: refers to unknown relation '{x}'")
        if rt.inverse:
            if rt.inverse in m.rtypes or rt.inverse in invs:
                errs.append(f"relation {rt.name}: inverse '{rt.inverse}' clashes with another name")
            invs[rt.inverse] = 1
    for parent in [m.top] + m.all_nodes():
        names = [c.name.lower() for c in parent.children]
        for d in {x for x in names if names.count(x) > 1}:
            errs.append(f"{parent.path() or '(root)'}: duplicate child '{d}'")
    for n in m.all_nodes():
        where = n.path()
        if n.level() > limit:
            errs.append(f"{where}: level {n.level()} is deeper than the model's {limit} levels")
        for k in n.local:
            if k not in m.props:
                errs.append(f"{where}: unknown property '{k}' (not defined on root {m.root_name})")
        for p in m.props.values():
            try:
                v, _ = m.resolve(n, p)
            except ValueError as x:
                errs.append(f"{where}: {x}")
                continue
            if p.required and v is None:
                errs.append(f"{where}: required '{p.name}' is unset (set it here or on an ancestor)")
        if "no_active_under_retired" in m.rules and "lifecycle" in m.props:
            try:
                lp, a = m.props["lifecycle"], n.parent
                mine = m.resolve(n, lp)[0]
                while a is not None and a.parent is not None:
                    if mine == "active" and m.resolve(a, lp)[0] == "retire":
                        errs.append(f"{where}: active under retired ancestor {a.path()}")
                        break
                    a = a.parent
            except ValueError:
                pass
    names = [e.name.lower() for e in m.entities]
    for d in {x for x in names if names.count(x) > 1}:
        errs.append(f"duplicate entity '{d}'")
    for e in m.entities:
        w = f"entity {e.name}"
        if e.type not in m.etypes:
            errs.append(f"{w}: unknown entity type '{e.type}' (defined: {', '.join(m.etypes) or 'none'})")
            defs = {}
        else:
            defs = m.eprop_defs(e.type)
        for k, v in e.local.items():
            if k not in defs:
                errs.append(f"{w}: unknown property '{k}' for type {e.type}")
            else:
                try:
                    defs[k].coerce(v)
                except ValueError as x:
                    errs.append(f"{w}: {x}")
        for p in defs.values():
            if p.required and e.local.get(p.name, p.default) is None:
                errs.append(f"{w}: required '{p.name}' is unset")
        seen = set()
        for r in e.rels:
            rt = m.rtypes.get(r["verb"])
            if r["err"]:
                errs.append(f"{w}: {r['verb']} {r['text']}: {r['err']}")
                continue
            t, tname = r["target"], target_text(r)
            if e.type in m.etypes and not m.conforms(e.type, rt.frm):
                errs.append(f"{w}: {e.type} cannot be the source of '{rt.name}' (allowed: {'|'.join(rt.frm)})")
            if isinstance(t, Entity):
                if t is e:
                    errs.append(f"{w}: {rt.name} to itself")
                if not m.conforms(t.type, rt.to):
                    errs.append(f"{w}: {rt.name} {tname} is a {t.type}; relation allows {'|'.join(rt.to)}")
            elif "Capability" not in rt.to and "*" not in rt.to:
                errs.append(f"{w}: {rt.name} targets {'|'.join(rt.to)}, not a capability")
            for k, v in r["attrs"].items():
                if k not in rt.attrs:
                    errs.append(f"{w}: {rt.name} {tname}: unknown attribute '{k}' (allowed: {', '.join(rt.attrs) or 'none'})")
                else:
                    try:
                        rt.attrs[k].coerce(v)
                    except ValueError as x:
                        errs.append(f"{w}: {rt.name} {tname}: {x}")
            if isinstance(t, Node) and rt.min_level and t.level() < rt.min_level:
                errs.append(f"{w}: {rt.name} {tname} is L{t.level()}; this relation is only allowed at L{rt.min_level} or deeper")
            if (rt.name, id(t)) in seen:
                errs.append(f"{w}: duplicate {rt.name} {tname}")
            seen.add((rt.name, id(t)))
            for c in rt.conflicts:
                if (c, id(t)) in seen:
                    errs.append(f"{w}: both {rt.name} and {c} {tname}")
            for c, tid in list(seen):
                if c in m.rtypes and rt.name in m.rtypes[c].conflicts and tid == id(t):
                    errs.append(f"{w}: both {c} and {rt.name} {tname}")
    for rt in m.rtypes.values():
        if rt.no_cycles:
            adj = collections.defaultdict(list)
            for e in m.entities:
                for r in e.rels:
                    if r["verb"] == rt.name and isinstance(r["target"], Entity):
                        adj[e.name].append(r["target"].name)
            state = {}

            def dfs(u, trail):
                state[u] = 1
                for v in adj[u]:
                    if state.get(v) == 1:
                        errs.append(f"{rt.name} cycle: " + " -> ".join(trail + [u, v]))
                    elif v not in state:
                        dfs(v, trail + [u])
                state[u] = 2
            for u in list(adj):
                if u not in state:
                    dfs(u, [])
    for e, r, rt in unmet(m):
        sev = r["attrs"].get("dependency", "hard")
        msg = f"{e.name} {rt.name} {r['target'].path()} ({sev}) but no active entity {'/'.join(rt.satisfied_by)} it"
        (errs if m.rules.get("unmet_requirements") == "error" and sev == "hard" else warns).append(msg)
    return errs, warns


# ------------------------------------------------------------------ commands
def ref(m, text):
    e, (n, err) = m.entity(text), m.find_cap(text)
    if e and n:
        sys.exit(f"'{text}' is both an entity and a capability; use the full capability path")
    if e or n:
        return e or n
    sys.exit(f"no entity or capability '{text}'" if "ambiguous" not in (err or "") else err)


def need(m, text, kind):
    x = ref(m, text)
    if kind == "ent" and not isinstance(x, Entity):
        sys.exit(f"'{text}' is a capability, not an entity")
    if kind == "cap" and not isinstance(x, Node):
        sys.exit(f"'{text}' is an entity, not a capability")
    return x


def disp(i):
    return i.split(":", 1)[1]


def cmd_tree(m):
    adj = adjacency(m)

    def go(n, d):
        rel = collections.Counter(lab for lab, _, _ in adj[cid(n)] if lab not in ("parent_of", "child_of"))
        vals = [str(m.resolve(n, m.props[k])[0]) for k in ("owner", "criticality", "maturity") if k in m.props]
        print("  " * d + f"L{n.level()} {n.name}   [{' | '.join(vals)}]" + "".join(f"  {k} {v}" for k, v in rel.items()))
        for c in n.children:
            go(c, d + 1)
    for c in m.top.children:
        go(c, 0)


def cmd_schema(m):
    print(f"capability levels: " + " > ".join(f"L{k} {v}" for k, v in sorted(m.levels.items())))
    print(f"capability properties: " + ", ".join(p.line() for p in m.props.values()))
    print("\nentity types")
    for t in m.etypes.values():
        print(f"  {t.name}" + (f" : {t.parent}" if t.parent else "") + "   own props: " + (", ".join(p.line() for p in t.props.values()) or "-"))
        if t.parent:
            print("      effective: " + ", ".join(m.eprop_defs(t.name)))
    print("\nrelation types")
    for r in m.rtypes.values():
        flags = [x for x in (("transitive" if r.transitive else ""), ("no_cycles" if r.no_cycles else ""),
                             (f"min_level {r.min_level}" if r.min_level else ""),
                             (f"satisfied_by {','.join(r.satisfied_by)}" if r.satisfied_by else ""),
                             (f"conflicts_with {','.join(r.conflicts)}" if r.conflicts else "")) if x]
        print(f"  {r.name}: {'|'.join(r.frm)} -> {'|'.join(r.to)}   inverse {r.inverse or '-'}   attrs: "
              + (", ".join(p.line() for p in r.attrs.values()) or "-") + (f"   [{'; '.join(flags)}]" if flags else ""))


def cmd_show(m, x):
    adj = adjacency(m)
    if isinstance(x, Node):
        print(f"{x.path()}   ({m.lvname(x)})")
        for p in m.props.values():
            v, origin = m.resolve(x, p)
            print(f"  {p.name:<20} {str(v):<14} {origin}")
        i = cid(x)
    else:
        print(f"{x.name}   ({x.type}, is-a {' > '.join(m.chain(x.type))})")
        for k, v in eprops(m, x).items():
            print(f"  {k:<20} {v}")
        i = eid(x)
    for lab, other, attrs in adj[i]:
        a = " [" + ", ".join(f"{k}={v}" for k, v in attrs.items()) + "]" if attrs else ""
        print(f"  {lab:<12} {disp(other)}{a}")


def cmd_neighbors(m, x):
    adj = adjacency(m)
    i = nid(x)
    by = collections.defaultdict(list)
    for lab, other, attrs in adj[i]:
        by[lab].append(disp(other) + ("  [" + ", ".join(f"{k}={v}" for k, v in attrs.items()) + "]" if attrs else ""))
    print(disp(i))
    for lab, items in by.items():
        print(f"  {lab}: " + "; ".join(items))


def cmd_closure(m, x, rel):
    adj = adjacency(m)
    start = nid(x)
    seen, queue = {start}, collections.deque([(start, 0)])
    found = False
    while queue:
        cur, d = queue.popleft()
        for lab, other, _ in adj[cur]:
            if lab == rel and other not in seen:
                seen.add(other)
                queue.append((other, d + 1))
                print("  " * d + f"{'-> ' if d else ''}{disp(other)}" if d else f"{disp(other)}")
                found = True
    if not found:
        print(f"nothing reachable from {disp(start)} via '{rel}'")


def cmd_path(m, a, b):
    adj = adjacency(m)
    s, t = nid(a), nid(b)
    prev, queue = {s: None}, collections.deque([s])
    while queue:
        cur = queue.popleft()
        if cur == t:
            break
        for lab, other, _ in adj[cur]:
            if other not in prev:
                prev[other] = (cur, lab)
                queue.append(other)
    if t not in prev:
        return print("no path")
    hops, cur = [], t
    while prev[cur]:
        p, lab = prev[cur]
        hops.append((p, lab, cur))
        cur = p
    print(disp(s))
    for p, lab, c in reversed(hops):
        print(f"  --{lab}--> {disp(c)}")


def cmd_who(m, x):
    adj = adjacency(m)
    print(f"{x.path() if isinstance(x, Node) else x.name}")
    by = collections.defaultdict(list)
    for lab, other, attrs in adj[nid(x)]:
        by[lab].append(disp(other) + (" (" + ", ".join(f"{k}={v}" for k, v in attrs.items()) + ")" if attrs else ""))
    for lab, items in by.items():
        print(f"  {lab}: " + "; ".join(items))
    if isinstance(x, Node):
        below = [e for e in providers(m, x) if all(r["target"] is not x for r in e.rels if r["verb"] in provide_verbs(m))]
        if below:
            print("  also provided via sub-capabilities by: " + ", ".join(e.name for e in below))


def cmd_gaps(m):
    g = unmet(m)
    if not g:
        return print("no unmet requirements")
    print(f"{len(g)} unmet requirement(s)")
    for e, r, rt in g:
        print(f"  - {e.name} {rt.name} {r['target'].path()} ({r['attrs'].get('dependency', 'hard')}): nothing {'/'.join(rt.satisfied_by)} it")


def provide_min_level(m):
    lv = [rt.min_level for rt in m.rtypes.values() if rt.name in provide_verbs(m) and rt.min_level]
    return min(lv) if lv else 1


def cmd_coverage(m):
    verbs, min_lv = provide_verbs(m), provide_min_level(m)
    nodes = [n for n in m.all_nodes() if n.level() >= min_lv]
    white = 0
    print(f"coverage at L{min_lv}+ via {', '.join(sorted(verbs))} (a capability counts providers beneath it too)")
    for n in nodes:
        direct = [e for e in m.entities if any(r["verb"] in verbs and r["target"] is n for r in e.rels)]
        rolled = providers(m, n)
        status = "WHITE SPACE" if not rolled else ("overlap" if len(direct) >= 2 else "")
        white += not rolled
        ind = n.level() - min_lv
        print(f"  {'  ' * ind}L{n.level()} {n.name:<{34 - 2 * ind}} providers {len(rolled)}  {status}")
    print(f"{len(nodes) - white}/{len(nodes)} covered, {white} white space")


def cmd_impact(m, e):
    before = {(x.name, r["target"].path(), r["verb"]) for x, r, _ in unmet(m)}
    after = unmet(m, {e.name})
    lost = [n for n in m.all_nodes() if providers(m, n) and not providers(m, n, {e.name})]
    print(f"impact of retiring/removing {e.name} ({e.type})")
    print("  capabilities left with no provider: " + (", ".join(n.path() for n in lost) or "none"))
    new = [(x, r, rt) for x, r, rt in after if (x.name, r["target"].path(), r["verb"]) not in before]
    print("  requirements that become unmet:" + ("" if new else " none"))
    for x, r, rt in new:
        print(f"    - {x.name} {rt.name} {r['target'].path()} ({r['attrs'].get('dependency', 'hard')})")
    adj = adjacency(m)
    for rt in m.rtypes.values():
        if rt.transitive and rt.inverse:
            seen, queue, out = {eid(e)}, collections.deque([(eid(e), 0)]), []
            while queue:
                cur, d = queue.popleft()
                for lab, other, _ in adj[cur]:
                    if lab == rt.inverse and other not in seen:
                        seen.add(other)
                        queue.append((other, d + 1))
                        out.append((disp(other), d + 1))
            if out:
                print(f"  affected via {rt.name} (transitive): " + ", ".join(f"{n}{'' if d == 1 else f' (via {d} hops)'}" for n, d in out))
    if any(r["verb"] in {x for rt in m.rtypes.values() for x in rt.satisfied_by} is False for r in e.rels):
        pass


def flatten(m):
    out = {}
    for t in m.etypes.values():
        out[f"entity_type {t.name}"] = {"parent": t.parent, "props": [p.line() for p in t.props.values()]}
    for r in m.rtypes.values():
        out[f"relation_type {r.name}"] = {"from": r.frm, "to": r.to, "inverse": r.inverse, "attrs": [p.line() for p in r.attrs.values()]}
    for n in m.all_nodes():
        out[f"capability {n.path()}"] = dict(n.local)
    for e in m.entities:
        out[f"entity {e.name}"] = {"type": e.type, **e.local}
        for r in e.rels:
            out[f"relation {e.name} {r['verb']} {target_text(r)}"] = dict(r["attrs"])
    return out


def cmd_diff(a, b):
    fa, fb = flatten(load(a)), flatten(load(b))
    for k in sorted(set(fb) - set(fa)):
        print(f"+ {k}")
    for k in sorted(set(fa) - set(fb)):
        print(f"- {k}")
    for k in sorted(set(fa) & set(fb)):
        if fa[k] != fb[k]:
            print(f"~ {k}: {fa[k]} -> {fb[k]}")
    if fa == fb:
        print("no differences")


def kv(args):
    out = {}
    for a in args:
        if "=" not in a:
            sys.exit(f"expected key=value, got '{a}'")
        k, _, v = a.partition("=")
        out[k.strip()] = unq(v)
    return out


def commit(m, what, strict=False):
    if getattr(m, "yaml", False):
        sys.exit(f"REJECTED: {MODEL} is a YAML model; edit its files (or use server.py) instead")
    m.link()
    errs, warns = validate(m)
    if errs or (strict and warns):
        print("REJECTED, model unchanged:")
        for x in errs + (warns if strict else []):
            print("  -", x)
        sys.exit(1)
    save(m, MODEL)
    print(what)
    for w in warns:
        print("  warning:", w)


def add_link(m, ename, verb, target, attrs):
    e = need(m, ename, "ent")
    e.rels.append({"verb": verb, "text": target, "attrs": attrs, "target": None, "err": None})
    commit(m, f"{e.name} {verb} {target}")


def main():
    a = sys.argv[1:]
    if not a:
        return print(__doc__)
    cmd, rest = a[0], a[1:]
    if cmd == "diff" and len(rest) == 2:
        return cmd_diff(*rest)
    m = load(MODEL)
    if cmd == "tree":
        cmd_tree(m)
    elif cmd == "schema":
        cmd_schema(m)
    elif cmd == "show" and rest:
        cmd_show(m, ref(m, rest[0]))
    elif cmd == "neighbors" and rest:
        cmd_neighbors(m, ref(m, rest[0]))
    elif cmd == "closure" and len(rest) == 2:
        cmd_closure(m, ref(m, rest[0]), rest[1])
    elif cmd == "path" and len(rest) == 2:
        cmd_path(m, ref(m, rest[0]), ref(m, rest[1]))
    elif cmd == "who" and rest:
        cmd_who(m, ref(m, rest[0]))
    elif cmd == "gaps":
        cmd_gaps(m)
    elif cmd == "coverage":
        cmd_coverage(m)
    elif cmd == "impact" and rest:
        cmd_impact(m, need(m, rest[0], "ent"))
    elif cmd == "validate":
        errs, warns = validate(m)
        for x in errs:
            print("-", x)
        for w in warns:
            print("warning:", w)
        strict = "--strict" in rest
        if not errs and not (warns and strict):
            print(f"ok: {len(m.all_nodes())} capabilities, {len(m.entities)} entities, "
                  f"{sum(len(e.rels) for e in m.entities)} relations ({len(warns)} warning(s))")
        sys.exit(1 if errs or (warns and strict) else 0)
    elif cmd == "export":
        print(json.dumps({"capabilities": [{"path": n.path(), "level": n.level(),
                                            "properties": {p.name: m.resolve(n, p)[0] for p in m.props.values()}} for n in m.all_nodes()],
                          "entities": [{"name": e.name, "type": e.type, "properties": eprops(m, e)} for e in m.entities],
                          "relations": [{"source": e.name, "relation": r["verb"], "target": target_text(r), **r["attrs"]}
                                        for e in m.entities for r in e.rels if r["target"]]}, indent=2))
    elif cmd == "add" and rest:
        mk = "-p" in rest
        rest = [x for x in rest if x != "-p"]
        parts = [p.strip() for p in rest[0].split("/") if p.strip()]
        n = m.top
        for i, part in enumerate(parts):
            nxt = next((c for c in n.children if c.name.lower() == part.lower()), None)
            last = i == len(parts) - 1
            if nxt is None:
                if not last and not mk:
                    sys.exit(f"parent '{'/'.join(parts[:i + 1])}' does not exist (use -p to create it)")
                nxt = Node(part, n)
                n.children.append(nxt)
            elif last:
                sys.exit(f"'{rest[0]}' already exists (use `set` to change it)")
            n = nxt
        n.local.update(kv(rest[1:]))
        commit(m, f"added {n.path()}  ({m.lvname(n)})")
    elif cmd == "set" and len(rest) >= 2:
        n = need(m, rest[0], "cap")
        n.local.update(kv(rest[1:]))
        commit(m, f"updated {n.path()}")
    elif cmd == "entity" and rest:
        sub, args = rest[0], rest[1:]
        if sub == "list":
            for e in m.entities:
                print(f"{e.type:<12} {e.name:<20} {len(e.rels)} relation(s)")
        elif sub == "add" and len(args) >= 2:
            if m.entity(args[1]):
                sys.exit(f"entity '{args[1]}' already exists")
            e = Entity(args[0], args[1])
            e.local.update(kv(args[2:]))
            m.entities.append(e)
            commit(m, f"added {e.type} {e.name}")
        elif sub == "set" and len(args) >= 2:
            e = need(m, args[0], "ent")
            e.local.update(kv(args[1:]))
            commit(m, f"updated {e.name}")
        else:
            print(__doc__)
    elif cmd == "link" and len(rest) >= 3:
        add_link(m, rest[0], rest[1], rest[2], kv(rest[3:]))
    elif cmd in ("expose", "require") and len(rest) >= 2:
        add_link(m, rest[0], cmd + "s", rest[1], kv(rest[2:]))
    elif cmd == "unlink" and len(rest) >= 2:
        e = need(m, rest[0], "ent")
        before = len(e.rels)
        e.rels = [r for r in e.rels if target_text(r).lower() != rest[1].lower() and (r["target"] is None or nid(r["target"]) != nid(ref(m, rest[1])))]
        if len(e.rels) == before:
            sys.exit(f"{e.name} has no relation to '{rest[1]}'")
        commit(m, f"removed {before - len(e.rels)} relation(s) from {e.name}")
    elif cmd == "type" and len(rest) >= 2:
        if rest[0] == "add":
            if rest[1] in m.etypes:
                sys.exit(f"type '{rest[1]}' already exists")
            m.etypes[rest[1]] = EType(rest[1], rest[2] if len(rest) > 2 else None)
            commit(m, f"added entity type {rest[1]}" + (f" : {rest[2]}" if len(rest) > 2 else ""))
        elif rest[0] == "prop" and len(rest) == 3:
            t = m.etypes.get(rest[1]) or sys.exit(f"no such type '{rest[1]}'")
            p = parse_prop(rest[2])
            t.props[p.name] = p
            commit(m, f"{t.name} now has property {p.name}")
        else:
            print(__doc__)
    elif cmd == "relation" and rest and rest[0] == "add" and len(rest) >= 4:
        if rest[1] in m.rtypes:
            sys.exit(f"relation '{rest[1]}' already exists")
        rt = RType(rest[1])
        rt.frm, rt.to = rest[2].split("|"), rest[3].split("|")
        for x in rest[4:]:
            if x == "transitive":
                rt.transitive = True
            elif x == "no_cycles":
                rt.no_cycles = True
            elif x.startswith("inverse="):
                rt.inverse = x.split("=", 1)[1]
            else:
                sys.exit(f"unknown option '{x}'")
        m.rtypes[rt.name] = rt
        commit(m, f"added relation {rt.name}: {'|'.join(rt.frm)} -> {'|'.join(rt.to)}")
    elif cmd == "yaml" and rest:
        import semyaml
        for p in semyaml.dump(m, sys.modules[__name__], rest[0]):
            print("wrote", p)
    elif cmd == "gen" and len(rest) >= 2:
        import gen
        lv = int(rest[rest.index("--level") + 1]) if "--level" in rest else 3
        gen.run(sys.modules[__name__], m, rest[0], rest[1], lv)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
