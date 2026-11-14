"""semyaml.py - load the semantic model from a tree of YAML files (and write one from any loaded model).

Every file is a mapping. A file with `kind` is a model document; a file without one is a fragment.
  kind: Model       include                                     the entry point (model.yaml)
  kind: Schema      root, levels, props, rules, entity_types, relations
  kind: Capability  name, parent (path, optional), props, children: [{name, props, children}]
  kind: Entity      type, name, props, relations: {verb: [target | {target: X, attr: value}]}
`include` (a path or list of paths, globs allowed, relative to the including file, inside the model folder)
loads each matching file. Documents are added to the model; fragments are merged into the including file
first (mappings merge, lists append, the including file wins on scalars). Each capability, entity, prop and
relation remembers the file it came from (`src`, `prop_src`, rel["src"]) so tools can point back at it.
Problems are collected in `m.load_errors` as "file: message" and reported by sem.validate.
"""
import copy, glob, os, re
import yaml

KEYS = {"Model": {"include", "name", "description"},
        "Schema": {"include", "root", "levels", "props", "rules", "entity_types", "relations"},
        "Capability": {"include", "name", "parent", "props", "children"},
        "Entity": {"include", "type", "name", "props", "relations"}}
CHILD_KEYS = {"name", "props", "children"}
RTYPE_KEYS = {"from", "to", "attrs", "inverse", "min_level", "satisfied_by", "conflicts_with", "transitive", "no_cycles"}


def sval(v):
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def names(v):
    return [] if v is None else [str(x) for x in v] if isinstance(v, list) else [x.strip() for x in str(v).split("|")]


def merge(dst, src, dprov, sprov, dp=(), sp=()):
    """Deep-merge src into dst, copying each leaf's source file from sprov(src path) into dprov[dst path]."""
    for k, v in src.items():
        if not dp and k == "include":
            continue
        d, s = dp + (k,), sp + (k,)
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            merge(dst[k], v, dprov, sprov, d, s)
        elif isinstance(v, list) and isinstance(dst.get(k), list):
            off = len(dst[k])
            dst[k].extend(copy.deepcopy(v))
            for i, x in enumerate(v):
                mark(x, dprov, sprov, d + (off + i,), s + (i,))
        else:
            for p in [p for p in dprov if p[:len(d)] == d]:
                del dprov[p]
            dst[k] = copy.deepcopy(v)
            mark(v, dprov, sprov, d, s)


def mark(v, dprov, sprov, d, s):
    dprov[d] = sprov(s)
    for k, x in (v.items() if isinstance(v, dict) else enumerate(v) if isinstance(v, list) else ()):
        mark(x, dprov, sprov, d + (k,), s + (k,))


