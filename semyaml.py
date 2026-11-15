"""semyaml.py - load the semantic model from a tree of YAML files (and write one from any loaded model).

Every file is a mapping. A file with `kind` is a model document; a file without one is a fragment.
  kind: Model       name, version (MAJOR.MINOR.PATCH), include   the entry point (model.yaml)
  kind: Schema      root, levels, props, rules, entity_types, relations
  kind: Capability  name, id, parent (path, optional), props, children: [{name, id, props, children}]
  kind: Entity      type, name, id, props, relations: {verb: [target | {target: X, attr: value}]}
`id` is a capability's or entity's universal id (a UUID). It survives renames and moves, a relation target may use it
instead of a name, and `python sem.py ids` (or assign_ids below) writes one for every object that lacks it.
`include` (a path or list of paths, globs allowed, relative to the including file, inside the model folder)
loads each matching file. Documents are added to the model; fragments are merged into the including file
first (mappings merge, lists append, the including file wins on scalars). Each capability, entity, prop and
relation remembers the file it came from (`src`, `prop_src`, rel["src"]) so tools can point back at it.
Problems are collected in `m.load_errors` as "file: message" and reported by sem.validate.
A prop (capability props, entity type props, relation attrs) is a .sem spec string, or a mapping that can document it:
  {type: string|int|enum|ref, description, values: [a, b] | {a: meaning, b: meaning}, to: [EntityType, ...],
   default, inherit, required, key}
`ref` values point at an entity of a `to` type by its name, id or a `key` prop (`key: true`, e.g. a User's email);
see Model.ref. Unresolved refs are validation warnings.
Entity types and relation types also take `description`. These become Prop.description / Prop.docs and .description.
"""
import copy, glob, os, re
import yaml
from semmodel.model import Model, Prop, EType, RType, Node, Entity, SEMVER_RE, parse_prop, slug, target_text

KEYS = {"Model": {"include", "name", "description", "version"},
        "Schema": {"include", "root", "levels", "props", "rules", "entity_types", "relations"},
        "Capability": {"include", "name", "id", "parent", "props", "children"},
        "Entity": {"include", "type", "name", "id", "props", "relations"}}
CHILD_KEYS = {"name", "id", "props", "children"}
PROP_KEYS = {"type", "values", "to", "default", "inherit", "required", "key", "description"}
ETYPE_KEYS = {"extends", "props", "description"}
RTYPE_KEYS = {"description", "from", "to", "attrs", "inverse", "min_level", "satisfied_by", "conflicts_with", "transitive", "no_cycles"}
PROP_TYPES = ("string", "int", "enum", "ref")


# ------------------------------------------------------------------ scalar coercion
def sval(v):
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def names(v):
    return [] if v is None else [str(x) for x in v] if isinstance(v, list) else [x.strip() for x in str(v).split("|")]


def _opt(v, f=sval):
    """f(v), or None when v is None."""
    return None if v is None else f(v)


def _text(v):
    return _opt(v, lambda x: str(x).strip())


# ------------------------------------------------------------------ include merging
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

    def source(self, f):
        """The text of f (an override wins); raises OSError when missing or overridden as deleted."""
        key = os.path.normcase(f)
        if key in self.overrides:
            if self.overrides[key] is None:
                raise FileNotFoundError(2, "deleted")
            return self.overrides[key]
        with open(f, encoding="utf-8") as fh:
            return fh.read()

    def parse(self, f):
        """f's content as a mapping, or None after recording why it could not be read."""
        try:
            data = yaml.safe_load(self.source(f))
            data = {} if data is None else data
            if not isinstance(data, dict):
                self.err(f, "a model file must be a mapping")
                return None
            return data
        except OSError as x:
            self.err(f, f"cannot read ({x.strerror})")
        except yaml.YAMLError as x:
            self.err(f, "YAML " + re.sub(r"\s+", " ", str(x)).replace(f'in "<unicode string>", ', ""))

    def read(self, f):
        """Parsed file content (cached), or None after recording why it could not be read."""
        if f not in self.raw:
            data = self.raw[f] = self.parse(f)
            self.files.setdefault(self.rel(f), {"kind": (data or {}).get("kind"), "includes": []})
        return self.raw[f]

    def matches(self, f, pat):
        """Existing, non-deleted files for one include pattern; records an error when it is bad or matches nothing."""
        if not isinstance(pat, str):
            self.err(f, f"include entries must be paths, got {pat!r}")
            return []
        full = os.path.normpath(os.path.join(os.path.dirname(f), pat))
        if os.path.commonpath([full, self.root]) != self.root:
            self.err(f, f"include '{pat}' points outside the model folder")
            return []
        hits = sorted(glob.glob(full)) if glob.has_magic(full) else [full] if os.path.isfile(full) else []
        hits = [h for h in hits if self.overrides.get(os.path.normcase(h), "") is not None]
        if not hits:
            self.err(f, f"include '{pat}' matches no file")
        return hits

    def expand(self, f, spec):
        out = []
        for pat in ([spec] if isinstance(spec, str) else spec if isinstance(spec, list) else [spec] if spec else []):
            out += [h for h in self.matches(f, pat) if h != f and h not in out]
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


