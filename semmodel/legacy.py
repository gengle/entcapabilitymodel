import os, re, sys
import semyaml
from semmodel.model import *
from semmodel.rules import *


def load(path):
    if os.path.isdir(path) or path.endswith((".yaml", ".yml")):
        return semyaml.load(path)
    return load_sem(path)


class SemParser:
    """State of a line-by-line .sem parse; one method per statement kind."""

    def __init__(self):
        self.m, self.stack, self.cur = Model(), [], None
        self.section = self.et = self.rt = self.ent = None

    def root(self, rest, ln):
        self.m.root_name, self.section = rest, "root"

    def level(self, rest, ln):
        k, _, v = rest.partition(" ")
        self.m.levels[int(k)] = v.strip()

    def root_prop(self, rest, ln):
        p = parse_prop(rest, ln)
        self.m.props[p.name] = p

    def etype_prop(self, rest, ln):
        p = parse_prop(rest, ln)
        self.et.props[p.name] = p

    def rule(self, rest, ln):
        k, _, v = rest.partition(" ")
        self.m.rules[k] = v.strip()

    def entity_type(self, rest, ln):
        g = re.match(r'^(\w+)(?:\s*:\s*(\w+))?$', rest)
        if not g:
            raise ValueError(f"line {ln}: bad entity_type '{rest}'")
        self.section, self.et = "etype", EType(g.group(1), g.group(2))
        self.m.etypes[self.et.name] = self.et

    def relation(self, rest, ln):
        self.section, self.rt = "rel", RType(rest)
        self.m.rtypes[self.rt.name] = self.rt

    def rel_setting(self, kw, rest, ln):
        rt = self.rt
        if kw == "attr":
            p = parse_prop(rest, ln)
            rt.attrs[p.name] = p
            return
        setters = {"from": ("frm", lambda: rest.split("|")), "to": ("to", lambda: rest.split("|")),
                   "inverse": ("inverse", lambda: rest), "min_level": ("min_level", lambda: int(rest)),
                   "satisfied_by": ("satisfied_by", rest.split), "conflicts_with": ("conflicts", rest.split),
                   "transitive": ("transitive", lambda: True), "no_cycles": ("no_cycles", lambda: True)}
        if kw not in setters:
            raise ValueError(f"line {ln}: unknown relation setting '{kw}'")
        attr, val = setters[kw]
        setattr(rt, attr, val())

    def entity(self, rest, ln):
        self.section = "entity"
        t, _, name = rest.partition(" ")
        self.ent = Entity(t, name.strip())
        self.m.entities.append(self.ent)

    def capability(self, rest, indent):
        self.section = "cap"
        while self.stack and self.stack[-1][0] >= indent:
            self.stack.pop()
        parent = self.stack[-1][1] if self.stack else self.m.top
        self.cur = Node(rest, parent)
        parent.children.append(self.cur)
        self.stack.append((indent, self.cur))

    def set_value(self, rest):
        k, _, v = rest.partition("=")
        (self.cur if self.section == "cap" else self.ent).local[k.strip()] = unq(v)

    def entity_relation(self, kw, text):
        g = REL_RE.match(text)
        attrs = {}
        for tok in re.split(r'[,\s]+', (g.group(3) or "").strip()):
            if tok:
                k, _, v = tok.partition("=")
                attrs[k] = v
        self.ent.rels.append({"verb": kw, "text": g.group(2), "attrs": attrs, "target": None, "err": None})

    def line(self, ln, raw):
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw.strip()
        kw, _, rest = text.partition(" ")
        rest, sec = rest.strip(), self.section
        if kw == "root":
            self.root(rest, ln)
        elif kw == "level" and sec == "root":
            self.level(rest, ln)
        elif kw == "prop" and sec == "root":
            self.root_prop(rest, ln)
        elif kw == "prop" and sec == "etype":
            self.etype_prop(rest, ln)
        elif kw == "rule" and sec == "root":
            self.rule(rest, ln)
        elif kw == "entity_type":
            self.entity_type(rest, ln)
        elif kw == "relation":
            self.relation(rest, ln)
        elif sec == "rel" and kw not in ("capability", "entity"):
            self.rel_setting(kw, rest, ln)
        elif kw == "entity":
            self.entity(rest, ln)
        elif kw == "capability":
            self.capability(rest, indent)
        elif kw == "set" and sec in ("cap", "entity"):
            self.set_value(rest)
        elif sec == "entity":
            self.entity_relation(kw, text)
        else:
            raise ValueError(f"line {ln}: cannot parse '{text}'")