class Loader:
    """overrides maps file paths to replacement text (None = treat the file as deleted)."""
    def __init__(self, root, overrides=None):
        self.root = os.path.abspath(root)
        self.overrides = {os.path.normcase(os.path.abspath(k)): v for k, v in (overrides or {}).items()}
        self.errors, self.docs, self.files, self.raw, self.visited = [], [], {}, {}, set()

    def rel(self, f):
        return os.path.relpath(f, self.root).replace(os.sep, "/")

    def err(self, f, msg):
        self.errors.append(f"{self.rel(f)}: {msg}")

    def read(self, f):
        """Parsed file content (cached), or None after recording why it could not be read."""
        if f not in self.raw:
            key, data = os.path.normcase(f), None
            try:
                if key in self.overrides and self.overrides[key] is None:
                    raise FileNotFoundError(2, "deleted")
                text = self.overrides[key] if key in self.overrides else open(f, encoding="utf-8").read()
                data = yaml.safe_load(text)
                data = {} if data is None else data
                if not isinstance(data, dict):
                    self.err(f, "a model file must be a mapping")
                    data = None
            except OSError as x:
                self.err(f, f"cannot read ({x.strerror})")
            except yaml.YAMLError as x:
                self.err(f, "YAML " + re.sub(r"\s+", " ", str(x)).replace(f'in "<unicode string>", ', ""))
            self.raw[f] = data
            self.files.setdefault(self.rel(f), {"kind": (data or {}).get("kind"), "includes": []})
        return self.raw[f]

    def expand(self, f, spec):
        out = []
        for pat in ([spec] if isinstance(spec, str) else spec if isinstance(spec, list) else [spec] if spec else []):
            if not isinstance(pat, str):
                self.err(f, f"include entries must be paths, got {pat!r}")
                continue
            full = os.path.normpath(os.path.join(os.path.dirname(f), pat))
            if os.path.commonpath([full, self.root]) != self.root:
                self.err(f, f"include '{pat}' points outside the model folder")
                continue
            hits = sorted(glob.glob(full)) if glob.has_magic(full) else [full] if os.path.isfile(full) else []
            hits = [h for h in hits if self.overrides.get(os.path.normcase(h), "") is not None]
            if not hits:
                self.err(f, f"include '{pat}' matches no file")
            out += [h for h in hits if h != f and h not in out]
        return out

    def visit(self, f):
        """Register document f (and every document it includes)."""
        if f in self.visited:
            return
        self.visited.add(f)
        data, prov = self.resolve(f, ())
        if data is not None:
            self.docs.append((self.rel(f), data, prov))

    def resolve(self, f, stack):
        """f's content with its fragments merged in, plus {path: source file} for every value."""
        data = self.read(f)
        if data is None:
            return None, None
        merged, prov = {}, {}
        incs = self.files[self.rel(f)]["includes"]
        for inc in self.expand(f, data.get("include")):
            if self.rel(inc) not in incs:
                incs.append(self.rel(inc))
            idata = self.read(inc)
            if idata is None:
                continue
            if "kind" in idata:
                self.visit(inc)
            elif inc in stack or inc == f:
                self.err(f, "include cycle: " + " -> ".join(self.rel(x) for x in stack + (f, inc)))
            else:
                fdata, fprov = self.resolve(inc, stack + (f,))
                if fdata is not None:
                    merge(merged, fdata, prov, lambda s, fp=fprov, src=self.rel(inc): fp.get(s, src))
        merge(merged, data, prov, lambda s, src=self.rel(f): src)
        return merged, prov


def load(path, S, overrides=None):
    """Load a YAML model from a folder (its model.yaml) or an entry file. S is the sem module."""
    path = os.path.abspath(path)
    root, entry = (path, os.path.join(path, "model.yaml")) if os.path.isdir(path) else (os.path.dirname(path), path)
    L = Loader(root, overrides)
    if L.read(entry) is not None and L.raw[entry].get("kind") != "Model":
        L.err(entry, "the entry file must have kind: Model")
    L.visit(entry)
    m = S.Model()
    m.yaml, m.src_root, m.entry, m.files, m.load_errors = True, root, L.rel(entry), L.files, L.errors
    m.top.src, m.top.prop_src = None, {}
    caps = []
    for f, d, prov in L.docs:
        kind = d.get("kind")
        if kind not in KEYS:
            L.errors.append(f"{f}: unknown kind '{kind}' (use {', '.join(KEYS)})")
            continue
        extra = set(d) - KEYS[kind] - {"kind"}
        if extra:
            L.errors.append(f"{f}: unknown key(s) for {kind}: {', '.join(sorted(extra))}")
        if kind == "Schema":
            schema(m, S, f, d, L.errors)
        elif kind == "Capability":
            caps.append((f, d, prov))
        elif kind == "Entity":
            entity(m, S, f, d, prov, L.errors)
    while caps:
        later = []
        for f, d, prov in caps:
            parent = m.top
            if d.get("parent"):
                parent, _ = m.find_cap(str(d["parent"]))
            if parent is None:
                later.append((f, d, prov))
            else:
                capability(m, S, parent, f, d, prov, (), L.errors)
        if len(later) == len(caps):
            L.errors += [f"{f}: parent capability '{d['parent']}' not found" for f, d, _ in later]
            break
        caps = later
    L.errors[:] = dict.fromkeys(L.errors)
    m.link()
    return m