# ------------------------------------------------------------------ loading
def load(path, overrides=None):
    """Load a YAML model from a folder (its model.yaml) or an entry file."""
    path = os.path.abspath(path)
    root, entry = (path, os.path.join(path, "model.yaml")) if os.path.isdir(path) else (os.path.dirname(path), path)
    L = Loader(root, overrides)
    if L.read(entry) is not None and L.raw[entry].get("kind") != "Model":
        L.err(entry, "the entry file must have kind: Model")
    L.visit(entry)
    m = Model()
    m.yaml, m.src_root, m.entry, m.files, m.load_errors = True, root, L.rel(entry), L.files, L.errors
    m.top.src, m.top.prop_src = None, {}
    caps = _load_docs(m, L)
    _attach_caps(m, caps, L.errors)
    L.errors[:] = dict.fromkeys(L.errors)
    m.link()
    return m


def _load_docs(m, L):
    """Apply every document by kind; Capability documents are returned for later, since they may name a parent."""
    caps = []
    for f, d, prov in L.docs:
        kind = d.get("kind")
        if kind not in KEYS:
            L.errors.append(f"{f}: unknown kind '{kind}' (use {', '.join(KEYS)})")
            continue
        extra = set(d) - KEYS[kind] - {"kind"}
        if extra:
            L.errors.append(f"{f}: unknown key(s) for {kind}: {', '.join(sorted(extra))}")
        if kind == "Model" and f == m.entry:
            m.name, m.version = _opt(d.get("name")), _opt(d.get("version"))
        elif kind == "Schema":
            schema(m, f, d, L.errors)
        elif kind == "Capability":
            caps.append((f, d, prov))
        elif kind == "Entity":
            entity(m, f, d, prov, L.errors)
    return caps


def _attach_caps(m, caps, errors):
    """Attach capability documents under their `parent:` (or the root), retrying until none more can be placed."""
    while caps:
        later = []
        for f, d, prov in caps:
            parent = m.find_cap(str(d["parent"]))[0] if d.get("parent") else m.top
            if parent is None:
                later.append((f, d, prov))
            else:
                capability(parent, f, d, prov, (), errors)
        if len(later) == len(caps):
            errors += [f"{f}: parent capability '{d['parent']}' not found" for f, d, _ in later]
            break
        caps = later


def prop(name, spec):
    """A property from its .sem syntax string, or from a mapping that can also document it:
    {type, values, default, inherit, required, description}, where `values` is a list or a mapping of value -> meaning."""
    if isinstance(spec, str):
        return parse_prop(f"{name}: {spec}")
    spec = spec or {}
    bad = lambda msg: ValueError(f"property {name}: {msg}")
    if not isinstance(spec, dict):
        raise bad("expected a spec string or a mapping")
    for k in set(spec) - PROP_KEYS:
        raise bad(f"unknown setting '{k}'")
    typ = str(spec.get("type", "string"))
    if typ not in PROP_TYPES:
        raise bad(f"unknown type '{typ}'")
    targets = names(spec.get("to"))
    if (typ == "ref") != bool(targets):
        raise bad("'to' (the entity types it may point at) is required for ref and only allowed for ref")
    vals, docs = _prop_values(spec.get("values"))
    if (typ == "enum") != bool(vals):
        raise bad("'values' is required for enum and only allowed for enum")
    dflt = _opt(spec.get("default"))
    if dflt is not None and vals and dflt not in vals:
        raise bad(f"default '{dflt}' is not one of its values")
    p = Prop(name, typ, vals, dflt, bool(spec.get("inherit")), bool(spec.get("required")), targets or None, bool(spec.get("key")))
    if spec.get("description") is not None:
        p.description = str(spec["description"]).strip()
    p.docs = {k: v for k, v in docs.items() if v}
    return p


