import collections, json, os, re, sys
from semmodel.model import *


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
    for src, p, t in refs(m):
        out.append((nid(src), p.name, eid(t), {}, f"{p.name}_of"))
    return out


def refs(m):
    """(capability or entity, prop, target entity) for every ref prop value set locally that resolves."""
    out = []
    for n in m.all_nodes():
        for k, v in n.local.items():
            t = m.ref(m.props.get(k), v)
            if t:
                out.append((n, m.props[k], t))
    for e in m.entities:
        defs = m.eprop_defs(e.type) if e.type in m.etypes else {}
        for k, v in e.local.items():
            t = m.ref(defs.get(k), v)
            if t:
                out.append((e, defs[k], t))
    return out


def adjacency(m):
    adj = collections.defaultdict(list)
    for s, lab, d, attrs, inv in edges(m):
        adj[s].append((lab, d, attrs))
        adj[d].append((inv, s, attrs))
    return adj


def unresolved(m, where, p, v):
    return f"{where}: {p.name} '{v}' is not a known {' or '.join(p.targets)} (match by {m.ref_keys(p)})"


def validate(m):
    errs, warns = list(getattr(m, "load_errors", [])), []
    limit = m.depth_limit()
    for t in m.etypes.values():
        if t.parent and t.parent not in m.etypes:
            errs.append(f"entity_type {t.name}: unknown parent '{t.parent}'")
        elif len(m.chain(t.name)) != len({*m.chain(t.name)}) or (t.parent and t.name in m.chain(t.parent)):
            errs.append(f"entity_type {t.name}: inheritance cycle")
    known = set(m.etypes) | {"Capability", "*"}
    scopes = [(m.root_name, m.props)] + [(f"entity_type {t.name}", t.props) for t in m.etypes.values()]         + [(f"relation {r.name}", r.attrs) for r in m.rtypes.values()]
    for where, props in scopes:
        for p in props.values():
            for x in p.targets:
                if x not in m.etypes and x != "*":
                    errs.append(f"{where}: {p.name}: ref to unknown entity type '{x}'")
    for t in m.etypes.values():  # a key prop identifies one entity, so its values must be unique
        for k, p in t.props.items():
            if p.key:
                vals = [str(e.local[k]).lower() for e in m.entities if k in e.local and m.conforms(e.type, [t.name])]
                for d in sorted({v for v in vals if vals.count(v) > 1}):
                    errs.append(f"entity_type {t.name}: key '{k}' value '{d}' is used by more than one entity")
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
            elif m.props[k].type == "ref" and m.ref(m.props[k], n.local[k]) is None:
                warns.append(unresolved(m, where, m.props[k], n.local[k]))
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
                if defs[k].type == "ref" and m.ref(defs[k], v) is None:
                    warns.append(unresolved(m, w, defs[k], v))
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
    if getattr(m, "yaml", False):
        validate_ids(m, errs, warns)
    for e, r, rt in unmet(m):
        sev = r["attrs"].get("dependency", "hard")
        msg = f"{e.name} {rt.name} {r['target'].path()} ({sev}) but no active entity {'/'.join(rt.satisfied_by)} it"
        (errs if m.rules.get("unmet_requirements") == "error" and sev == "hard" else warns).append(msg)
    return errs, warns


def validate_ids(m, errs, warns):
    """Model version and universal ids: every capability and entity should carry a unique UUID `id`."""
    if m.version is None:
        warns.append(f"{m.entry}: no model version (add `version: 1.0.0`, or run: python sem.py version 1.0.0)")
    elif not SEMVER_RE.match(m.version):
        errs.append(f"{m.entry}: version '{m.version}' is not MAJOR.MINOR.PATCH")
    owners, missing = {}, collections.Counter()
    for x, label in [(n, n.path()) for n in m.all_nodes()] + [(e, f"entity {e.name}") for e in m.entities]:
        if not x.uid:
            missing[getattr(x, "src", None) or "?"] += 1
        elif not UUID_RE.match(x.uid):
            errs.append(f"{label}: id '{x.uid}' is not a UUID")
        elif x.uid.lower() in owners:
            errs.append(f"{label}: id {x.uid} is already used by {owners[x.uid.lower()]}")
        else:
            owners[x.uid.lower()] = label
    for f, k in missing.items():
        warns.append(f"{f}: {k} capabilit{'y' if k == 1 else 'ies'}/entit{'y' if k == 1 else 'ies'} without an id "
                     "(run: python sem.py ids)")


