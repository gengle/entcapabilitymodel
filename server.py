"""server.py - demo server for a YAML model: JSON API + the React viewer built into web/dist (stdlib + PyYAML).

    python server.py [--model model] [--port 8765] [--host 127.0.0.1]

GET  /api/model                       snapshot: schema, capability tree, entities, files, issues, gaps
GET  /api/version                     changes whenever a YAML file under the model folder changes (poll it)
GET  /api/file?path=entities/x.yaml   raw file content
GET  /api/impact?entity=Name          what retiring/removing an entity would break
GET  /api/locate?id=<uuid or prefix>  the capabilities/entities with that id (or id prefix): route id, file, line
POST /api/preview {files: {path: content}}  snapshot as if those files had that content (nothing is written)
PUT  /api/file {path, content, force} write a file; rejected (422) if it adds validation errors, unless force
DELETE /api/file?path=...             delete a file; same rule
POST /api/ids                         give every capability/entity without an `id` a UUID (writes those files)
POST /api/version {to}                set model.yaml's version: major | minor | patch (bump) or an explicit x.y.z

ui.yaml in the model folder holds the viewer's form-control settings (written by its Forms page). Nothing includes it,
so it is not part of the model; it is read and written through /api/file and left out of the snapshot's file list.
"""
import argparse, collections, hashlib, json, mimetypes, os, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import semyaml
from semmodel import model, rules

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "web", "dist")
LOCK = threading.Lock()
ROOT = None  # absolute model folder, set in main()
UI_FILE = "ui.yaml"  # viewer form settings, not part of the model


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def version():
    h = hashlib.sha1()
    for p, r in semyaml.yaml_files(ROOT):
        st = os.stat(p)
        h.update(f"{r}:{st.st_mtime_ns}:{st.st_size};".encode())
    return h.hexdigest()[:16]


def safe_path(r):
    if not isinstance(r, str) or not r.endswith((".yaml", ".yml")):
        raise ValueError("path must be a .yaml/.yml file inside the model folder")
    p = os.path.normpath(os.path.join(ROOT, r))
    if os.path.commonpath([p, ROOT]) != ROOT:
        raise ValueError("path must be a .yaml/.yml file inside the model folder")
    return p


def load(overrides=None):
    """Load the model; overrides maps absolute paths to replacement text (None = deleted)."""
    return semyaml.load(ROOT, overrides)


# ------------------------------------------------------------------ snapshot
def prop_json(p):
    return {"name": p.name, "type": p.type, "enum": p.enum, "default": p.default,
            "inherit": p.inherit, "required": p.required, "spec": p.line(),
            "description": p.description, "valueDocs": p.docs, "to": p.targets or None, "key": p.key}


class Index:
    """Per-snapshot lookups built once: incoming references, provider levels, and ref resolution."""

    def __init__(self, m):
        self.m = m
        self.verbs, self.min_lv = rules.provide_verbs(m), rules.provide_min_level(m)
        self.incoming = collections.defaultdict(list)
        for e in m.entities:
            for r in e.rels:
                if r["target"] is not None and r["verb"] in m.rtypes:
                    rt = m.rtypes[r["verb"]]
                    self.incoming[rules.nid(r["target"])].append({
                        "verb": rt.name, "inverse": rt.inverse or f"~{rt.name}", "from": rules.eid(e),
                        "attrs": r["attrs"], "src": r.get("src")})
        for x, p, t in rules.refs(m):  # ref props (e.g. owner) point at entities too
            self.incoming[rules.eid(t)].append({"verb": p.name, "inverse": f"{p.name}_of", "from": rules.nid(x),
                                              "attrs": {}, "src": x.prop_src.get(p.name)})

    def ref_id(self, p, v):
        t = self.m.ref(p, v)
        return rules.eid(t) if t else None