def _prop_values(raw):
    """(values list or None, {value: meaning}) from a `values:` list or mapping."""
    if isinstance(raw, dict):
        docs = {sval(k): _text(v) for k, v in raw.items()}
        return list(docs), docs
    return names(raw) or None, {}


def props(f, specs, errors, where):
    out = {}
    if specs is not None and not isinstance(specs, dict):
        errors.append(f"{f}: {where} props must be a mapping")
        return out
    for name, spec in (specs or {}).items():
        try:
            out[name] = prop(name, spec)
        except ValueError as x:
            errors.append(f"{f}: {where}: {x}")
    return out


def schema(m, f, d, errors):
    if "root" in d:
        m.root_name = str(d["root"])
    for k, v in (d.get("levels") or {}).items():
        m.levels[int(k)] = str(v)
    m.props.update(props(f, d.get("props"), errors, m.root_name))
    for k, v in (d.get("rules") or {}).items():
        m.rules[k] = "" if v is None or v is True else sval(v)
    for name, spec in (d.get("entity_types") or {}).items():
        spec = spec or {}
        if name in m.etypes:
            errors.append(f"{f}: entity type '{name}' is defined twice")
        errors += [f"{f}: entity type {name}: unknown setting '{k}'" for k in set(spec) - ETYPE_KEYS]
        et = EType(str(name), spec.get("extends"))
        et.description = _text(spec.get("description"))
        et.props = props(f, spec.get("props"), errors, f"entity type {name}")
        m.etypes[et.name] = et
    for name, spec in (d.get("relations") or {}).items():
        spec = spec or {}
        if name in m.rtypes:
            errors.append(f"{f}: relation '{name}' is defined twice")
        errors += [f"{f}: relation {name}: unknown setting '{k}'" for k in set(spec) - RTYPE_KEYS]
        rt = _rtype(f, str(name), spec, errors)
        m.rtypes[rt.name] = rt


def _rtype(f, name, spec, errors):
    rt = RType(name)
    rt.description = _text(spec.get("description"))
    rt.frm, rt.to = names(spec.get("from")), names(spec.get("to"))
    rt.attrs = props(f, spec.get("attrs"), errors, f"relation {name}")
    rt.inverse = spec.get("inverse")
    rt.min_level = _opt(spec.get("min_level"), int)
    rt.satisfied_by, rt.conflicts = names(spec.get("satisfied_by")), names(spec.get("conflicts_with"))
    rt.transitive, rt.no_cycles = bool(spec.get("transitive")), bool(spec.get("no_cycles"))
    return rt


def _load_props(obj, d, prov, base, f):
    """Copy d's non-null props (as strings) into obj.local, remembering each one's source file."""
    for k, v in (d.get("props") or {}).items():
        if v is not None:
            obj.local[k], obj.prop_src[k] = sval(v), prov.get(base + ("props", k), f)


def capability(parent, f, d, prov, path, errors):
    if not d.get("name"):
        errors.append(f"{prov.get(path, f) if path else f}: capability without a name")
        return
    n = Node(str(d["name"]), parent)
    n.src, n.prop_src = prov.get(path + ("name",), f), {}
    n.uid = _opt(d.get("id"))
    parent.children.append(n)
    _load_props(n, d, prov, path, f)
    for i, c in enumerate(d.get("children") or []):
        if not isinstance(c, dict):
            errors.append(f"{n.src}: {n.path()}: children must be mappings with a name")
            continue
        errors += [f"{n.src}: {n.path()}/{c.get('name')}: unknown key '{k}'" for k in set(c) - CHILD_KEYS]
        capability(n, f, c, prov, path + ("children", i), errors)


