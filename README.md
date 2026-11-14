# Dynamic semantic model (sem.py + semyaml.py + gen.py + server.py)
The model lives in `model/` as YAML and is the single source of truth. It defines capability levels/props, entity types (is-a),
relation types (domain/range, attrs, inverse, min_level, satisfied_by, conflicts_with, transitive, no_cycles), the capability
tree, and one file per entity. Generators read the model, so schema changes flow through. Needs Python 3 with PyYAML.

## Model files
Every file is a mapping. A file with `kind` is a document; a file without one is a fragment.

    model.yaml                        kind: Model       include: [schema/*.yaml, capabilities/*.yaml, entities/*.yaml]
    schema/*.yaml                     kind: Schema      root, levels, props, rules, entity_types, relations
    capabilities/finance.yaml         kind: Capability  name, props, children: [{name, props, children}]
    capabilities/finance/*.yaml       kind: Capability  parent: Finance  (attaches a subtree to an existing node)
    entities/sap-s4.yaml              kind: Entity      type, name, props, relations: {exposes: [Payment Run, {target: Budgeting, coverage: partial}]}
    fragments/finance-it.yaml         (no kind)         props: {owner: Finance IT}

`include:` takes a path or a list (globs allowed), relative to the file. Included documents join the model; included fragments
are merged into the including file first: mappings merge, lists append, the including file wins on scalars. Props are written
`"enum(low,medium,high) = medium inherit required"` or as `{type, values, default, inherit, required}`. Relation targets are an
entity name, a capability path, or a unique capability name.

## CLI

    python sem.py tree | schema | validate [--strict] | show X | neighbors X | closure X rel | path A B | who X | gaps | coverage | impact E
    python sem.py gen all out [--level 2]     # site sql typeql jsonschema openapi mermaid csv
    python sem.py yaml <folder>               # write any model (e.g. an old .sem file via SEM_MODEL) as a YAML tree
    python sem.py diff <old> <new>            # each side a .sem file, a model folder or a model.yaml

The edit commands (add, set, entity, link, type, relation) only work on legacy `.sem` files; a YAML model is edited in its
files or in the viewer.

## Viewer

    cd web && npm install && npm run build && cd ..
    python server.py                          # http://127.0.0.1:8765  (--model <folder>, --port N)

Browse files, the capability tree and entities; edit YAML with a live preview of the rendered model and its validation; saves
that would add validation errors are rejected unless forced; external file changes reload automatically. For frontend work run
`python server.py` and `npm run dev` in `web/` (http://localhost:5173, proxies /api).

Notes: TypeQL output is an untested draft. The model-level rules (min_level, cycles, satisfied_by) live in sem.py; SQL views
reproduce unmet/coverage/closure, but generated JSON Schema/TypeQL do not enforce them.