def norm_uid(s):
    return re.sub(r"[^0-9a-f]", "", str(s).lower())


def locate(m, text):
    """Capabilities and entities whose id is `text`, or starts with it (at least 4 hex digits; case, hyphens and
    braces are ignored, so the short "d54cfb4b" the viewer shows works). Exact matches win over prefix matches."""
    t = str(text).strip().lower().strip("{}")
    q = norm_uid(t)
    if len(q) < 4 or not re.fullmatch(r"[0-9a-f-]+", t):
        return []
    objs = [x for x in [*m.all_nodes(), *m.entities] if getattr(x, "uid", None)]
    return [x for x in objs if norm_uid(x.uid) == q] or [x for x in objs if norm_uid(x.uid).startswith(q)]


def id_line(m, x):
    """1-based line of x's `id:` in its source file (YAML models), or None."""
    root, src = getattr(m, "src_root", None), getattr(x, "src", None)
    if not (root and src and x.uid):
        return None
    try:
        with open(os.path.join(root, src), encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if x.uid.lower() in line.lower():
                    return i
    except OSError:
        pass
    return None


def describe(m, x):
    return (f"capability L{x.level()} {x.path()}" if isinstance(x, Node) else f"entity ({x.type}) {x.name}")


def ref(m, text):
    e, (n, err) = m.entity(text), m.find_cap(text)
    if e and n:
        sys.exit(f"'{text}' is both an entity and a capability; use the full capability path")
    if e or n:
        return e or n
    hits = locate(m, text)  # a unique id prefix also works
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        sys.exit(f"'{text}' is the start of {len(hits)} ids; give more digits")
    sys.exit(f"no entity or capability '{text}'" if "ambiguous" not in (err or "") else err)


def need(m, text, kind):
    x = ref(m, text)
    if kind == "ent" and not isinstance(x, Entity):
        sys.exit(f"'{text}' is a capability, not an entity")
    if kind == "cap" and not isinstance(x, Node):
        sys.exit(f"'{text}' is an entity, not a capability")
    return x


def provide_min_level(m):
    lv = [rt.min_level for rt in m.rtypes.values() if rt.name in provide_verbs(m) and rt.min_level]
    return min(lv) if lv else 1


def impact(m, e):
    """What retiring (or removing) entity e would change, as plain data shared by the CLI and the server.

    provides   [(capability, [other providers])] for each capability e directly provides (a satisfied_by verb)
    white      capabilities at or above the coverage level that would be left with no provider at all
    unmet      [(entity, rel, rtype)] requirements met today that would become unmet
    dependents [(relation, [(entity id, hops)])] entities reaching e through the inverse of a transitive relation
    referenced [(capability or entity, prop)] ref props that name e (e.g. what it owns or heads)
    """
    verbs, min_lv = provide_verbs(m), provide_min_level(m)
    gone = {e.name}
    provides = [(r["target"], [x for x in providers(m, r["target"], gone)])
                for r in e.rels if r["verb"] in verbs and isinstance(r["target"], Node)]
    white = [n for n in m.all_nodes() if n.level() >= min_lv and providers(m, n) and not providers(m, n, gone)]
    before = {(x.name, r["target"].path(), r["verb"]) for x, r, _ in unmet(m)}
    new = [(x, r, rt) for x, r, rt in unmet(m, gone) if (x.name, r["target"].path(), r["verb"]) not in before]
    adj, dependents = adjacency(m), []
    for rt in m.rtypes.values():
        if rt.transitive and rt.inverse:
            seen, queue, out = {eid(e)}, collections.deque([(eid(e), 0)]), []
            while queue:
                cur, d = queue.popleft()
                for lab, other, _ in adj[cur]:
                    if lab == rt.inverse and other not in seen:
                        seen.add(other)
                        queue.append((other, d + 1))
                        out.append((other, d + 1))
            if out:
                dependents.append((rt, out))
    referenced = [(x, p) for x, p, t in refs(m) if t is e]
    return {"provides": provides, "white": white, "unmet": new, "dependents": dependents, "referenced": referenced}
