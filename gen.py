"""Generators: every output is derived from the model, so adding a type/relation/entity changes them all."""
import csv, html, json, os, re


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def w(outdir, name, text):
    p = os.path.join(outdir, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)
    return p


def pyname(s):
    return re.sub(r"\W+", "_", s).lower()


def cap_rels(m):
    return [rt for rt in m.rtypes.values() if "Capability" in rt.to or "*" in rt.to]


def js_type(p):
    if p.type == "int":
        return {"type": "integer"}
    if p.type == "enum":
        return {"type": "string", "enum": p.enum}
    return {"type": "string"}


# ---------------------------------------------------------------- site
CSS = """body{font:15px/1.5 system-ui,sans-serif;margin:0;color:#1d1d1f;background:#fafaf8}
nav{background:#1f2a37;padding:10px 24px}nav a{color:#e5e7eb;margin-right:18px;text-decoration:none}
main{max-width:980px;margin:24px auto;padding:0 24px}h1{font-size:24px}h2{font-size:17px;margin-top:28px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e3e3df;padding:6px 10px;text-align:left}
th{font-weight:600;color:#555}.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;background:#e8eef7}
.warn{background:#fff3d6}.bad{background:#fde2e0}.ok{background:#e1f3e4}ul.t{list-style:none;padding-left:18px}ul.t.root{padding-left:0}
.muted{color:#777;font-size:13px}input{padding:6px 10px;width:100%;box-sizing:border-box;margin:8px 0}"""


