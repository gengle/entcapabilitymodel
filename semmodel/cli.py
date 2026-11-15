"""sem.py - a dynamic, self-describing semantic model you can navigate and generate from (std-only).

MODEL      tree | schema | validate [--strict] | show <ref> | export | diff <old.sem> <new.sem>
EDIT       add "L1/L2/L3" [k=v ..] [-p] | set <capability> k=v ..
           entity add <Type> <Name> [k=v ..] | entity set <Name> k=v .. | entity list
           link <Entity> <relation> <target> [k=v ..]   (expose / require are shortcuts) | unlink <Entity> <target>
META       type add <Name> [Parent] | type prop <Type> "key: type [= default]"
           relation add <name> <from|from> <to|to> [inverse=x] [transitive] [no_cycles]
NAVIGATE   locate <id> | neighbors <ref> | closure <ref> <relation> | path <A> <B> | who <ref> | gaps | coverage | impact <Entity>
GENERATE   gen <site|sql|typeql|jsonschema|openapi|mermaid|csv|all> <outdir> [--level N] | yaml <outdir>
YAML       ids [--dry-run]   give every capability and entity without an `id` a new UUID (written into its file)
           version [major|minor|patch|<x.y.z>]   show the model version, bump it, or set it (model.yaml)
<ref> is an entity name, a capability path / unique capability name, or an `id`.
Model: $SEM_MODEL, else ./model/ (YAML, see semyaml.py) if present, else ./model.sem. A YAML model is read-only
here: EDIT and META commands refuse it, edit its files (or use server.py). `yaml <outdir>` converts any model.
"""
import collections, json, os, sys
import gen, semyaml
from semmodel.model import *
from semmodel.rules import *
from semmodel.legacy import *


def yaml_root():
    root = MODEL if os.path.isdir(MODEL) else os.path.dirname(os.path.abspath(MODEL))
    if not os.path.isfile(os.path.join(root, "model.yaml")):
        sys.exit("this command needs a YAML model (a folder with model.yaml)")
    return root


def cmd_version(rest):
    root = yaml_root()
    old = semyaml.read_version(root)
    if not rest:
        return print(old or "no version set")
    try:
        new = semyaml.bump(old, rest[0])
    except ValueError as x:
        sys.exit(str(x))
    semyaml.write_version(root, new)
    print(f"version {old or '(none)'} -> {new}")


def cmd_ids(rest):
    dry = "--dry-run" in rest
    done = semyaml.assign_ids(yaml_root(), dry_run=dry)
    for f, label, uid in done:
        print(f"{'would add' if dry else 'added'} id {uid}  {label}  ({f})")
    print(f"{len(done)} id(s) {'to add' if dry else 'added'}" if done else "every capability and entity already has an id")


def cmd_locate(m, text):
    hits = locate(m, text)
    if not hits:
        sys.exit(f"no capability or entity has an id matching '{text}' (give the full id or at least 4 hex digits)")
    if len(hits) > 1:
        print(f"{len(hits)} objects have ids starting with '{text}'; give more digits:")
    for x in hits:
        line = id_line(m, x)
        print(describe(x))
        print(f"  {x.src}{f':{line}' if line else ''}   id {x.uid}")


def disp(i):
    return i.split(":", 1)[1]


def attr_text(attrs, brackets="[]"):
    """'k=v, k=v' wrapped in the given brackets, or '' when there are none."""
    return brackets[0] + ", ".join(f"{k}={v}" for k, v in attrs.items()) + brackets[1] if attrs else ""


def by_label(adj, x, brackets, sep=""):
    """Neighbours of x grouped by relation label: {label: ['name  [attrs]', ...]}."""
    by = collections.defaultdict(list)
    for lab, other, attrs in adj[nid(x)]:
        by[lab].append(disp(other) + (sep + attr_text(attrs, brackets) if attrs else ""))
    return by


def print_by(by):
    for lab, items in by.items():
        print(f"  {lab}: " + "; ".join(items))


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


def print_docs(props, ind):
    """Descriptions of props and their enum values, indented under the line that lists them."""
    for p in props.values():
        if p.description:
            print(f"{ind}{p.name}: {p.description}")
        for v in p.enum or []:
            if v in p.docs:
                print(f"{ind}  {p.name}={v}: {p.docs[v]}")