def entity(m, f, d, prov, errors):
    if not d.get("type") or not d.get("name"):
        errors.append(f"{f}: an Entity needs both type and name")
        return
    e = Entity(str(d["type"]), str(d["name"]))
    e.src, e.prop_src = f, {}
    e.uid = _opt(d.get("id"))
    _load_props(e, d, prov, (), f)
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
def _clean(pairs):
    """A mapping of the (key, value) pairs whose value is not None."""
    return {k: v for k, v in pairs if v is not None}


def spec(p):
    """The .sem syntax string, or the mapping form when the property carries descriptions."""
    if not (p.description or p.docs):
        return p.line().split(":", 1)[1].strip()
    return _clean((
        ("type", p.type), ("description", p.description), ("to", list(p.targets) or None),
        ("values", {x: p.docs.get(x) for x in p.enum} if p.enum else None), ("default", typed(p, p.default)),
        ("inherit", p.inherit or None), ("required", p.required or None), ("key", p.key or None)))


def typed(p, v):
    return int(v) if p is not None and p.type == "int" and re.fullmatch(r"-?\d+", str(v)) else v


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    return path


def _specs(defs):
    return {p.name: spec(p) for p in defs.values()}


def _schema_doc(m):
    etypes = {t.name: _clean((("description", t.description or None), ("extends", t.parent or None),
                              ("props", _specs(t.props) if t.props else None))) or None for t in m.etypes.values()}
    rels = {r.name: _clean((
        ("description", r.description), ("from", r.frm), ("to", r.to), ("attrs", _specs(r.attrs) or None),
        ("inverse", r.inverse), ("min_level", r.min_level), ("satisfied_by", r.satisfied_by or None),
        ("conflicts_with", r.conflicts or None), ("transitive", r.transitive or None), ("no_cycles", r.no_cycles or None)))
        for r in m.rtypes.values()}
    return {"kind": "Schema", "root": m.root_name, "levels": dict(sorted(m.levels.items())), "props": _specs(m.props),
            "rules": {k: v or True for k, v in m.rules.items()}, "entity_types": etypes, "relations": rels}


def _cap_doc(m, n):
    d = {"name": n.name, **({"id": n.uid} if n.uid else {})}
    if n.local:
        d["props"] = {k: typed(m.props.get(k), v) for k, v in n.local.items()}
    if n.children:
        d["children"] = [_cap_doc(m, c) for c in n.children]
    return d


def _entity_doc(m, e):
    defs = m.eprop_defs(e.type) if e.type in m.etypes else {}
    d = {"kind": "Entity", "type": e.type, "name": e.name, **({"id": e.uid} if e.uid else {})}
    if e.local:
        d["props"] = {k: typed(defs.get(k), v) for k, v in e.local.items()}
    rels = {}
    for r in e.rels:
        t = target_text(r)
        rels.setdefault(r["verb"], []).append({"target": t, **r["attrs"]} if r["attrs"] else t)
    if rels:
        d["relations"] = rels
    return d


def dump(m, outdir):
    """Write m as a YAML source tree: model.yaml, schema.yaml, capabilities/<L1>.yaml, entities/<name>.yaml."""
    at = lambda *p: os.path.join(outdir, *p)
    head = {"kind": "Model", **({"name": m.name} if m.name else {}),
            **({"version": m.version} if m.version else {})}
    out = [write(at("model.yaml"), {**head, "include": ["schema.yaml", "capabilities/*.yaml", "entities/*.yaml"]}),
           write(at("schema.yaml"), _schema_doc(m))]
    out += [write(at("capabilities", slug(top.name) + ".yaml"), {"kind": "Capability", **_cap_doc(m, top)}) for top in m.top.children]
    out += [write(at("entities", slug(e.name) + ".yaml"), _entity_doc(m, e)) for e in m.entities]
    return out


# ------------------------------------------------------------------ in-place edits (keep comments and layout)
def _lines(path):
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    return text, text.splitlines(keepends=True)


def _save(path, lines):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(lines))


def _eol(line):
    return "\r\n" if line.endswith("\r\n") else "\n"


def _get(mapping, key):
    for k, v in mapping.value:
        if isinstance(k, yaml.ScalarNode) and k.value == key:
            return k, v
    return None, None


def _scalar(mapping, key):
    """The text of the scalar under `key`, or None."""
    v = _get(mapping, key)[1]
    return v.value if isinstance(v, yaml.ScalarNode) else None