def gen_site(S, m, out, level):
    E = html.escape
    adj = S.adjacency(m)

    def href(i, depth):
        pre = "../" * depth
        kind, name = i.split(":", 1)
        return f"{pre}{'cap' if kind == 'cap' else 'ent'}/{slug(name)}.html"

    def page(title, body, depth):
        pre = "../" * depth
        return (f"<!doctype html><meta charset=utf-8><title>{E(title)}</title><style>{CSS}</style>"
                f"<nav><a href='{pre}index.html'>Capability map</a><a href='{pre}entities.html'>Entities</a>"
                f"<a href='{pre}coverage.html'>Coverage</a><a href='{pre}gaps.html'>Gaps</a><a href='{pre}schema.html'>Schema</a></nav>"
                f"<main><h1>{E(title)}</h1>{body}</main>")

    def links(i, depth, skip=("parent_of", "child_of")):
        by = {}
        for lab, other, attrs in adj[i]:
            if lab not in skip:
                by.setdefault(lab, []).append((other, attrs))
        rows = ""
        for lab, items in by.items():
            cells = ", ".join(f"<a href='{href(o, depth)}'>{E(o.split(':', 1)[1].split('/')[-1])}</a>"
                              + (f" <span class=muted>{E(', '.join(f'{k}={v}' for k, v in a.items()))}</span>" if a else "")
                              for o, a in items)
            rows += f"<tr><td>{E(lab)}</td><td>{cells}</td></tr>"
        return f"<table>{rows}</table>" if rows else "<p class=muted>no relationships</p>"

    def tree(n):
        s = f"<li><a href='cap/{slug(n.path())}.html'>{E(n.name)}</a> <span class=muted>L{n.level()}</span>"
        c = [x for x in n.children]
        return s + (("<ul class=t>" + "".join(tree(x) for x in c) + "</ul>") if c else "") + "</li>"

    idx = ("<input id=q placeholder='filter...' oninput=\"for(const li of document.querySelectorAll('li'))"
           "li.style.display=li.textContent.toLowerCase().includes(this.value.toLowerCase())?'':'none'\">"
           "<ul class='t root'>" + "".join(tree(n) for n in m.top.children) + "</ul>")
    w(out, "index.html", page(f"{m.root_name} map", idx, 0))
    for n in m.all_nodes():
        props = "".join(f"<tr><td>{E(p.name)}</td><td>{E(str(v))}</td><td class=muted>{E(o)}</td></tr>"
                        for p in m.props.values() for v, o in [m.resolve(n, p)])
        crumbs = " / ".join(f"<a href='{'../' * 0}{slug(a.path())}.html'>{E(a.name)}</a>" for a in
                            [x for x in [n.parent] if x.parent is not None] and [])
        anc, a = [], n.parent
        while a is not None and a.parent is not None:
            anc.append(a)
            a = a.parent
        crumbs = " / ".join(f"<a href='{slug(x.path())}.html'>{E(x.name)}</a>" for x in reversed(anc))
        kids = "".join(f"<li><a href='{slug(c.path())}.html'>{E(c.name)}</a></li>" for c in n.children)
        provs = S.providers(m, n)
        body = (f"<p class=muted>{E(m.lvname(n))}{(' · ' + crumbs) if crumbs else ''}</p><h2>Properties</h2><table>{props}</table>"
                f"<h2>Relationships</h2>{links(S.cid(n), 1)}"
                + (f"<h2>Sub-capabilities</h2><ul>{kids}</ul>" if kids else "")
                + f"<h2>Provided by (including sub-capabilities)</h2><p>"
                + (", ".join(f"<a href='../ent/{slug(e.name)}.html'>{E(e.name)}</a>" for e in provs) or "<span class='pill bad'>white space</span>") + "</p>")
        w(out, f"cap/{slug(n.path())}.html", page(n.name, body, 1))
    for e in m.entities:
        props = "".join(f"<tr><td>{E(k)}</td><td>{E(str(v))}</td></tr>" for k, v in S.eprops(m, e).items())
        body = (f"<p class=muted>{E(e.type)} · is-a {E(' > '.join(m.chain(e.type)))}</p><h2>Properties</h2><table>{props}</table>"
                f"<h2>Relationships</h2>{links(S.eid(e), 1)}")
        w(out, f"ent/{slug(e.name)}.html", page(e.name, body, 1))
    rows = "".join(f"<tr><td><a href='ent/{slug(e.name)}.html'>{E(e.name)}</a></td><td>{E(e.type)}</td><td>{len(e.rels)}</td></tr>" for e in m.entities)
    w(out, "entities.html", page("Entities", f"<table><tr><th>Name<th>Type<th>Relations</tr>{rows}</table>", 0))
    min_lv, rows = S.provide_min_level(m), ""
    for n in (x for x in m.all_nodes() if x.level() >= S.provide_min_level(m)):
        pr = S.providers(m, n)
        rows += (f"<tr class={'bad' if not pr else ''}><td>{'&nbsp;' * 4 * (n.level() - min_lv)}<a href='cap/{slug(n.path())}.html'>{E(n.name)}</a></td>"
                 f"<td>L{n.level()}</td><td>{len(pr)}</td><td>{E(', '.join(e.name for e in pr)) or 'white space'}</td></tr>")
    w(out, "coverage.html", page("Coverage", f"<table><tr><th>Capability<th>Level<th>#<th>Providers</tr>{rows}</table>", 0))
    g = S.unmet(m)
    rows = "".join(f"<tr class=warn><td><a href='ent/{slug(e.name)}.html'>{E(e.name)}</a></td><td>{E(rt.name)}</td>"
                   f"<td><a href='cap/{slug(r['target'].path())}.html'>{E(r['target'].name)}</a></td><td>{E(r['attrs'].get('dependency', ''))}</td></tr>" for e, r, rt in g)
    w(out, "gaps.html", page("Unmet requirements", f"<table><tr><th>Entity<th>Relation<th>Capability<th>Severity</tr>{rows}</table>" if g else "<p>None.</p>", 0))
    st = "".join(f"<tr><td>{E(t.name)}</td><td>{E(t.parent or '')}</td><td>{E(', '.join(p.line() for p in m.eprop_defs(t.name).values()))}</td></tr>" for t in m.etypes.values())
    rt_ = "".join(f"<tr><td>{E(r.name)}</td><td>{E('|'.join(r.frm))} → {E('|'.join(r.to))}</td><td>{E(r.inverse or '')}</td>"
                  f"<td>{E(', '.join(p.line() for p in r.attrs.values()))}</td></tr>" for r in m.rtypes.values())
    w(out, "schema.html", page("Schema", f"<h2>Entity types</h2><table><tr><th>Type<th>is-a<th>Properties</tr>{st}</table>"
                                         f"<h2>Relation types</h2><table><tr><th>Name<th>Shape<th>Inverse<th>Attributes</tr>{rt_}</table>", 0))
    w(out, "graph.json", json.dumps({"nodes": sorted({i for e in S.edges(m) for i in e[:3:2]}),
                                    "edges": [{"s": s, "rel": l, "d": d, "attrs": a} for s, l, d, a, _ in S.edges(m)]}, indent=1))