def cmd_schema(m):
    print(f"capability levels: " + " > ".join(f"L{k} {v}" for k, v in sorted(m.levels.items())))
    print(f"capability properties: " + ", ".join(p.line() for p in m.props.values()))
    print_docs(m.props, "    ")
    print("\nentity types")
    for t in m.etypes.values():
        print(f"  {t.name}" + (f" : {t.parent}" if t.parent else "") + "   own props: " + (", ".join(p.line() for p in t.props.values()) or "-"))
        if t.description:
            print(f"      {t.description}")
        if t.parent:
            print("      effective: " + ", ".join(m.eprop_defs(t.name)))
        print_docs(t.props, "      ")
    print("\nrelation types")
    for r in m.rtypes.values():
        flags = [x for x in (("transitive" if r.transitive else ""), ("no_cycles" if r.no_cycles else ""),
                             (f"min_level {r.min_level}" if r.min_level else ""),
                             (f"satisfied_by {','.join(r.satisfied_by)}" if r.satisfied_by else ""),
                             (f"conflicts_with {','.join(r.conflicts)}" if r.conflicts else "")) if x]
        print(f"  {r.name}: {'|'.join(r.frm)} -> {'|'.join(r.to)}   inverse {r.inverse or '-'}   attrs: "
              + (", ".join(p.line() for p in r.attrs.values()) or "-") + (f"   [{'; '.join(flags)}]" if flags else ""))
        if r.description:
            print(f"      {r.description}")
        print_docs(r.attrs, "      ")


def cmd_show(m, x):
    adj = adjacency(m)
    if isinstance(x, Node):
        print(f"{x.path()}   ({m.lvname(x)})" + (f"   id {x.uid}" if x.uid else ""))
        for p in m.props.values():
            v, origin = m.resolve(x, p)
            print(f"  {p.name:<20} {str(v):<14} {origin}")
        i = cid(x)
    else:
        print(f"{x.name}   ({x.type}, is-a {' > '.join(m.chain(x.type))})" + (f"   id {x.uid}" if x.uid else ""))
        for k, v in eprops(m, x).items():
            print(f"  {k:<20} {v}")
        i = eid(x)
    for lab, other, attrs in adj[i]:
        print(f"  {lab:<12} {disp(other)}{' ' if attrs else ''}{attr_text(attrs)}")


def cmd_neighbors(m, x):
    print(disp(nid(x)))
    print_by(by_label(adjacency(m), x, "[]", "  "))


def cmd_closure(m, x, rel):
    start, found = nid(x), False
    for other, hops in reach(adjacency(m), start, rel):
        print("  " * (hops - 1) + "-> " + disp(other) if hops > 1 else disp(other))
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
    print(f"{x.path() if isinstance(x, Node) else x.name}")
    print_by(by_label(adjacency(m), x, "()", " "))
    if isinstance(x, Node):
        verbs = provide_verbs(m)
        below = [e for e in providers(m, x) if not directly_provides(e, x, verbs)]
        if below:
            print("  also provided via sub-capabilities by: " + ", ".join(e.name for e in below))


def cmd_gaps(m):
    g = unmet(m)
    if not g:
        return print("no unmet requirements")
    print(f"{len(g)} unmet requirement(s)")
    for e, r, rt in g:
        print(f"  - {e.name} {rt.name} {r['target'].path()} ({dependency(r)}): nothing {'/'.join(rt.satisfied_by)} it")


def cmd_coverage(m):
    verbs, min_lv = provide_verbs(m), provide_min_level(m)
    nodes = [n for n in m.all_nodes() if n.level() >= min_lv]
    white = 0
    print(f"coverage at L{min_lv}+ via {', '.join(sorted(verbs))} (a capability counts providers beneath it too)")
    for n in nodes:
        direct = [e for e in m.entities if directly_provides(e, n, verbs)]
        rolled = providers(m, n)
        status = "WHITE SPACE" if not rolled else ("overlap" if len(direct) >= 2 else "")
        white += not rolled
        ind = n.level() - min_lv
        print(f"  {'  ' * ind}L{n.level()} {n.name:<{34 - 2 * ind}} providers {len(rolled)}  {status}")
    print(f"{len(nodes) - white}/{len(nodes)} covered, {white} white space")


def cmd_impact(m, e):
    i = impact(m, e)
    hard = [u for u in i["unmet"] if dependency(u[1]) == "hard"]
    print(f"retirement impact of {e.name} ({e.type})" + ("  [already retired: it no longer counts as a provider]" if retired(e) else ""))
    if not (i["white"] or i["unmet"] or i["dependents"] or i["referenced"]):
        print("  safe to retire: nothing relies on it")
    else:
        print(f"  {len(i['white'])} capability(ies) left without a provider, {len(hard)} hard / "
              f"{len(i['unmet']) - len(hard)} soft requirement(s) unmet, "
              f"{sum(len(a) for _, a in i['dependents'])} dependent(s), {len(i['referenced'])} reference(s)")
    for n, others in i["provides"]:
        print(f"  provides {n.path()}: " + (f"also provided by {', '.join(x.name for x in others)}" if others else "sole provider"))
    for n in i["white"]:
        print(f"  white space: {n.path()}")
    for x, r, rt in i["unmet"]:
        print(f"  unmet: {x.name} {rt.name} {r['target'].path()} ({dependency(r)})")
    for rt, out in i["dependents"]:
        print(f"  {rt.inverse} (via {rt.name}): " + ", ".join(f"{disp(x)}{'' if d == 1 else f' ({d} hops)'}" for x, d in out))
    for x, p in i["referenced"]:
        print(f"  {p.name} of {disp(nid(x))}")