def load_sem(path):
    p = SemParser()
    for ln, raw in enumerate(open(path), 1):
        if raw.strip() and not raw.lstrip().startswith("#"):
            p.line(ln, raw)
    p.m.link()
    return p.m


def _sets(ind, keys, local):
    return [f"{ind}set {k} = {fmt(local[k])}" for k in keys if k in local]


def _props(ind, props):
    return [f"{ind}prop " + p.line() for p in props.values()]


def save(m, path):
    out = [f"root {m.root_name}"] + [f"  level {k} {v}" for k, v in sorted(m.levels.items())]
    out += _props("  ", m.props)
    out += [f"  rule {k}" + (f" {v}" if v else "") for k, v in m.rules.items()] + [""]
    for t in m.etypes.values():
        out.append(f"entity_type {t.name}" + (f" : {t.parent}" if t.parent else ""))
        out += _props("  ", t.props)
    out.append("")
    for r in m.rtypes.values():
        out += [f"relation {r.name}", f"  from {'|'.join(r.frm)}", f"  to {'|'.join(r.to)}"]
        out += ["  attr " + p.line() for p in r.attrs.values()]
        for key, val in (("inverse", r.inverse), ("min_level", r.min_level),
                         ("satisfied_by", " ".join(r.satisfied_by)), ("conflicts_with", " ".join(r.conflicts))):
            if val:
                out.append(f"  {key} {val}")
        out += (["  transitive"] if r.transitive else []) + (["  no_cycles"] if r.no_cycles else [])
    out.append("")

    def emit(n, d):
        out.append("  " * d + f"capability {n.name}")
        out.extend(_sets("  " * (d + 1), m.props, n.local))
        for c in n.children:
            emit(c, d + 1)
    for c in m.top.children:
        emit(c, 0)
    out.append("")
    for e in m.entities:
        out.append(f"entity {e.type} {e.name}")
        defs = m.eprop_defs(e.type)
        out.extend(_sets("  ", [*defs, *(k for k in e.local if k not in defs)], e.local))
        for r in e.rels:
            rt = m.rtypes.get(r["verb"])
            kv = [f"{a}={v}" for a, v in r["attrs"].items() if not (rt and a in rt.attrs and rt.attrs[a].default == v)]
            out.append(f"  {r['verb']} {target_text(r)}" + (f" [{', '.join(kv)}]" if kv else ""))
    open(path, "w").write("\n".join(out) + "\n")


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


class Usage(Exception):
    """Raised by an edit handler whose arguments do not fit; main() answers with the usage text."""


def edit_add(m, rest):
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


def edit_set(m, rest):
    n = need(m, rest[0], "cap")
    n.local.update(kv(rest[1:]))
    commit(m, f"updated {n.path()}")


def edit_entity(m, rest):
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
        raise Usage


def edit_link(m, rest):
    add_link(m, rest[0], rest[1], rest[2], kv(rest[3:]))


def edit_shortcut(verb):
    """`expose` / `require`: link <Entity> exposes|requires <target>."""
    return lambda m, rest: add_link(m, rest[0], verb + "s", rest[1], kv(rest[2:]))


def edit_unlink(m, rest):
    e = need(m, rest[0], "ent")
    before = len(e.rels)
    e.rels = [r for r in e.rels if target_text(r).lower() != rest[1].lower() and (r["target"] is None or nid(r["target"]) != nid(ref(m, rest[1])))]
    if len(e.rels) == before:
        sys.exit(f"{e.name} has no relation to '{rest[1]}'")
    commit(m, f"removed {before - len(e.rels)} relation(s) from {e.name}")


def edit_type(m, rest):
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
        raise Usage


def edit_relation(m, rest):
    if rest[0] != "add":
        raise Usage
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
