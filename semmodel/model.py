import os, re

MODEL = os.environ.get("SEM_MODEL") or ("model" if os.path.isdir("model") else "model.sem")
PROP_RE = re.compile(r'^(\w+):\s*(\w+)(?:\(([^)]*)\))?(?:\s*=\s*("[^"]*"|\S+))?((?:\s+(?:inherit|required|key))*)\s*$')
REL_RE = re.compile(r'^(\w+)\s+(.+?)(?:\s*\[([^\]]*)\])?\s*$')
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def unq(v):
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fmt(v):
    return f'"{v}"' if re.search(r'[^\w.\-]', v) else v


class Prop:
    def __init__(self, name, typ, enum, default, inherit=False, required=False, targets=None, key=False):
        self.name, self.type, self.enum, self.default = name, typ, enum, default
        self.inherit, self.required = inherit, required
        self.targets = targets or []  # type ref: the entity types a value may point at (ref(User,Team))
        self.key = key                # the value identifies its entity, so a ref may use it (e.g. a User's email)
        self.description = None  # what the field means (YAML mapping form only; the .sem syntax has no room for it)
        self.docs = {}           # enum value -> what that value means

    def line(self):
        args = self.enum or (self.targets if self.type == "ref" else None)
        t = self.type + (f"({','.join(args)})" if args else "")
        return (f"{self.name}: {t}" + (f" = {fmt(self.default)}" if self.default is not None else "")
                + (" inherit" if self.inherit else "") + (" required" if self.required else "") + (" key" if self.key else ""))

    def coerce(self, raw):
        if self.type == "int":
            try:
                return int(raw)
            except ValueError:
                raise ValueError(f"{self.name}: '{raw}' is not an int")
        if self.type == "enum" and raw not in self.enum:
            raise ValueError(f"{self.name}: '{raw}' not in {{{', '.join(self.enum)}}}")
        return raw


def parse_prop(rest, ln=0):
    g = PROP_RE.match(rest.strip())
    if not g:
        raise ValueError(f"line {ln}: bad property '{rest}'")
    name, typ, enum, default, flags = g.groups()
    args = [x.strip() for x in enum.split(",")] if enum else None
    if typ == "ref" and not args:
        raise ValueError(f"line {ln}: property {name}: ref needs the entity types it may point at, e.g. ref(User,Team)")
    return Prop(name, typ, None if typ == "ref" else args, unq(default) if default else None,
                "inherit" in flags, "required" in flags, args if typ == "ref" else None, "key" in flags)


class Node:
    def __init__(self, name, parent=None):
        self.name, self.parent, self.children, self.local = name, parent, [], {}
        self.uid = None  # universal id (YAML `id`); stays the same when the capability is renamed or moved

    def path(self):
        parts, n = [], self
        while n.parent is not None:
            parts.append(n.name)
            n = n.parent
        return "/".join(reversed(parts))

    def level(self):
        return self.path().count("/") + 1

    def descendants(self):
        for c in self.children:
            yield c
            yield from c.descendants()


class Entity:
    def __init__(self, etype, name):
        self.type, self.name, self.local, self.rels = etype, name, {}, []
        self.uid = None  # universal id (YAML `id`)


class EType:
    def __init__(self, name, parent=None):
        self.name, self.parent, self.props = name, parent, {}
        self.description = None


class RType:
    def __init__(self, name):
        self.name, self.frm, self.to, self.attrs, self.inverse = name, [], [], {}, None
        self.min_level, self.satisfied_by, self.conflicts = None, [], []
        self.transitive = self.no_cycles = False
        self.description = None


class Model:
    def __init__(self):
        self.root_name, self.levels, self.props, self.rules = "Capability", {}, {}, {}
        self.etypes, self.rtypes, self.entities, self.top = {}, {}, [], Node("")
        self.name = self.version = None  # from model.yaml (YAML models only)

    # ---- capability tree
    def all_nodes(self):
        out, stack = [], list(reversed(self.top.children))
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(reversed(n.children))
        return out

    def find(self, path):
        n = self.top
        for part in [p for p in path.split("/") if p]:
            n = next((c for c in n.children if c.name.lower() == part.lower()), None)
            if n is None:
                return None
        return n if n is not self.top else None

    def find_cap(self, text):
        low = text.lower()
        n = self.find(text) or next((x for x in self.all_nodes() if x.uid and x.uid.lower() == low), None)
        if n:
            return n, None
        hits = [x for x in self.all_nodes() if x.name.lower() == low] if "/" not in text else []
        if len(hits) == 1:
            return hits[0], None
        if hits:
            return None, f"'{text}' is ambiguous: " + ", ".join(h.path() for h in hits)
        return None, f"no such capability '{text}'"

    def depth_limit(self):
        return len(self.levels) if self.levels else 99

    def lvname(self, n):
        return f"L{n.level()} {self.levels.get(n.level(), '')}".strip()

    def resolve(self, node, p):
        if p.name in node.local:
            return p.coerce(node.local[p.name]), "local"
        if p.inherit:
            a = node.parent
            while a is not None and a.parent is not None:
                if p.name in a.local:
                    return p.coerce(a.local[p.name]), f"inherited from {a.path()}"
                a = a.parent
        if p.default is not None:
            return p.coerce(p.default), "root default"
        return None, "unset"

    # ---- entities and types
    def entity(self, name):
        return next((e for e in self.entities if e.name.lower() == name.lower()), None) or \
            next((e for e in self.entities if e.uid and e.uid.lower() == name.lower()), None)

    def chain(self, t):
        out = []
        while t and t in self.etypes and t not in out:
            out.append(t)
            t = self.etypes[t].parent
        return out

    def eprop_defs(self, t):
        d = {}
        for name in reversed(self.chain(t)):
            d.update(self.etypes[name].props)
        return d

    def conforms(self, t, names):
        return "*" in names or any(x in names for x in self.chain(t))

    def ref(self, p, value):
        """The entity a ref prop's value points at: an entity of one of p.targets whose name, id or a `key` prop
        (e.g. a User's email) equals the value, ignoring case. None when it matches nothing (or p is not a ref)."""
        if value is None or p is None or p.type != "ref":
            return None
        v = str(value).strip().lower()
        for e in self.entities:
            if not self.conforms(e.type, p.targets):
                continue
            if e.name.lower() == v or (e.uid or "").lower() == v:
                return e
            if any(d.key and str(e.local.get(k, "")).lower() == v for k, d in self.eprop_defs(e.type).items()):
                return e
        return None

    def ref_keys(self, p):
        """How a ref prop's value may name its entity, for messages: name, id and the targets' key props."""
        keys = {k for t in self.etypes if self.conforms(t, p.targets) for k, d in self.eprop_defs(t).items() if d.key}
        return ", ".join(["name", "id", *sorted(keys)])

    def link(self):
        for e in self.entities:
            for r in e.rels:
                rt = self.rtypes.get(r["verb"])
                if rt is None:
                    r["target"], r["err"] = None, f"unknown relation '{r['verb']}' (defined: {', '.join(self.rtypes) or 'none'})"
                else:
                    r["target"], r["err"] = self.resolve_target(rt, r["text"])

    def resolve_target(self, rt, text):
        err = None
        if "Capability" in rt.to or "*" in rt.to:
            n, err = self.find_cap(text)
            if n:
                return n, None
        e = self.entity(text)
        if e:
            return e, None
        return None, err or f"no such {'/'.join(rt.to)} '{text}'"


def target_text(r):
    t = r["target"]
    return t.path() if isinstance(t, Node) else (t.name if t is not None else r["text"])