def cap_props(ix, n):
    m, props = ix.m, []
    for p in m.props.values():
        try:
            v, origin = m.resolve(n, p)
        except ValueError as x:
            v, origin = n.local.get(p.name), f"invalid: {x}"
        src = None
        if origin == "local":
            src = n.prop_src.get(p.name)
        elif origin.startswith("inherited from "):
            a = m.find(origin[len("inherited from "):])
            src = a and a.prop_src.get(p.name)
        props.append({"name": p.name, "value": v, "origin": origin, "src": src, "ref": ix.ref_id(p, v)})
    return props


def cap_json(ix, n):
    m = ix.m
    direct = [rules.eid(e) for e in m.entities if rules.directly_provides(e, n, ix.verbs)]
    rolled = [rules.eid(e) for e in rules.providers(m, n)]
    status = None if n.level() < ix.min_lv else "white" if not rolled else "overlap" if len(direct) >= 2 else "ok"
    return {"id": rules.cid(n), "uid": n.uid, "name": n.name, "path": n.path(), "level": n.level(), "levelName": m.levels.get(n.level(), ""),
            "src": n.src, "props": cap_props(ix, n), "extra": [k for k in n.local if k not in m.props],
            "providers": direct, "rolledProviders": rolled, "status": status,
            "incoming": ix.incoming[rules.cid(n)], "children": [cap_json(ix, c) for c in n.children]}


def ent_json(ix, e):
    m = ix.m
    defs = m.eprop_defs(e.type) if e.type in m.etypes else {}
    props = [{"name": k, "value": e.local.get(k, p.default),
              "origin": "local" if k in e.local else "default" if p.default is not None else "unset",
              "src": e.prop_src.get(k), "ref": ix.ref_id(p, e.local.get(k, p.default))} for k, p in defs.items()]
    props += [{"name": k, "value": v, "origin": "unknown", "src": e.prop_src.get(k), "ref": None}
              for k, v in e.local.items() if k not in defs]
    rels = [{"verb": r["verb"], "text": r["text"], "target": rules.nid(r["target"]) if r["target"] is not None else None,
             "label": rules.target_text(r), "attrs": r["attrs"], "src": r.get("src"), "err": r["err"]} for r in e.rels]
    return {"id": rules.eid(e), "uid": e.uid, "name": e.name, "type": e.type, "chain": m.chain(e.type), "src": e.src,
            "retired": rules.retired(e), "props": props, "relations": rels, "incoming": ix.incoming[rules.eid(e)],
            "impact": impact_json(m, e)}


def issue_owners(m):
    """(message prefix, file) pairs, longest prefix first, so the first match owns the message."""
    owners = [(f"entity {e.name}:", e.src) for e in m.entities] + [(f"{e.name} ", e.src) for e in m.entities]
    owners += [(n.path() + ":", n.src) for n in m.all_nodes()] + [(f + ":", f) for f in m.files]
    owners.sort(key=lambda x: -len(x[0]))
    return owners


def issue_json(owners, level, msg):
    return {"level": level, "msg": msg, "file": next((src for pre, src in owners if msg.startswith(pre)), None)}


def file_infos(m):
    """Every YAML file under the model folder with its includes, plus what each file defines."""
    files = {}
    for p, r in semyaml.yaml_files(ROOT):
        if r == UI_FILE and r not in m.files:
            continue
        info = m.files.get(r)
        if info is None:
            try:
                kind = (semyaml.yaml.safe_load(open(p, encoding="utf-8")) or {}).get("kind")
            except Exception:
                kind = None
            info = {"kind": kind, "includes": []}
        files[r] = {"path": r, "kind": info["kind"] or "fragment", "includes": info["includes"], "includedBy": [],
                    "reached": r in m.files, "defines": []}
    for r, f in files.items():
        for inc in f["includes"]:
            if inc in files:
                files[inc]["includedBy"].append(r)
    for n in m.all_nodes():
        if n.src in files and (n.parent is m.top or n.parent.src != n.src):
            files[n.src]["defines"].append(rules.cid(n))
    for e in m.entities:
        if e.src in files:
            files[e.src]["defines"].append(rules.eid(e))
    return list(files.values())