def prop(S, name, spec):
    if isinstance(spec, str):
        return S.parse_prop(f"{name}: {spec}")
    spec = spec or {}
    typ = str(spec.get("type", "string"))
    if typ not in ("string", "int", "enum"):
        raise ValueError(f"property {name}: unknown type '{typ}'")
    vals = names(spec.get("values")) or None
    if (typ == "enum") != bool(vals):
        raise ValueError(f"property {name}: 'values' is required for enum and only allowed for enum")
    dflt = spec.get("default")
    return S.Prop(name, typ, vals, None if dflt is None else sval(dflt), bool(spec.get("inherit")), bool(spec.get("required")))


def props(S, f, specs, errors, where):
    out = {}
    if specs is not None and not isinstance(specs, dict):
        errors.append(f"{f}: {where} props must be a mapping")
        return out
    for name, spec in (specs or {}).items():
        try:
            out[name] = prop(S, name, spec)
        except ValueError as x:
            errors.append(f"{f}: {where}: {x}")
    return out


def schema(m, S, f, d, errors):
    if "root" in d:
        m.root_name = str(d["root"])
    for k, v in (d.get("levels") or {}).items():
        m.levels[int(k)] = str(v)
    m.props.update(props(S, f, d.get("props"), errors, m.root_name))
    for k, v in (d.get("rules") or {}).items():
        m.rules[k] = "" if v is None or v is True else sval(v)
    for name, spec in (d.get("entity_types") or {}).items():
        spec = spec or {}
        if name in m.etypes:
            errors.append(f"{f}: entity type '{name}' is defined twice")
        et = S.EType(str(name), spec.get("extends"))
        et.props = props(S, f, spec.get("props"), errors, f"entity type {name}")
        m.etypes[et.name] = et
    for name, spec in (d.get("relations") or {}).items():
        spec = spec or {}
        if name in m.rtypes:
            errors.append(f"{f}: relation '{name}' is defined twice")
        for k in set(spec) - RTYPE_KEYS:
            errors.append(f"{f}: relation {name}: unknown setting '{k}'")
        rt = S.RType(str(name))
        rt.frm, rt.to = names(spec.get("from")), names(spec.get("to"))
        rt.attrs = props(S, f, spec.get("attrs"), errors, f"relation {name}")
        rt.inverse = spec.get("inverse")
        rt.min_level = int(spec["min_level"]) if spec.get("min_level") is not None else None
        rt.satisfied_by, rt.conflicts = names(spec.get("satisfied_by")), names(spec.get("conflicts_with"))
        rt.transitive, rt.no_cycles = bool(spec.get("transitive")), bool(spec.get("no_cycles"))
        m.rtypes[rt.name] = rt


def capability(m, S, parent, f, d, prov, path, errors):
    if not d.get("name"):
        errors.append(f"{prov.get(path, f) if path else f}: capability without a name")
        return
    n = S.Node(str(d["name"]), parent)
    n.src, n.prop_src = prov.get(path + ("name",), f), {}
    parent.children.append(n)
    for k, v in (d.get("props") or {}).items():
        if v is not None:
            n.local[k], n.prop_src[k] = sval(v), prov.get(path + ("props", k), f)
    for i, c in enumerate(d.get("children") or []):
        if not isinstance(c, dict):
            errors.append(f"{n.src}: {n.path()}: children must be mappings with a name")
            continue
        for k in set(c) - CHILD_KEYS:
            errors.append(f"{n.src}: {n.path()}/{c.get('name')}: unknown key '{k}'")
        capability(m, S, n, f, c, prov, path + ("children", i), errors)