# ---------------------------------------------------------------- sql
def sqlq(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def gen_sql(S, m, out, level):
    cap_cols = list(m.props)
    ent_props = []
    for t in m.etypes:
        for k in m.eprop_defs(t):
            if k not in ent_props:
                ent_props.append(k)
    L = ["-- generated; SQLite", "PRAGMA foreign_keys=ON;"]
    L.append("CREATE TABLE capability(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL, parent_id INTEGER REFERENCES capability(id), level INTEGER NOT NULL"
             + "".join(f", {c} {'INTEGER' if m.props[c].type == 'int' else 'TEXT'}" for c in cap_cols) + ");")
    L.append("CREATE TABLE entity_type(name TEXT PRIMARY KEY, parent TEXT REFERENCES entity_type(name));")
    L.append("CREATE TABLE entity(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL REFERENCES entity_type(name), props TEXT NOT NULL DEFAULT '{}');")
    L.append("CREATE TABLE relation_type(name TEXT PRIMARY KEY, inverse TEXT, from_types TEXT, to_types TEXT, transitive INTEGER, min_level INTEGER);")
    L.append("CREATE TABLE link(id INTEGER PRIMARY KEY, src INTEGER NOT NULL REFERENCES entity(id), relation TEXT NOT NULL REFERENCES relation_type(name),"
             " cap_id INTEGER REFERENCES capability(id), ent_id INTEGER REFERENCES entity(id), attrs TEXT NOT NULL DEFAULT '{}',"
             " CHECK((cap_id IS NULL) <> (ent_id IS NULL)));")
    L.append("CREATE INDEX link_rel ON link(relation, cap_id);")
    ids = {n: i + 1 for i, n in enumerate(m.all_nodes())}
    for n in m.all_nodes():
        vals = [S.pyval(n, m, c) if False else m.resolve(n, m.props[c])[0] for c in cap_cols]
        L.append(f"INSERT INTO capability VALUES({ids[n]},{sqlq(n.path())},{sqlq(n.name)},{ids[n.parent] if n.parent in ids else 'NULL'},{n.level()}"
                 + "".join("," + sqlq(v) for v in vals) + ");")
    for t in m.etypes.values():
        L.append(f"INSERT INTO entity_type VALUES({sqlq(t.name)},{sqlq(t.parent)});")
    eids = {e.name: i + 1 for i, e in enumerate(m.entities)}
    for e in m.entities:
        L.append(f"INSERT INTO entity VALUES({eids[e.name]},{sqlq(e.name)},{sqlq(e.type)},{sqlq(json.dumps(S.eprops(m, e)))});")
    for r in m.rtypes.values():
        L.append(f"INSERT INTO relation_type VALUES({sqlq(r.name)},{sqlq(r.inverse)},{sqlq('|'.join(r.frm))},{sqlq('|'.join(r.to))},{int(r.transitive)},{r.min_level or 'NULL'});")
    for e in m.entities:
        for r in e.rels:
            t = r["target"]
            if t is None:
                continue
            cap, ent = (ids[t], "NULL") if isinstance(t, S.Node) else ("NULL", eids[t.name])
            L.append(f"INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES({eids[e.name]},{sqlq(r['verb'])},{cap},{ent},{sqlq(json.dumps(r['attrs']))});")
    L.append("CREATE VIEW entity_active AS SELECT * FROM entity WHERE COALESCE(json_extract(props,'$.lifecycle'),'active')<>'retire';")
    for rt in m.rtypes.values():
        if rt.satisfied_by:
            vs = ",".join(sqlq(v) for v in rt.satisfied_by)
            L.append(f"CREATE VIEW unmet_{pyname(rt.name)} AS SELECT e.name AS entity, c.path AS capability, json_extract(l.attrs,'$.dependency') AS severity\n"
                     f"  FROM link l JOIN entity_active e ON e.id=l.src JOIN capability c ON c.id=l.cap_id WHERE l.relation={sqlq(rt.name)} AND NOT EXISTS (\n"
                     f"    SELECT 1 FROM link p JOIN entity_active pe ON pe.id=p.src JOIN capability pc ON pc.id=p.cap_id\n"
                     f"    WHERE p.relation IN ({vs}) AND pe.id<>l.src AND (pc.path=c.path OR pc.path LIKE c.path||'/%'));")
    prov = sorted(S.provide_verbs(m))
    if prov:
        vs = ",".join(sqlq(v) for v in prov)
        L.append(f"CREATE VIEW coverage AS SELECT c.path, c.level, (SELECT COUNT(DISTINCT p.src) FROM link p JOIN entity_active pe ON pe.id=p.src JOIN capability pc ON pc.id=p.cap_id\n"
                 f"  WHERE p.relation IN ({vs}) AND (pc.path=c.path OR pc.path LIKE c.path||'/%')) AS providers FROM capability c WHERE c.level>={S.provide_min_level(m)};")
    for rt in m.rtypes.values():
        if rt.transitive:
            L.append(f"CREATE VIEW {pyname(rt.name)}_closure AS WITH RECURSIVE r(src,dst) AS (SELECT src,ent_id FROM link WHERE relation={sqlq(rt.name)} AND ent_id IS NOT NULL\n"
                     f"  UNION SELECT r.src,l.ent_id FROM r JOIN link l ON l.src=r.dst WHERE l.relation={sqlq(rt.name)} AND l.ent_id IS NOT NULL)\n"
                     f"  SELECT a.name AS src, b.name AS dst FROM r JOIN entity a ON a.id=r.src JOIN entity b ON b.id=r.dst;")
    w(out, "schema.sql", "\n".join(L) + "\n")


# ---------------------------------------------------------------- typeql (draft)
def gen_typeql(S, m, out, level):
    attrs = {}
    for k, p in m.props.items():
        attrs[k] = p
    for t in m.etypes:
        for k, p in m.etypes[t].props.items():
            attrs.setdefault(k, p)
    tv = lambda p: "integer" if p.type == "int" else "string"
    L = ["# DRAFT - generated, not run against a TypeDB server. Check syntax against your TypeDB 3.x version.", "define", ""]
    L.append("attribute path, value string;")
    L.append("attribute name, value string;")
    for k, p in attrs.items():
        L.append(f"attribute {k}, value {tv(p)};")
    for rt in m.rtypes.values():
        for a, p in rt.attrs.items():
            L.append(f"attribute {rt.name}_{a}, value {tv(p)};")
    L.append("")
    L.append("entity capability, owns path @key, owns name, " + ", ".join(f"owns {k}" for k in m.props) + ", plays capability_hierarchy:parent, plays capability_hierarchy:child"
             + "".join(f", plays {rt.name}:target" for rt in cap_rels(m)) + ";")
    L.append("relation capability_hierarchy, relates parent, relates child;")
    for t in m.etypes.values():
        L.append(f"entity {pyname(t.name)}" + (f" sub {pyname(t.parent)}" if t.parent else ", owns name @key") + "".join(f", owns {k}" for k in t.props) + ";")
    for rt in m.rtypes.values():
        L.append(f"relation {rt.name}, relates source, relates target" + "".join(f", owns {rt.name}_{a}" for a in rt.attrs) + ";")
        for f in rt.frm:
            if f != "Capability" and f != "*":
                L.append(f"{pyname(f)} plays {rt.name}:source;")
        for tt in rt.to:
            if tt != "Capability" and tt != "*":
                L.append(f"{pyname(tt)} plays {rt.name}:target;")
    L += ["", "# rules and constraints (min_level, no_cycles, satisfied_by) are enforced in the generating model, not in this schema.", ""]
    w(out, "schema.tql", "\n".join(L) + "\n")
    D = ["# DRAFT data load"]
    for n in m.all_nodes():
        D.append(f"insert $c isa capability, has path {json.dumps(n.path())}, has name {json.dumps(n.name)}"
                 + "".join(f", has {k} {json.dumps(m.resolve(n, p)[0])}" for k, p in m.props.items() if m.resolve(n, p)[0] is not None) + ";")
    for n in m.all_nodes():
        if n.parent.parent is not None:
            D.append(f"match $p isa capability, has path {json.dumps(n.parent.path())}; $c isa capability, has path {json.dumps(n.path())}; insert capability_hierarchy(parent: $p, child: $c);")
    for e in m.entities:
        D.append(f"insert $e isa {pyname(e.type)}, has name {json.dumps(e.name)}" + "".join(f", has {k} {json.dumps(v)}" for k, v in S.eprops(m, e).items() if v is not None) + ";")
    for e in m.entities:
        for r in e.rels:
            t = r["target"]
            if t is None:
                continue
            key = f"$t isa capability, has path {json.dumps(t.path())}" if isinstance(t, S.Node) else f"$t isa {pyname(t.type)}, has name {json.dumps(t.name)}"
            D.append(f"match $s isa {pyname(e.type)}, has name {json.dumps(e.name)}; {key}; insert {r['verb']}(source: $s, target: $t)"
                     + "".join(f" has {r['verb']}_{k} {json.dumps(v)}" for k, v in r["attrs"].items()) + ";")
    w(out, "data.tql", "\n".join(D) + "\n")


# ---------------------------------------------------------------- json schema / openapi
def schemas(S, m):
    defs = {"Capability": {"type": "object", "required": ["path", "level"],
                           "properties": {"path": {"type": "string"}, "level": {"type": "integer", "minimum": 1, "maximum": m.depth_limit()},
                                          **{k: js_type(p) for k, p in m.props.items()}}}}
    defs["Link"] = {"type": "object", "required": ["target"], "properties": {"target": {"type": "string"}, "attrs": {"type": "object"}}}
    for t in m.etypes.values():
        own = {k: js_type(p) for k, p in t.props.items()}
        sch = {"type": "object", "properties": own}
        if not t.parent:
            sch["properties"]["name"] = {"type": "string"}
            sch["required"] = ["name"]
            sch["properties"]["relations"] = {"type": "object", "properties": {
                rt.name: {"type": "array", "items": {"$ref": f"#/$defs/Link_{rt.name}"}} for rt in m.rtypes.values()}}
        defs[t.name] = {"allOf": [{"$ref": f"#/$defs/{t.parent}"}, sch]} if t.parent else sch
        req = [k for k, p in t.props.items() if p.required]
        if req:
            sch["required"] = sch.get("required", []) + req
    for rt in m.rtypes.values():
        defs[f"Link_{rt.name}"] = {"type": "object", "required": ["target"], "properties": {
            "target": {"type": "string", "description": "->".join(rt.to)},
            "attrs": {"type": "object", "additionalProperties": False, "properties": {k: js_type(p) for k, p in rt.attrs.items()}}}}
    return defs


def gen_jsonschema(S, m, out, level):
    defs = schemas(S, m)
    doc = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": f"{m.root_name} model", "type": "object",
           "properties": {"capabilities": {"type": "array", "items": {"$ref": "#/$defs/Capability"}},
                          "entities": {"type": "array", "items": {"oneOf": [{"$ref": f"#/$defs/{t}"} for t in m.etypes]}}}, "$defs": defs}
    w(out, "schema.json", json.dumps(doc, indent=2))


