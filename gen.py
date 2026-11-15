"""Generators: every output is derived from the model, so adding a type/relation/entity changes them all.

Add a generator by writing gen_x(S, m, out, level) and registering it in GENS."""
import csv, html, json, os, re

# ---------------------------------------------------------------- shared helpers
# prop type -> target type (anything not listed is a string)
JSON_TYPES = {"int": "integer"}
SQL_TYPES = {"int": "INTEGER"}
TQL_TYPES = {"int": "integer"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def w(outdir, name, text):
    p = os.path.join(outdir, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8", newline="\n").write(text)
    return p


def pyname(s):
    return re.sub(r"\W+", "_", s).lower()


def sqlq(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def jq(v):
    return json.dumps(v)


def cap_rels(m):
    return [rt for rt in m.rtypes.values() if "Capability" in rt.to or "*" in rt.to]


def desc(x):
    """Description of a Prop, EType or RType (None when undocumented, e.g. legacy .sem models)."""
    return getattr(x, "description", None) or None


def vdocs(p):
    """Enum value -> meaning, in the enum's declared order, documented values only."""
    d = getattr(p, "docs", None) or {}
    return {v: d[v] for v in (p.enum or []) if d.get(v)}


def vdoc(p, v):
    return (getattr(p, "docs", None) or {}).get(str(v)) if v is not None else None


def cap_cols(m):
    """The per-capability property columns: (name, Prop)."""
    return list(m.props.items())


def cap_values(m, n):
    """Resolved value of each capability column for node n, in column order."""
    return [m.resolve(n, p)[0] for p in m.props.values()]


def owners(m):
    """(kind, owner name, own props) for capability, entity types and relation types (property tables)."""
    return ([("capability", m.root_name, m.props)] + [("entity_type", t.name, t.props) for t in m.etypes.values()]
            + [("relation_type", r.name, r.attrs) for r in m.rtypes.values()])


def rel_ends(types):
    """Entity types (not Capability/wildcard) named at one end of a relation type."""
    return [t for t in types if t not in ("Capability", "*")]


def comment_doc(x, prefix="#"):
    return [f"{prefix} {' '.join(desc(x).split())}"] if desc(x) else []


def with_desc(x, sch):
    return {"description": desc(x), **sch} if desc(x) else sch


def js_type(p):
    s = {"type": JSON_TYPES.get(p.type, "string")}
    if p.type == "enum":
        s["enum"] = p.enum
    if desc(p):
        s["description"] = desc(p)
    if vdocs(p):
        s["x-enumDescriptions"] = vdocs(p)
    return s


# ---------------------------------------------------------------- site
CSS = """body{font:15px/1.5 system-ui,sans-serif;margin:0;color:#1d1d1f;background:#fafaf8}
nav{background:#1f2a37;padding:10px 24px}nav a{color:#e5e7eb;margin-right:18px;text-decoration:none}
main{max-width:980px;margin:24px auto;padding:0 24px}h1{font-size:24px}h2{font-size:17px;margin-top:28px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e3e3df;padding:6px 10px;text-align:left}
th{font-weight:600;color:#555}.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;background:#e8eef7}
.warn{background:#fff3d6}.bad{background:#fde2e0}.ok{background:#e1f3e4}ul.t{list-style:none;padding-left:18px}ul.t.root{padding-left:0}
.muted{color:#777;font-size:13px}td ul.v{margin:0;padding-left:18px}h3{font-size:15px;margin:18px 0 4px}input{padding:6px 10px;width:100%;box-sizing:border-box;margin:8px 0}"""

E = html.escape


def table(head, rows):
    return f"<table><tr>{head}</tr>{rows}</table>"


class Site:
    """Static HTML site; one method per page family."""

    def __init__(self, S, m, out):
        self.S, self.m, self.out, self.adj = S, m, out, S.adjacency(m)

    def write(self, name, title, body, depth=0):
        pre = "../" * depth
        w(self.out, name, f"<!doctype html><meta charset=utf-8><title>{E(title)}</title><style>{CSS}</style>"
          f"<nav><a href='{pre}index.html'>Capability map</a><a href='{pre}entities.html'>Entities</a>"
          f"<a href='{pre}coverage.html'>Coverage</a><a href='{pre}gaps.html'>Gaps</a><a href='{pre}schema.html'>Schema</a></nav>"
          f"<main><h1>{E(title)}</h1>{body}</main>")

    @staticmethod
    def href(i, depth):
        kind, name = i.split(":", 1)
        return f"{'../' * depth}{'cap' if kind == 'cap' else 'ent'}/{slug(name)}.html"

    # --- fragments
    def rtype(self, lab):
        return self.m.rtypes.get(lab) or next((r for r in self.m.rtypes.values() if r.inverse == lab), None)

    def attr_text(self, lab, k, v):
        rt = self.rtype(lab)
        p = rt.attrs.get(k) if rt else None
        mean = vdoc(p, v) if p else None
        return f"<span title='{E(mean)}'>{E(f'{k}={v}')}</span>" if mean else E(f"{k}={v}")

    @staticmethod
    def field(p):
        return E(p.name) + (f"<div class=muted>{E(desc(p))}</div>" if desc(p) else "")

    def value(self, p, v, depth=1):
        mean = vdoc(p, v) if p is not None else None
        t = self.m.ref(p, v) if getattr(p, "type", None) == "ref" else None  # ref props link to the entity they name
        shown = (f"<a href='{self.href(self.S.eid(t), depth)}'>{E(t.name)}</a>"
                 + (f" <span class=muted>({E(str(v))})</span>" if t.name.lower() != str(v).lower() else "")) if t else E(str(v))
        return shown + (f"<div class=muted>{E(mean)}</div>" if mean else "")

    @staticmethod
    def fields(props):
        rows = ""
        for p in props.values():
            t = p.type + (f" · default {p.default}" if p.default is not None else "") + (" · inherit" if p.inherit else "") + (" · required" if p.required else "")
            vals = vdocs(p)
            vs = (("<ul class=v>" + "".join(f"<li><b>{E(v)}</b>" + (f" — {E(vals[v])}" if v in vals else "") + "</li>" for v in p.enum) + "</ul>")
                  if p.enum else "")
            rows += f"<tr><td>{E(p.name)}</td><td class=muted>{E(t)}</td><td>{E(desc(p) or '')}{vs}</td></tr>"
        return f"<table><tr><th>Field<th>Type<th>Meaning</tr>{rows}</table>" if rows else "<p class=muted>no own properties</p>"

    def links(self, i, depth, skip=("parent_of", "child_of")):
        by = {}
        for lab, other, attrs in self.adj[i]:
            if lab not in skip:
                by.setdefault(lab, []).append((other, attrs))
        rows = ""
        for lab, items in by.items():
            cells = ", ".join(f"<a href='{self.href(o, depth)}'>{E(o.split(':', 1)[1].split('/')[-1])}</a>"
                              + (f" <span class=muted>{', '.join(self.attr_text(lab, k, v) for k, v in a.items())}</span>" if a else "")
                              for o, a in items)
            rows += f"<tr><td>{E(lab)}</td><td>{cells}</td></tr>"
        return f"<table>{rows}</table>" if rows else "<p class=muted>no relationships</p>"

    def detail(self, subtitle, rows, rid, extra=""):
        """Body shared by capability and entity pages: subtitle, properties table, relationships, then extra."""
        return (f"<p class=muted>{subtitle}</p><h2>Properties</h2><table>{rows}</table>"
                f"<h2>Relationships</h2>{self.links(rid, 1)}" + extra)

    # --- pages
    def tree(self, n):
        s = f"<li><a href='cap/{slug(n.path())}.html'>{E(n.name)}</a> <span class=muted>L{n.level()}</span>"
        c = list(n.children)
        return s + (("<ul class=t>" + "".join(self.tree(x) for x in c) + "</ul>") if c else "") + "</li>"

    def index(self):
        idx = ("<input id=q placeholder='filter...' oninput=\"for(const li of document.querySelectorAll('li'))"
               "li.style.display=li.textContent.toLowerCase().includes(this.value.toLowerCase())?'':'none'\">"
               "<ul class='t root'>" + "".join(self.tree(n) for n in self.m.top.children) + "</ul>")
        self.write("index.html", f"{self.m.root_name} map", idx)

    def cap_page(self, n):
        S, m = self.S, self.m
        rows = "".join(f"<tr><td>{self.field(p)}</td><td>{self.value(p, v)}</td><td class=muted>{E(o)}</td></tr>"
                       for p in m.props.values() for v, o in [m.resolve(n, p)])
        anc, a = [], n.parent
        while a is not None and a.parent is not None:
            anc.append(a)
            a = a.parent
        crumbs = " / ".join(f"<a href='{slug(x.path())}.html'>{E(x.name)}</a>" for x in reversed(anc))
        kids = "".join(f"<li><a href='{slug(c.path())}.html'>{E(c.name)}</a></li>" for c in n.children)
        provs = ", ".join(f"<a href='../ent/{slug(e.name)}.html'>{E(e.name)}</a>" for e in S.providers(m, n)) or "<span class='pill bad'>white space</span>"
        extra = ((f"<h2>Sub-capabilities</h2><ul>{kids}</ul>" if kids else "")
                 + f"<h2>Provided by (including sub-capabilities)</h2><p>{provs}</p>")
        sub = E(m.lvname(n)) + (' · ' + crumbs if crumbs else '')
        self.write(f"cap/{slug(n.path())}.html", n.name, self.detail(sub, rows, S.cid(n), extra), 1)

    def ent_page(self, e):
        S, m = self.S, self.m
        pd = m.eprop_defs(e.type)
        rows = "".join(f"<tr><td>{self.field(pd[k])}</td><td>{self.value(pd[k], v)}</td></tr>" for k, v in S.eprops(m, e).items())
        td = desc(m.etypes.get(e.type))
        sub = f"{E(e.type)} · is-a {E(' > '.join(m.chain(e.type)))}{(' · ' + E(td)) if td else ''}"
        self.write(f"ent/{slug(e.name)}.html", e.name, self.detail(sub, rows, S.eid(e)), 1)

    def entities(self):
        rows = "".join(f"<tr><td><a href='ent/{slug(e.name)}.html'>{E(e.name)}</a></td><td>{E(e.type)}</td><td>{len(e.rels)}</td></tr>" for e in self.m.entities)
        self.write("entities.html", "Entities", table("<th>Name<th>Type<th>Relations", rows))

    def coverage(self):
        S, m = self.S, self.m
        min_lv, rows = S.provide_min_level(m), ""
        for n in (x for x in m.all_nodes() if x.level() >= min_lv):
            pr = S.providers(m, n)
            rows += (f"<tr class={'bad' if not pr else ''}><td>{'&nbsp;' * 4 * (n.level() - min_lv)}<a href='cap/{slug(n.path())}.html'>{E(n.name)}</a></td>"
                     f"<td>L{n.level()}</td><td>{len(pr)}</td><td>{E(', '.join(e.name for e in pr)) or 'white space'}</td></tr>")
        self.write("coverage.html", "Coverage", table("<th>Capability<th>Level<th>#<th>Providers", rows))

    def gaps(self):
        g = self.S.unmet(self.m)
        rows = "".join(f"<tr class=warn><td><a href='ent/{slug(e.name)}.html'>{E(e.name)}</a></td><td>{E(rt.name)}</td>"
                       f"<td><a href='cap/{slug(r['target'].path())}.html'>{E(r['target'].name)}</a></td><td>{E(r['attrs'].get('dependency', ''))}</td></tr>" for e, r, rt in g)
        self.write("gaps.html", "Unmet requirements", table("<th>Entity<th>Relation<th>Capability<th>Severity", rows) if g else "<p>None.</p>")

    def schema(self):
        m = self.m
        lines = lambda props: E(", ".join(p.line() for p in props.values()))
        st = "".join(f"<tr><td>{E(t.name)}</td><td>{E(t.parent or '')}</td><td>{E(desc(t) or '')}</td><td>{lines(m.eprop_defs(t.name))}</td></tr>" for t in m.etypes.values())
        rt_ = "".join(f"<tr><td>{E(r.name)}</td><td>{E('|'.join(r.frm))} → {E('|'.join(r.to))}</td><td>{E(r.inverse or '')}</td><td>{E(desc(r) or '')}</td>"
                      f"<td>{lines(r.attrs)}</td></tr>" for r in m.rtypes.values())
        note = lambda x: f"<p class=muted>{E(desc(x))}</p>" if desc(x) else ""
        tf = "".join(f"<h3>{E(t.name)}{(' <span class=muted>is-a ' + E(t.parent) + ' (inherits its fields)</span>') if t.parent else ''}</h3>"
                     + note(t) + self.fields(t.props) for t in m.etypes.values())
        rf = "".join(f"<h3>{E(r.name)}</h3>" + note(r) + self.fields(r.attrs) for r in m.rtypes.values() if r.attrs)
        self.write("schema.html", "Schema",
                   f"<h2>{E(m.root_name)} properties</h2>{self.fields(m.props)}"
                   f"<h2>Entity types</h2>{table('<th>Type<th>is-a<th>Description<th>Properties', st)}"
                   f"<h2>Relation types</h2>{table('<th>Name<th>Shape<th>Inverse<th>Description<th>Attributes', rt_)}"
                   f"<h2>Entity type fields</h2>{tf}" + (f"<h2>Relation attributes</h2>{rf}" if rf else ""))

    def graph(self):
        ed = self.S.edges(self.m)
        w(self.out, "graph.json", json.dumps({"nodes": sorted({i for e in ed for i in e[:3:2]}),
                                              "edges": [{"s": s, "rel": l, "d": d, "attrs": a} for s, l, d, a, _ in ed]}, indent=1))


def gen_site(S, m, out, level):
    s = Site(S, m, out)
    s.index()
    for n in m.all_nodes():
        s.cap_page(n)
    for e in m.entities:
        s.ent_page(e)
    s.entities(), s.coverage(), s.gaps(), s.schema(), s.graph()


# ---------------------------------------------------------------- sql
SQL_TABLES = [
    "CREATE TABLE entity_type(name TEXT PRIMARY KEY, parent TEXT REFERENCES entity_type(name), description TEXT);",
    "CREATE TABLE entity(id INTEGER PRIMARY KEY, uid TEXT UNIQUE, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL REFERENCES entity_type(name), props TEXT NOT NULL DEFAULT '{}');",
    "CREATE TABLE relation_type(name TEXT PRIMARY KEY, inverse TEXT, from_types TEXT, to_types TEXT, transitive INTEGER, min_level INTEGER, description TEXT);",
    # owner_kind: 'capability' (owner = root name), 'entity_type' (owner = type, own props only) or 'relation_type' (owner = verb, its attrs)
    "CREATE TABLE property(owner_kind TEXT NOT NULL, owner TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, default_value TEXT,"
    " inherit INTEGER, required INTEGER, description TEXT, PRIMARY KEY(owner_kind, owner, name));",
    "CREATE TABLE property_value(owner_kind TEXT NOT NULL, owner TEXT NOT NULL, property TEXT NOT NULL, value TEXT NOT NULL, ord INTEGER NOT NULL, description TEXT,"
    " PRIMARY KEY(owner_kind, owner, property, value), FOREIGN KEY(owner_kind, owner, property) REFERENCES property(owner_kind, owner, name));",
    "CREATE TABLE link(id INTEGER PRIMARY KEY, src INTEGER NOT NULL REFERENCES entity(id), relation TEXT NOT NULL REFERENCES relation_type(name),"
    " cap_id INTEGER REFERENCES capability(id), ent_id INTEGER REFERENCES entity(id), attrs TEXT NOT NULL DEFAULT '{}',"
    " CHECK((cap_id IS NULL) <> (ent_id IS NULL)));",
    "CREATE INDEX link_rel ON link(relation, cap_id);",
]


def sql_tables(m):
    cols = cap_cols(m)
    # SQLite has no COMMENT ON: column meanings go in comments here and, queryable, in property/property_value below.
    L = [f"-- capability.{c}: {' '.join(desc(p).split())}" for c, p in cols if desc(p)]
    L.append("CREATE TABLE capability(id INTEGER PRIMARY KEY, uid TEXT UNIQUE, path TEXT UNIQUE NOT NULL, name TEXT NOT NULL, parent_id INTEGER REFERENCES capability(id), level INTEGER NOT NULL"
             + "".join(f", {c} {SQL_TYPES.get(p.type, 'TEXT')}" for c, p in cols) + ");")
    return L + SQL_TABLES


def sql_inserts(S, m, ids, eids):
    L = []
    for n in m.all_nodes():
        L.append(f"INSERT INTO capability VALUES({ids[n]},{sqlq(n.uid)},{sqlq(n.path())},{sqlq(n.name)},{ids[n.parent] if n.parent in ids else 'NULL'},{n.level()}"
                 + "".join("," + sqlq(v) for v in cap_values(m, n)) + ");")
    for t in m.etypes.values():
        L.append(f"INSERT INTO entity_type VALUES({sqlq(t.name)},{sqlq(t.parent)},{sqlq(desc(t))});")
    for e in m.entities:
        L.append(f"INSERT INTO entity VALUES({eids[e.name]},{sqlq(e.uid)},{sqlq(e.name)},{sqlq(e.type)},{sqlq(jq(S.eprops(m, e)))});")
    for r in m.rtypes.values():
        L.append(f"INSERT INTO relation_type VALUES({sqlq(r.name)},{sqlq(r.inverse)},{sqlq('|'.join(r.frm))},{sqlq('|'.join(r.to))},{int(r.transitive)},{r.min_level or 'NULL'},{sqlq(desc(r))});")
    for kind, owner, props in owners(m):
        for p in props.values():
            L.append(f"INSERT INTO property VALUES({sqlq(kind)},{sqlq(owner)},{sqlq(p.name)},{sqlq(p.type)},{sqlq(p.default)},{int(bool(p.inherit))},{int(bool(p.required))},{sqlq(desc(p))});")
            for i, v in enumerate(p.enum or []):
                L.append(f"INSERT INTO property_value VALUES({sqlq(kind)},{sqlq(owner)},{sqlq(p.name)},{sqlq(v)},{i},{sqlq(vdoc(p, v))});")
    for e in m.entities:
        for r in e.rels:
            t = r["target"]
            if t is None:
                continue
            cap, ent = (ids[t], "NULL") if isinstance(t, S.Node) else ("NULL", eids[t.name])
            L.append(f"INSERT INTO link(src,relation,cap_id,ent_id,attrs) VALUES({eids[e.name]},{sqlq(r['verb'])},{cap},{ent},{sqlq(jq(r['attrs']))});")
    return L


def sql_views(S, m):
    L = ["CREATE VIEW entity_active AS SELECT * FROM entity WHERE COALESCE(json_extract(props,'$.lifecycle'),'active')<>'retire';"]
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
    return L


def gen_sql(S, m, out, level):
    ids = {n: i + 1 for i, n in enumerate(m.all_nodes())}
    eids = {e.name: i + 1 for i, e in enumerate(m.entities)}
    L = ["-- generated; SQLite" + (f" from model version {m.version}" if m.version else ""), "PRAGMA foreign_keys=ON;"]
    L += sql_tables(m) + sql_inserts(S, m, ids, eids) + sql_views(S, m)
    w(out, "schema.sql", "\n".join(L) + "\n")


# ---------------------------------------------------------------- typeql (draft)
def tql_attributes(m):
    """Attribute definitions: capability props, then first definition of each entity-type prop, then relation attrs."""
    attrs = dict(m.props)
    for t in m.etypes.values():
        for k, p in t.props.items():
            attrs.setdefault(k, p)
    L = ["attribute path, value string;", "attribute name, value string;"]
    for k, p in attrs.items():
        L += comment_doc(p) + [f"attribute {k}, value {TQL_TYPES.get(p.type, 'string')};"]
    for rt in m.rtypes.values():
        for a, p in rt.attrs.items():
            L += comment_doc(p) + [f"attribute {rt.name}_{a}, value {TQL_TYPES.get(p.type, 'string')};"]
    return L


def tql_entities(m):
    L = ["entity capability, owns path @key, owns name, " + ", ".join(f"owns {k}" for k in m.props) + ", plays capability_hierarchy:parent, plays capability_hierarchy:child"
         + "".join(f", plays {rt.name}:target" for rt in cap_rels(m)) + ";",
         "relation capability_hierarchy, relates parent, relates child;"]
    for t in m.etypes.values():
        L += comment_doc(t)
        L.append(f"entity {pyname(t.name)}" + (f" sub {pyname(t.parent)}" if t.parent else ", owns name @key") + "".join(f", owns {k}" for k in t.props) + ";")
    return L


def tql_relations(m):
    L = []
    for rt in m.rtypes.values():
        L += comment_doc(rt)
        L.append(f"relation {rt.name}, relates source, relates target" + "".join(f", owns {rt.name}_{a}" for a in rt.attrs) + ";")
        L += [f"{pyname(f)} plays {rt.name}:source;" for f in rel_ends(rt.frm)]
        L += [f"{pyname(t)} plays {rt.name}:target;" for t in rel_ends(rt.to)]
    return L


def tql_data(S, m):
    D = ["# DRAFT data load"]
    for n in m.all_nodes():
        D.append(f"insert $c isa capability, has path {jq(n.path())}, has name {jq(n.name)}"
                 + "".join(f", has {k} {jq(v)}" for (k, _), v in zip(cap_cols(m), cap_values(m, n)) if v is not None) + ";")
    for n in m.all_nodes():
        if n.parent.parent is not None:
            D.append(f"match $p isa capability, has path {jq(n.parent.path())}; $c isa capability, has path {jq(n.path())}; insert capability_hierarchy(parent: $p, child: $c);")
    for e in m.entities:
        D.append(f"insert $e isa {pyname(e.type)}, has name {jq(e.name)}" + "".join(f", has {k} {jq(v)}" for k, v in S.eprops(m, e).items() if v is not None) + ";")
    for e in m.entities:
        for r in e.rels:
            t = r["target"]
            if t is None:
                continue
            key = f"$t isa capability, has path {jq(t.path())}" if isinstance(t, S.Node) else f"$t isa {pyname(t.type)}, has name {jq(t.name)}"
            D.append(f"match $s isa {pyname(e.type)}, has name {jq(e.name)}; {key}; insert {r['verb']}(source: $s, target: $t)"
                     + "".join(f" has {r['verb']}_{k} {jq(v)}" for k, v in r["attrs"].items()) + ";")
    return D


def gen_typeql(S, m, out, level):
    L = ["# DRAFT - generated, not run against a TypeDB server. Check syntax against your TypeDB 3.x version.", "define", ""]
    L += tql_attributes(m) + [""] + tql_entities(m) + tql_relations(m)
    L += ["", "# rules and constraints (min_level, no_cycles, satisfied_by) are enforced in the generating model, not in this schema.", ""]
    w(out, "schema.tql", "\n".join(L) + "\n")
    w(out, "data.tql", "\n".join(tql_data(S, m)) + "\n")


# ---------------------------------------------------------------- json schema / openapi
def def_capability(m):
    return {"type": "object", "required": ["path", "level"],
            "properties": {"path": {"type": "string"}, "level": {"type": "integer", "minimum": 1, "maximum": m.depth_limit()},
                           **{k: js_type(p) for k, p in m.props.items()}}}


def def_entity_type(m, t):
    sch = {"type": "object", "properties": {k: js_type(p) for k, p in t.props.items()}}
    if not t.parent:
        sch["properties"]["name"] = {"type": "string"}
        sch["required"] = ["name"]
        sch["properties"]["relations"] = {"type": "object", "properties": {
            rt.name: {"type": "array", "items": {"$ref": f"#/$defs/Link_{rt.name}"}} for rt in m.rtypes.values()}}
    d = {"allOf": [{"$ref": f"#/$defs/{t.parent}"}, sch]} if t.parent else sch
    req = [k for k, p in t.props.items() if p.required]
    if req:
        sch["required"] = sch.get("required", []) + req
    return with_desc(t, d)


def def_link(rt):
    return with_desc(rt, {"type": "object", "required": ["target"], "properties": {
        "target": {"type": "string", "description": "->".join(rt.to)},
        "attrs": {"type": "object", "additionalProperties": False, "properties": {k: js_type(p) for k, p in rt.attrs.items()}}}})


def schemas(S, m):
    defs = {"Capability": def_capability(m),
            "Link": {"type": "object", "required": ["target"], "properties": {"target": {"type": "string"}, "attrs": {"type": "object"}}}}
    for t in m.etypes.values():
        defs[t.name] = def_entity_type(m, t)
    for rt in m.rtypes.values():
        defs[f"Link_{rt.name}"] = def_link(rt)
    return defs


def gen_jsonschema(S, m, out, level):
    doc = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": f"{m.root_name} model", "type": "object",
           "properties": {"capabilities": {"type": "array", "items": {"$ref": "#/$defs/Capability"}},
                          "entities": {"type": "array", "items": {"oneOf": [{"$ref": f"#/$defs/{t}"} for t in m.etypes]}}}, "$defs": schemas(S, m)}
    w(out, "schema.json", json.dumps(doc, indent=2))


def gen_openapi(S, m, out, level):
    comp = {k: json.loads(json.dumps(v).replace("#/$defs/", "#/components/schemas/")) for k, v in schemas(S, m).items()}
    ref = lambda r: {"$ref": f"#/components/schemas/{r}"}
    ok = lambda r, arr=False: {"200": {"description": "ok", "content": {"application/json": {"schema": (
        {"type": "array", "items": ref(r)} if arr else ref(r))}}}}
    pparam = lambda name: [{"name": name, "in": "path", "required": True, "schema": {"type": "string"}}]
    paths = {"/capabilities": {"get": {"summary": "List capabilities", "parameters": [{"name": "level", "in": "query", "schema": {"type": "integer"}}], "responses": ok("Capability", True)}},
             "/capabilities/{path}": {"get": {"summary": "Get a capability", "parameters": pparam("path"), "responses": ok("Capability")}},
             "/coverage": {"get": {"summary": "Providers per capability", "responses": {"200": {"description": "ok"}}}},
             "/gaps": {"get": {"summary": "Unmet requirements", "responses": {"200": {"description": "ok"}}}}}
    for t in m.etypes:
        p = f"/{pyname(t)}s"
        paths[p] = {"get": {"summary": f"List {t} entities", "responses": ok(t, True)}, "post": {"summary": f"Create {t}", "requestBody": {"content": {"application/json": {"schema": ref(t)}}}, "responses": {"201": {"description": "created"}}}}
        paths[p + "/{name}"] = {"get": {"summary": f"Get {t}", "parameters": pparam("name"), "responses": ok(t)}}
    for rt in m.rtypes.values():
        paths[f"/entities/{{name}}/{rt.name}"] = {"get": {"summary": f"{rt.name} links ({'|'.join(rt.frm)} -> {'|'.join(rt.to)})", "parameters": pparam("name"), "responses": ok(f"Link_{rt.name}", True)}}
    w(out, "openapi.json", json.dumps({"openapi": "3.0.3", "info": {"title": f"{m.name or m.root_name + ' model'} API", "version": m.version or "0.0.0"}, "paths": paths, "components": {"schemas": comp}}, indent=2))


# ---------------------------------------------------------------- mermaid / csv
def mermaid_nodes(S, m, shown, mid):
    L = []
    for n in shown:
        L.append(f'  {mid(S.cid(n))}["L{n.level()} {n.name}"]')
        if n.parent.parent is not None:
            L.append(f"  {mid(S.cid(n.parent))} --> {mid(S.cid(n))}")
    return L + [f'  {mid(S.eid(e))}(["{e.name}<br/><i>{e.type}</i>"])' for e in m.entities]


def mermaid_edges(S, m, shown, mid):
    L = []
    for e in m.entities:
        for r in e.rels:
            t = r["target"]
            if t is None:
                continue
            if isinstance(t, S.Node):
                while t not in shown and t.parent.parent is not None:
                    t = t.parent
            lab = r["verb"] + ("*" if r["attrs"].get("coverage") == "partial" else "")
            L.append(f"  {mid(S.eid(e))} -->|{lab}| {mid(S.nid(t))}")
    return L


def gen_mermaid(S, m, out, level):
    mid = lambda i: "n" + re.sub(r"\W", "_", i)
    shown = [n for n in m.all_nodes() if n.level() <= level]
    L = ["```mermaid", "flowchart LR"] + mermaid_nodes(S, m, shown, mid) + mermaid_edges(S, m, shown, mid) + ["```"]
    w(out, "model.md", "\n".join(L) + "\n")


def write_csv(out, name, header, rows):
    with open(os.path.join(out, name), "w", newline="", encoding="utf-8") as f:
        c = csv.writer(f)
        c.writerow(header)
        c.writerows(rows)


def gen_csv(S, m, out, level):
    os.makedirs(out, exist_ok=True)
    write_csv(out, "capabilities.csv", ["id", "path", "name", "level"] + list(m.props),
              ([n.uid or "", n.path(), n.name, n.level()] + cap_values(m, n) for n in m.all_nodes()))
    keys = []
    for e in m.entities:
        keys += [k for k in S.eprops(m, e) if k not in keys]
    write_csv(out, "entities.csv", ["id", "name", "type"] + keys,
              ([e.uid or "", e.name, e.type] + [S.eprops(m, e).get(k, "") for k in keys] for e in m.entities))
    ak = sorted({k for rt in m.rtypes.values() for k in rt.attrs})
    write_csv(out, "relations.csv", ["source", "relation", "target", "target_kind"] + ak,
              ([e.name, r["verb"], S.target_text(r), "capability" if isinstance(r["target"], S.Node) else "entity"] + [r["attrs"].get(k, "") for k in ak]
               for e in m.entities for r in e.rels if r["target"] is not None))


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