def flatten(m):
    out = {"capability props": {"props": [p.line() for p in m.props.values()]}}

    def docs(scope, desc, props):
        if desc:
            out[f"description {scope}"] = {"text": desc}
        for p in props.values():
            if p.description or p.docs:
                out[f"description {scope}.{p.name}"] = {**({"text": p.description} if p.description else {}), **p.docs}
    docs("capability", None, m.props)
    for t in m.etypes.values():
        docs(f"entity_type {t.name}", t.description, t.props)
    for r in m.rtypes.values():
        docs(f"relation_type {r.name}", r.description, r.attrs)
    for t in m.etypes.values():
        out[f"entity_type {t.name}"] = {"parent": t.parent, "props": [p.line() for p in t.props.values()]}
    for r in m.rtypes.values():
        out[f"relation_type {r.name}"] = {"from": r.frm, "to": r.to, "inverse": r.inverse, "attrs": [p.line() for p in r.attrs.values()]}
    if m.version is not None:
        out["model"] = {"version": m.version}
    for n in m.all_nodes():
        out[f"capability {n.path()}"] = {**({"id": n.uid} if n.uid else {}), **n.local}
    for e in m.entities:
        out[f"entity {e.name}"] = {"type": e.type, **({"id": e.uid} if e.uid else {}), **e.local}
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


def cmd_validate(m, rest):
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


def cmd_export(m):
    print(json.dumps({"version": m.version, "capabilities": [{"id": n.uid, "path": n.path(), "level": n.level(),
                                        "properties": {p.name: m.resolve(n, p)[0] for p in m.props.values()}} for n in m.all_nodes()],
                      "entities": [{"id": e.uid, "name": e.name, "type": e.type, "properties": eprops(m, e)} for e in m.entities],
                      "relations": [{"source": e.name, "relation": r["verb"], "target": target_text(r), **r["attrs"]}
                                    for e in m.entities for r in e.rels if r["target"]]}, indent=2))


def cmd_yaml(m, outdir):
    for p in semyaml.dump(m, outdir):
        print("wrote", p)


def cmd_gen(m, rest):
    lv = int(rest[rest.index("--level") + 1]) if "--level" in rest else 3
    gen.run(m, rest[0], rest[1], lv)


# Commands that run before the model is loaded: name -> (min args, max args or None, handler(rest)).
EARLY = {
    "diff": (2, 2, lambda rest: cmd_diff(*rest)),
    "ids": (0, None, cmd_ids),
    "version": (0, None, cmd_version),
}

# Commands on the loaded model: name -> (min args, max args or None, handler(m, rest)).
# A call whose argument count does not fit prints the usage text, as does a handler raising Usage.
COMMANDS = {
    "tree": (0, None, lambda m, r: cmd_tree(m)),
    "schema": (0, None, lambda m, r: cmd_schema(m)),
    "show": (1, None, lambda m, r: cmd_show(m, ref(m, r[0]))),
    "neighbors": (1, None, lambda m, r: cmd_neighbors(m, ref(m, r[0]))),
    "closure": (2, 2, lambda m, r: cmd_closure(m, ref(m, r[0]), r[1])),
    "path": (2, 2, lambda m, r: cmd_path(m, ref(m, r[0]), ref(m, r[1]))),
    "who": (1, None, lambda m, r: cmd_who(m, ref(m, r[0]))),
    "gaps": (0, None, lambda m, r: cmd_gaps(m)),
    "coverage": (0, None, lambda m, r: cmd_coverage(m)),
    "locate": (1, None, lambda m, r: cmd_locate(m, r[0])),
    "impact": (1, None, lambda m, r: cmd_impact(m, need(m, r[0], "ent"))),
    "validate": (0, None, cmd_validate),
    "export": (0, None, lambda m, r: cmd_export(m)),
    "add": (1, None, edit_add),
    "set": (2, None, edit_set),
    "entity": (1, None, edit_entity),
    "link": (3, None, edit_link),
    "expose": (2, None, edit_shortcut("expose")),
    "require": (2, None, edit_shortcut("require")),
    "unlink": (2, None, edit_unlink),
    "type": (2, None, edit_type),
    "relation": (4, None, edit_relation),
    "yaml": (1, None, lambda m, r: cmd_yaml(m, r[0])),
    "gen": (2, None, cmd_gen),
}


def fits(spec, rest):
    lo, hi, _ = spec
    return len(rest) >= lo and (hi is None or len(rest) <= hi)


def main():
    a = sys.argv[1:]
    if not a:
        return print(__doc__)
    cmd, rest = a[0], a[1:]
    if cmd in EARLY and fits(EARLY[cmd], rest):
        return EARLY[cmd][2](rest)
    m = load(MODEL)
    if cmd in COMMANDS and fits(COMMANDS[cmd], rest):
        try:
            return COMMANDS[cmd][2](m, rest)
        except Usage:
            pass
    print(__doc__)