def gen_openapi(S, m, out, level):
    comp = {k: json.loads(json.dumps(v).replace("#/$defs/", "#/components/schemas/")) for k, v in schemas(S, m).items()}
    ok = lambda ref, arr=False: {"200": {"description": "ok", "content": {"application/json": {"schema": (
        {"type": "array", "items": {"$ref": f"#/components/schemas/{ref}"}} if arr else {"$ref": f"#/components/schemas/{ref}"})}}}}
    paths = {"/capabilities": {"get": {"summary": "List capabilities", "parameters": [{"name": "level", "in": "query", "schema": {"type": "integer"}}], "responses": ok("Capability", True)}},
             "/capabilities/{path}": {"get": {"summary": "Get a capability", "parameters": [{"name": "path", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": ok("Capability")}},
             "/coverage": {"get": {"summary": "Providers per capability", "responses": {"200": {"description": "ok"}}}},
             "/gaps": {"get": {"summary": "Unmet requirements", "responses": {"200": {"description": "ok"}}}}}
    for t in m.etypes:
        p = f"/{pyname(t)}s"
        paths[p] = {"get": {"summary": f"List {t} entities", "responses": ok(t, True)}, "post": {"summary": f"Create {t}", "requestBody": {"content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{t}"}}}}, "responses": {"201": {"description": "created"}}}}
        paths[p + "/{name}"] = {"get": {"summary": f"Get {t}", "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": ok(t)}}
    for rt in m.rtypes.values():
        paths[f"/entities/{{name}}/{rt.name}"] = {"get": {"summary": f"{rt.name} links ({'|'.join(rt.frm)} -> {'|'.join(rt.to)})", "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": ok(f"Link_{rt.name}", True)}}
    w(out, "openapi.json", json.dumps({"openapi": "3.0.3", "info": {"title": f"{m.root_name} model API", "version": "1.0.0"}, "paths": paths, "components": {"schemas": comp}}, indent=2))


# ---------------------------------------------------------------- mermaid / csv
def gen_mermaid(S, m, out, level):
    mid = lambda i: "n" + re.sub(r"\W", "_", i)
    L = ["```mermaid", "flowchart LR"]
    shown = [n for n in m.all_nodes() if n.level() <= level]
    for n in shown:
        L.append(f'  {mid(S.cid(n))}["L{n.level()} {n.name}"]')
        if n.parent.parent is not None:
            L.append(f"  {mid(S.cid(n.parent))} --> {mid(S.cid(n))}")
    for e in m.entities:
        L.append(f'  {mid(S.eid(e))}(["{e.name}<br/><i>{e.type}</i>"])')
    for e in m.entities:
        for r in e.rels:
            t = r["target"]
            if t is None:
                continue
            if isinstance(t, S.Node):
                while t not in shown and t.parent.parent is not None:
                    t = t.parent
            lab = r["verb"] + ("*" if r["attrs"].get("coverage") == "partial" else "")
            style = "-.->" if r["verb"] in S.provide_verbs(m) and False else "-->"
            L.append(f"  {mid(S.eid(e))} {style}|{lab}| {mid(S.nid(t))}")
    L.append("```")
    w(out, "model.md", "\n".join(L) + "\n")


def gen_csv(S, m, out, level):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "capabilities.csv"), "w", newline="") as f:
        c = csv.writer(f)
        c.writerow(["path", "name", "level"] + list(m.props))
        for n in m.all_nodes():
            c.writerow([n.path(), n.name, n.level()] + [m.resolve(n, p)[0] for p in m.props.values()])
    keys = []
    for e in m.entities:
        for k in S.eprops(m, e):
            if k not in keys:
                keys.append(k)
    with open(os.path.join(out, "entities.csv"), "w", newline="") as f:
        c = csv.writer(f)
        c.writerow(["name", "type"] + keys)
        for e in m.entities:
            pr = S.eprops(m, e)
            c.writerow([e.name, e.type] + [pr.get(k, "") for k in keys])
    ak = sorted({k for rt in m.rtypes.values() for k in rt.attrs})
    with open(os.path.join(out, "relations.csv"), "w", newline="") as f:
        c = csv.writer(f)
        c.writerow(["source", "relation", "target", "target_kind"] + ak)
        for e in m.entities:
            for r in e.rels:
                if r["target"] is not None:
                    c.writerow([e.name, r["verb"], S.target_text(r), "capability" if isinstance(r["target"], S.Node) else "entity"] + [r["attrs"].get(k, "") for k in ak])


GENS = {"site": gen_site, "sql": gen_sql, "typeql": gen_typeql, "jsonschema": gen_jsonschema,
        "openapi": gen_openapi, "mermaid": gen_mermaid, "csv": gen_csv}


def run(S, m, kind, outdir, level):
    errs, _ = S.validate(m)
    if errs:
        raise SystemExit("refusing to generate from an invalid model:\n  - " + "\n  - ".join(errs))
    kinds = list(GENS) if kind == "all" else [kind]
    for k in kinds:
        if k not in GENS:
            raise SystemExit(f"unknown generator '{k}' (choose: {', '.join(GENS)}, all)")
        d = os.path.join(outdir, k) if kind == "all" else outdir
        GENS[k](S, m, d, level)
        print(f"generated {k} -> {d}")