def rtype_json(r):
    return {"name": r.name, "from": r.frm, "to": r.to, "attrs": [prop_json(p) for p in r.attrs.values()],
            "inverse": r.inverse, "minLevel": r.min_level, "satisfiedBy": r.satisfied_by, "conflictsWith": r.conflicts,
            "transitive": r.transitive, "noCycles": r.no_cycles, "description": r.description}


def etype_json(m, t):
    return {"name": t.name, "parent": t.parent, "chain": m.chain(t.name), "props": [prop_json(p) for p in t.props.values()],
            "effective": list(m.eprop_defs(t.name)), "description": t.description}


def snapshot(m):
    errs, warns = rules.validate(m)
    ix = Index(m)
    entities = [ent_json(ix, e) for e in m.entities]
    owners = issue_owners(m)
    covered = [n for n in m.all_nodes() if n.level() >= ix.min_lv]
    return {
        "entry": m.entry,
        "model": {"name": m.name, "version": m.version},
        "schema": {"root": m.root_name, "levels": {str(k): v for k, v in sorted(m.levels.items())},
                   "props": [prop_json(p) for p in m.props.values()], "rules": m.rules,
                   "entityTypes": [etype_json(m, t) for t in m.etypes.values()],
                   "relationTypes": [rtype_json(r) for r in m.rtypes.values()]},
        "capabilities": [cap_json(ix, n) for n in m.top.children],
        "entities": entities,
        "files": file_infos(m),
        "issues": [issue_json(owners, "error", x) for x in errs] + [issue_json(owners, "warning", x) for x in warns],
        "gaps": [{"entity": rules.eid(e), "verb": rt.name, "target": rules.cid(r["target"]),
                  "dependency": rules.dependency(r), "satisfiedBy": rt.satisfied_by} for e, r, rt in rules.unmet(m)],
        "coverage": {"minLevel": ix.min_lv, "total": len(covered), "covered": sum(1 for n in covered if rules.providers(m, n))},
    }


def impact_json(m, e):
    """rules.impact as JSON (see Impact in web/src/types.ts)."""
    i = rules.impact(m, e)
    return {"provides": [{"target": rules.cid(n), "others": [rules.eid(x) for x in others]} for n, others in i["provides"]],
            "white": [rules.cid(n) for n in i["white"]],
            "unmet": [{"entity": rules.eid(x), "verb": rt.name, "target": rules.cid(r["target"]),
                       "dependency": rules.dependency(r)} for x, r, rt in i["unmet"]],
            "dependents": [{"relation": rt.name, "inverse": rt.inverse, "affected": [{"id": x, "hops": d} for x, d in out]}
                           for rt, out in i["dependents"]],
            "referenced": [{"from": rules.nid(x), "prop": p.name} for x, p in i["referenced"]]}


def impact(m, name):
    e = m.entity(name)
    if e is None:
        raise ValueError(f"no entity '{name}'")
    return {"entity": rules.eid(e), **impact_json(m, e)}


# ------------------------------------------------------------------ http
NO_ENDPOINT = (404, {"error": "no such endpoint"})
VIEWER_MISSING = (b"<h1>Viewer not built</h1><p>Run <code>npm install && npm run build</code> in web/, "
                  b"or <code>npm run dev</code> there and open http://localhost:5173.</p>")


def with_version(m):
    return {**snapshot(m), "version": version()}


