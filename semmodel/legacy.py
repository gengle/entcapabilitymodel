import collections, json, os, re, sys
from semmodel.model import *
from semmodel.rules import *


def load(path):
    if os.path.isdir(path) or path.endswith((".yaml", ".yml")):
        import semyaml
        return semyaml.load(path, facade())
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