def entity(m, S, f, d, prov, errors):
    if not d.get("type") or not d.get("name"):
        errors.append(f"{f}: an Entity needs both type and name")
        return
    e = S.Entity(str(d["type"]), str(d["name"]))
    e.src, e.prop_src = f, {}
    for k, v in (d.get("props") or {}).items():
        if v is not None:
            e.local[k], e.prop_src[k] = sval(v), prov.get(("props", k), f)
    rels = d.get("relations") or {}
    if not isinstance(rels, dict):
        errors.append(f"{f}: relations must map a relation name to a list of targets")
        rels = {}
    for verb, items in rels.items():
        for i, it in enumerate(items if isinstance(items, list) else [items]):
            attrs = {}
            if isinstance(it, dict):
                attrs = {k: sval(v) for k, v in it.items() if k != "target"}
                it = it.get("target")
            if it is None:
                errors.append(f"{f}: {e.name}: a '{verb}' entry has no target")
                continue
            e.rels.append({"verb": str(verb), "text": str(it), "attrs": attrs, "target": None, "err": None,
                           "src": prov.get(("relations", verb, i), f)})
    m.entities.append(e)


# ------------------------------------------------------------------ writing
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def spec(p):
    return p.line().split(":", 1)[1].strip()


def typed(p, v):
    return int(v) if p is not None and p.type == "int" and re.fullmatch(r"-?\d+", str(v)) else v


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    return path


def dump(m, S, outdir):
    """Write m as a YAML source tree: model.yaml, schema.yaml, capabilities/<L1>.yaml, entities/<name>.yaml."""
    out = [write(os.path.join(outdir, "model.yaml"), {"kind": "Model", "include": ["schema.yaml", "capabilities/*.yaml", "entities/*.yaml"]})]
    sch = {"kind": "Schema", "root": m.root_name, "levels": dict(sorted(m.levels.items())),
           "props": {p.name: spec(p) for p in m.props.values()},
           "rules": {k: v or True for k, v in m.rules.items()},
           "entity_types": {t.name: {**({"extends": t.parent} if t.parent else {}),
                                     **({"props": {p.name: spec(p) for p in t.props.values()}} if t.props else {})} or None
                            for t in m.etypes.values()},
           "relations": {}}
    for r in m.rtypes.values():
        sch["relations"][r.name] = {k: v for k, v in (
            ("from", r.frm), ("to", r.to), ("attrs", {p.name: spec(p) for p in r.attrs.values()} or None),
            ("inverse", r.inverse), ("min_level", r.min_level), ("satisfied_by", r.satisfied_by or None),
            ("conflicts_with", r.conflicts or None), ("transitive", r.transitive or None), ("no_cycles", r.no_cycles or None)) if v is not None}
    out.append(write(os.path.join(outdir, "schema.yaml"), sch))

    def cap(n):
        d = {"name": n.name}
        if n.local:
            d["props"] = {k: typed(m.props.get(k), v) for k, v in n.local.items()}
        if n.children:
            d["children"] = [cap(c) for c in n.children]
        return d
    for top in m.top.children:
        out.append(write(os.path.join(outdir, "capabilities", slug(top.name) + ".yaml"), {"kind": "Capability", **cap(top)}))
    for e in m.entities:
        defs = m.eprop_defs(e.type) if e.type in m.etypes else {}
        d = {"kind": "Entity", "type": e.type, "name": e.name}
        if e.local:
            d["props"] = {k: typed(defs.get(k), v) for k, v in e.local.items()}
        rels = {}
        for r in e.rels:
            t = S.target_text(r)
            rels.setdefault(r["verb"], []).append({"target": t, **r["attrs"]} if r["attrs"] else t)
        if rels:
            d["relations"] = rels
        out.append(write(os.path.join(outdir, "entities", slug(e.name) + ".yaml"), d))
    return out