class Handler(BaseHTTPRequestHandler):
    # (method, path) -> handler method name
    ROUTES = {("GET", "/api/model"): "get_model", ("GET", "/api/version"): "get_version",
              ("GET", "/api/file"): "get_file", ("GET", "/api/impact"): "get_impact",
              ("GET", "/api/locate"): "get_locate",
              ("POST", "/api/ids"): "post_ids", ("POST", "/api/version"): "post_version",
              ("POST", "/api/preview"): "post_preview",
              ("PUT", "/api/file"): "put_file", ("DELETE", "/api/file"): "delete_file"}

    def log_message(self, fmt, *args):
        if "/api/version" not in self.path:
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = json.dumps(body).encode() if ctype.startswith("application/json") else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def query(self):
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def dispatch(self):
        try:
            url = urlparse(self.path).path
            name = self.ROUTES.get((self.command, url))
            if name:
                getattr(self, name)()
            elif self.command == "GET" and not url.startswith("/api/"):
                self.static(url)
            else:
                self.send(*NO_ENDPOINT)
        except ValueError as x:
            self.send(400, {"error": str(x)})
        except Exception as x:  # keep the demo server alive and say why
            self.send(500, {"error": f"{type(x).__name__}: {x}"})

    do_GET = do_POST = do_PUT = do_DELETE = dispatch

    def get_model(self):
        self.send(200, with_version(load()))

    def get_version(self):
        self.send(200, {"version": version()})

    def get_file(self):
        path = self.query().get("path")
        p = safe_path(path)
        if not os.path.isfile(p):
            return self.send(404, {"error": f"no file {path}"})
        self.send(200, {"path": rel(p), "content": open(p, encoding="utf-8").read()})

    def get_impact(self):
        self.send(200, impact(load(), self.query().get("entity", "")))

    def get_locate(self):
        m, q = load(), self.query().get("id", "")
        self.send(200, {"query": q, "matches": [
            {"id": rules.nid(x), "uid": x.uid, "kind": "capability" if isinstance(x, model.Node) else "entity",
             "label": rules.describe(x), "file": x.src, "line": rules.id_line(m, x)} for x in rules.locate(m, q)]})

    def post_ids(self):
        with LOCK:
            added = semyaml.assign_ids(ROOT)
            self.send(200, {**with_version(load()), "added": len(added)})

    def post_version(self):
        to = str(self.body().get("to", "")).strip()
        with LOCK:
            new = semyaml.bump(semyaml.read_version(ROOT), to)  # ValueError -> 400
            semyaml.write_version(ROOT, new)
            self.send(200, with_version(load()))

    def post_preview(self):
        b = self.body()
        files = dict(b.get("files") or {})
        if "path" in b:
            files[b["path"]] = b.get("content", "")
        self.send(200, snapshot(load({safe_path(k): str(v) for k, v in files.items()})))

    def change(self, overrides, force, apply):
        with LOCK:
            before = set(rules.validate(load())[0])
            added = [x for x in rules.validate(load(overrides))[0] if x not in before]
            if added and not force:
                return self.send(422, {"error": "rejected: the change adds validation errors", "errors": added})
            apply()
            self.send(200, with_version(load()))

    def put_file(self):
        b = self.body()
        p, content = safe_path(b.get("path")), str(b.get("content", ""))

        def write():
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
        self.change({p: content}, bool(b.get("force")), write)

    def delete_file(self):
        q = self.query()
        p = safe_path(q.get("path"))
        if not os.path.isfile(p):
            return self.send(404, {"error": f"no file {q.get('path')}"})
        self.change({p: None}, q.get("force") == "1", lambda: os.remove(p))

    def static(self, url):
        if not os.path.isdir(DIST):
            return self.send(200, VIEWER_MISSING, "text/html; charset=utf-8")
        p = os.path.normpath(os.path.join(DIST, url.lstrip("/")))
        if os.path.commonpath([p, DIST]) != DIST or not os.path.isfile(p):
            p = os.path.join(DIST, "index.html")
        self.send(200, open(p, "rb").read(), mimetypes.guess_type(p)[0] or "application/octet-stream")


def main():
    global ROOT
    ap = argparse.ArgumentParser(description="Serve a YAML semantic model and its React viewer.")
    ap.add_argument("--model", default=os.environ.get("SEM_MODEL") or os.path.join(HERE, "model"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    ROOT = os.path.abspath(a.model)
    if not os.path.isfile(os.path.join(ROOT, "model.yaml")):
        sys.exit(f"{ROOT} has no model.yaml (convert a .sem model with: python sem.py yaml <folder>)")
    print(f"serving {ROOT} on http://{a.host}:{a.port}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