def _new_line(lines, k, v, make):
    """(index, line) of a new sibling line after `k: v` (the value may run over several lines);
    make(indent) is its text without the line ending."""
    end = v.end_mark
    last = end.line if end.column > 0 else end.line - 1
    row = k.start_mark.line
    return max(last, row) + 1, make(" " * k.start_mark.column) + _eol(lines[row])


def yaml_files(root):
    """(path, relative path) of every .yaml/.yml file under root in sorted order, skipping dot folders."""
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for fn in sorted(f for f in files if f.endswith((".yaml", ".yml"))):
            path = os.path.join(d, fn)
            yield path, os.path.relpath(path, root).replace(os.sep, "/")


def _id_targets(doc):
    """[(mapping node, label prefix)] for the objects of a Capability / Entity document, in tree order."""
    kind = _scalar(doc, "kind")
    out = []

    def walk(node):
        out.append((node, ""))
        kids = _get(node, "children")[1]
        for c in (kids.value if isinstance(kids, yaml.SequenceNode) else []):
            if isinstance(c, yaml.MappingNode):
                walk(c)
    if kind == "Entity":
        out.append((doc, "entity "))
    elif kind == "Capability":
        walk(doc)
    return out


def assign_ids(root, dry_run=False, new_id=None):
    """Write `id: <uuid>` next to the name of every capability and entity (in kind: Capability / Entity files) that has
    none. Edits the text in place, so comments and layout stay. Returns [(file, label, id)]."""
    import uuid
    new_id = new_id or (lambda: str(uuid.uuid4()))
    root, done = os.path.abspath(root), []
    for path, rel in yaml_files(root):
        text, lines = _lines(path)
        try:
            doc = yaml.compose(text)
        except yaml.YAMLError:
            continue
        if not isinstance(doc, yaml.MappingNode):
            continue
        inserts = []
        for node, label in _id_targets(doc):
            k, v = _get(node, "name")
            # a flow mapping `{name: X}` on one line is left alone; give it an id by hand
            if k is None or not isinstance(v, yaml.ScalarNode) or _get(node, "id")[0] is not None or node.flow_style:
                continue
            uid = new_id()
            inserts.append(_new_line(lines, k, v, lambda indent, uid=uid: f"{indent}id: {uid}"))
            done.append((rel, label + v.value, uid))
        if inserts and not dry_run:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += _eol(lines[0])
            for at, line in sorted(inserts, reverse=True):
                lines.insert(at, line)
            _save(path, lines)
    return done


def read_version(root):
    data = yaml.safe_load(open(os.path.join(root, "model.yaml"), encoding="utf-8")) or {}
    return _opt(data.get("version"))


def bump(old, how):
    """The version after `how` (major | minor | patch | an explicit x.y.z); ValueError if that is not possible."""
    if how in ("major", "minor", "patch"):
        if not old or not SEMVER_RE.match(old):
            raise ValueError(f"cannot bump '{old}'; set a version first (e.g. 1.0.0)")
        x, y, z = (int(v) for v in re.match(r"(\d+)\.(\d+)\.(\d+)", old).groups())
        return {"major": f"{x + 1}.0.0", "minor": f"{x}.{y + 1}.0", "patch": f"{x}.{y}.{z + 1}"}[how]
    if not SEMVER_RE.match(how):
        raise ValueError(f"'{how}' is not MAJOR.MINOR.PATCH (or major / minor / patch)")
    return how


def write_version(root, version):
    """Set `version:` in model.yaml, editing that one line (or adding it after `name:` / `kind:`)."""
    path = os.path.join(root, "model.yaml")
    text, lines = _lines(path)
    doc = yaml.compose(text)
    k, v = _get(doc, "version")
    if k is not None:
        i = k.start_mark.line
        lines[i] = lines[i][:k.start_mark.column] + f"version: {version}" + lines[i][v.end_mark.column:] if v.end_mark.line == i \
            else f"version: {version}{_eol(lines[i])}"
    else:
        k, v = _get(doc, "name")
        if k is None:
            k, v = _get(doc, "kind")
        at, line = _new_line(lines, k, v, lambda _: f"version: {version}")
        lines.insert(at, line)
    _save(path, lines)
