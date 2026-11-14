"""server.py - demo server for a YAML model: JSON API + the React viewer built into web/dist (stdlib + PyYAML).

    python server.py [--model model] [--port 8765] [--host 127.0.0.1]

GET  /api/model                       snapshot: schema, capability tree, entities, files, issues, gaps
GET  /api/version                     changes whenever a YAML file under the model folder changes (poll it)
GET  /api/file?path=entities/x.yaml   raw file content
GET  /api/impact?entity=Name          what retiring/removing an entity would break
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

import sem
import semyaml

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "web", "dist")
LOCK = threading.Lock()
ROOT = None  # absolute model folder, set in main()
UI_FILE = "ui.yaml"  # viewer form settings, not part of the model


def yaml_files():
    out = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        out += [os.path.join(d, f) for f in sorted(files) if f.endswith((".yaml", ".yml"))]
    return out


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def version():
    h = hashlib.sha1()
    for p in yaml_files():
        st = os.stat(p)
        h.update(f"{rel(p)}:{st.st_mtime_ns}:{st.st_size};".encode())
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
    return semyaml.load(ROOT, sem, overrides)


# ------------------------------------------------------------------ snapshot
def prop_json(p):
    return {"name": p.name, "type": p.type, "enum": p.enum, "default": p.default,
            "inherit": p.inherit, "required": p.required, "spec": p.line()}


def snapshot(m):
    errs, warns = sem.validate(m)
    verbs, min_lv = sem.provide_verbs(m), sem.provide_min_level(m)
    nodes, ents = m.all_nodes(), m.entities
    incoming = collections.defaultdict(list)
    for e in ents:
        for r in e.rels:
            if r["target"] is not None and r["verb"] in m.rtypes:
                rt = m.rtypes[r["verb"]]
                incoming[sem.nid(r["target"])].append({"verb": rt.name, "inverse": rt.inverse or f"~{rt.name}",
                                                       "from": sem.eid(e), "attrs": r["attrs"], "src": r.get("src")})

    def cap(n):
        props = []
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
            props.append({"name": p.name, "value": v, "origin": origin, "src": src})
        direct = [sem.eid(e) for e in ents if any(r["verb"] in verbs and r["target"] is n for r in e.rels)]
        rolled = [sem.eid(e) for e in sem.providers(m, n)]
        status = None if n.level() < min_lv else "white" if not rolled else "overlap" if len(direct) >= 2 else "ok"
        return {"id": sem.cid(n), "uid": n.uid, "name": n.name, "path": n.path(), "level": n.level(), "levelName": m.levels.get(n.level(), ""),
                "src": n.src, "props": props, "extra": [k for k in n.local if k not in m.props],
                "providers": direct, "rolledProviders": rolled, "status": status,
                "incoming": incoming[sem.cid(n)], "children": [cap(c) for c in n.children]}

    def ent(e):
        defs = m.eprop_defs(e.type) if e.type in m.etypes else {}
        props = [{"name": k, "value": e.local.get(k, p.default),
                  "origin": "local" if k in e.local else "default" if p.default is not None else "unset",
                  "src": e.prop_src.get(k)} for k, p in defs.items()]
        props += [{"name": k, "value": v, "origin": "unknown", "src": e.prop_src.get(k)} for k, v in e.local.items() if k not in defs]
        rels = [{"verb": r["verb"], "text": r["text"], "target": sem.nid(r["target"]) if r["target"] is not None else None,
                 "label": sem.target_text(r), "attrs": r["attrs"], "src": r.get("src"), "err": r["err"]} for r in e.rels]
        return {"id": sem.eid(e), "uid": e.uid, "name": e.name, "type": e.type, "chain": m.chain(e.type), "src": e.src,
                "retired": sem.retired(e), "props": props, "relations": rels, "incoming": incoming[sem.eid(e)]}

    entities = [ent(e) for e in ents]
    owners = [(f"entity {e.name}:", e.src) for e in ents] + [(f"{e.name} ", e.src) for e in ents]
    owners += [(n.path() + ":", n.src) for n in nodes] + [(f + ":", f) for f in m.files]
    owners.sort(key=lambda x: -len(x[0]))

    def issue(level, msg):
        f = next((src for pre, src in owners if msg.startswith(pre)), None)
        return {"level": level, "msg": msg, "file": f}

    files = {}
    for p in yaml_files():
        r = rel(p)
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
    for n in nodes:
        if n.src in files and (n.parent is m.top or n.parent.src != n.src):
            files[n.src]["defines"].append(sem.cid(n))
    for e in ents:
        if e.src in files:
            files[e.src]["defines"].append(sem.eid(e))

    rtypes = [{"name": r.name, "from": r.frm, "to": r.to, "attrs": [prop_json(p) for p in r.attrs.values()],
               "inverse": r.inverse, "minLevel": r.min_level, "satisfiedBy": r.satisfied_by, "conflictsWith": r.conflicts,
               "transitive": r.transitive, "noCycles": r.no_cycles} for r in m.rtypes.values()]
    etypes = [{"name": t.name, "parent": t.parent, "chain": m.chain(t.name), "props": [prop_json(p) for p in t.props.values()],
               "effective": list(m.eprop_defs(t.name))} for t in m.etypes.values()]
    covered = [n for n in nodes if n.level() >= min_lv]
    return {
        "entry": m.entry,
        "model": {"name": m.name, "version": m.version},
        "schema": {"root": m.root_name, "levels": {str(k): v for k, v in sorted(m.levels.items())},
                   "props": [prop_json(p) for p in m.props.values()], "rules": m.rules,
                   "entityTypes": etypes, "relationTypes": rtypes},
        "capabilities": [cap(n) for n in m.top.children],
        "entities": entities,
        "files": list(files.values()),
        "issues": [issue("error", x) for x in errs] + [issue("warning", x) for x in warns],
        "gaps": [{"entity": sem.eid(e), "verb": rt.name, "target": sem.cid(r["target"]),
                  "dependency": r["attrs"].get("dependency", "hard"), "satisfiedBy": rt.satisfied_by} for e, r, rt in sem.unmet(m)],
        "coverage": {"minLevel": min_lv, "total": len(covered), "covered": sum(1 for n in covered if sem.providers(m, n))},
    }


def impact(m, name):
    e = m.entity(name)
    if e is None:
        raise ValueError(f"no entity '{name}'")
    before = {(x.name, r["target"].path(), r["verb"]) for x, r, _ in sem.unmet(m)}
    lost = [sem.cid(n) for n in m.all_nodes() if sem.providers(m, n) and not sem.providers(m, n, {e.name})]
    new = [{"entity": sem.eid(x), "verb": rt.name, "target": sem.cid(r["target"]), "dependency": r["attrs"].get("dependency", "hard")}
           for x, r, rt in sem.unmet(m, {e.name}) if (x.name, r["target"].path(), r["verb"]) not in before]
    adj, chains = sem.adjacency(m), []
    for rt in m.rtypes.values():
        if rt.transitive and rt.inverse:
            seen, queue, out = {sem.eid(e)}, collections.deque([(sem.eid(e), 0)]), []
            while queue:
                cur, d = queue.popleft()
                for lab, other, _ in adj[cur]:
                    if lab == rt.inverse and other not in seen:
                        seen.add(other)
                        queue.append((other, d + 1))
                        out.append({"id": other, "hops": d + 1})
            if out:
                chains.append({"relation": rt.name, "affected": out})
    return {"entity": sem.eid(e), "lostCapabilities": lost, "newUnmet": new, "transitive": chains}


# ------------------------------------------------------------------ http
class Handler(BaseHTTPRequestHandler):
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

    def route(self, fn):
        try:
            fn()
        except ValueError as x:
            self.send(400, {"error": str(x)})
        except Exception as x:  # keep the demo server alive and say why
            self.send(500, {"error": f"{type(x).__name__}: {x}"})

    def do_GET(self):
        self.route(self.get)

    def do_POST(self):
        self.route(self.post)

    def do_PUT(self):
        self.route(self.put)

    def do_DELETE(self):
        self.route(self.delete)

    def get(self):
        url, q = urlparse(self.path).path, self.query()
        if url == "/api/model":
            self.send(200, {**snapshot(load()), "version": version()})
        elif url == "/api/version":
            self.send(200, {"version": version()})
        elif url == "/api/file":
            p = safe_path(q.get("path"))
            if not os.path.isfile(p):
                return self.send(404, {"error": f"no file {q.get('path')}"})
            self.send(200, {"path": rel(p), "content": open(p, encoding="utf-8").read()})
        elif url == "/api/impact":
            self.send(200, impact(load(), q.get("entity", "")))
        elif url.startswith("/api/"):
            self.send(404, {"error": "no such endpoint"})
        else:
            self.static(url)

    def post(self):
        url = urlparse(self.path).path
        if url == "/api/ids":
            with LOCK:
                added = semyaml.assign_ids(ROOT)
                return self.send(200, {**snapshot(load()), "version": version(), "added": len(added)})
        if url == "/api/version":
            to = str(self.body().get("to", "")).strip()
            with LOCK:
                new = sem.bump(semyaml.read_version(ROOT), to)  # ValueError -> 400
                semyaml.write_version(ROOT, new)
                return self.send(200, {**snapshot(load()), "version": version()})
        if url != "/api/preview":
            return self.send(404, {"error": "no such endpoint"})
        b = self.body()
        files = dict(b.get("files") or {})
        if "path" in b:
            files[b["path"]] = b.get("content", "")
        self.send(200, snapshot(load({safe_path(k): str(v) for k, v in files.items()})))

    def change(self, overrides, force, apply):
        with LOCK:
            before = set(sem.validate(load())[0])
            m = load(overrides)
            added = [x for x in sem.validate(m)[0] if x not in before]
            if added and not force:
                return self.send(422, {"error": "rejected: the change adds validation errors", "errors": added})
            apply()
            self.send(200, {**snapshot(load()), "version": version()})

    def put(self):
        if urlparse(self.path).path != "/api/file":
            return self.send(404, {"error": "no such endpoint"})
        b = self.body()
        p, content = safe_path(b.get("path")), str(b.get("content", ""))

        def write():
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
        self.change({p: content}, bool(b.get("force")), write)

    def delete(self):
        if urlparse(self.path).path != "/api/file":
            return self.send(404, {"error": "no such endpoint"})
        q = self.query()
        p = safe_path(q.get("path"))
        if not os.path.isfile(p):
            return self.send(404, {"error": f"no file {q.get('path')}"})
        self.change({p: None}, q.get("force") == "1", lambda: os.remove(p))

    def static(self, url):
        if not os.path.isdir(DIST):
            return self.send(200, b"<h1>Viewer not built</h1><p>Run <code>npm install && npm run build</code> in web/, "
                                  b"or <code>npm run dev</code> there and open http://localhost:5173.</p>", "text/html; charset=utf-8")
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
