# Developer Dynamic Semantic Model

The model lives in `model/` as YAML and is the single source of truth. It defines capability levels/props, entity types (is-a),
relation types (domain/range, attrs, inverse, min_level, satisfied_by, conflicts_with, transitive, no_cycles), the capability
tree, and one file per entity. Generators read the model, so schema changes flow through. Needs Python 3 with PyYAML.

## Model files
Every file is a mapping. A file with `kind` is a document; a file without one is a fragment.

    model.yaml                        kind: Model       name, version: 1.0.0, include: [schema/*.yaml, capabilities/*.yaml, entities/*.yaml]
    schema/*.yaml                     kind: Schema      root, levels, props, rules, entity_types, relations
    capabilities/finance.yaml         kind: Capability  name, id, props, children: [{name, id, props, children}]
    capabilities/finance/*.yaml       kind: Capability  parent: Finance  (attaches a subtree to an existing node)
    entities/sap-s4.yaml              kind: Entity      type, name, id, props, relations: {exposes: [Payment Run, {target: Budgeting, coverage: partial}]}
    fragments/finance-it.yaml         (no kind)         props: {owner: Finance IT}

`include:` takes a path or a list (globs allowed), relative to the file. Included documents join the model; included fragments
are merged into the including file first: mappings merge, lists append, the including file wins on scalars. Props are written
`"enum(low,medium,high) = medium inherit required"` or as `{type, description, values, default, inherit, required}`, where
`values` is a list or a mapping of value -> meaning (only the mapping form can carry a `description` and value meanings;
entity types and relation types take a `description` too). The viewer shows them as field help and the generators carry them.
A `ref` prop (`{type: ref, to: [User, Team]}` or `"ref(User,Team)"`) points at an entity by its name, id or a `key: true`
prop such as a User's email; the viewer links it, and a value that names no such entity is a validation warning. Relation targets are an
entity name, a capability path, a unique capability name, or an `id`.

Every capability and entity carries a universal `id` (a UUID) that stays the same through renames and moves; validation
reports a missing id as a warning and a malformed or duplicate one as an error. The model's `version` (MAJOR.MINOR.PATCH)
is stamped into the SQL, CSV and OpenAPI output.

## Insurance enterprise example

The model includes an illustrative insurance enterprise capability map spanning product, distribution, underwriting,
policy administration, billing, claims, reinsurance, and enterprise management. Existing finance, human resources and
technology capabilities remain alongside it. `Insurance Architecture` is a placeholder owner, not a real organization.
Most new capabilities intentionally have no provider; coverage gaps show where an organization can map its own teams
and systems. The example operations team and policy platform demonstrate provider and dependency links only.

The insurance schema in `model/schema/insurance-entity-types.yaml` and `model/schema/insurance-relations.yaml` models
parties, products, coverages, submissions, quotes, policies, risks, claims, billing and reinsurance as typed entities
and relationships. Files named `model/entities/example-*.yaml` contain fictional records. For example:

    python sem.py show "Example Commercial Property Policy"
    python sem.py neighbors "Example Warehouse Claim"
    python sem.py path "Example Warehouse Claim" "Example Commercial Property Product"

The vocabulary is insurance-domain inspired, **not an implementation of or a conformance claim to ACORD**. Coverage
concepts are shared by products and policies; `PolicyCoverage` illustrates policy-specific limits, deductibles and
insured risks. The model validates declared types, relationship endpoints and basic properties, but not required
relationship cardinalities, cross-link consistency, insurance contract rules, dates, currency amounts, jurisdictional
requirements or ACORD messages.
It is a starting point for tailoring, not a complete carrier operating model or a production transaction schema.

## CLI

    python sem.py tree | schema | validate [--strict] | show X | neighbors X | closure X rel | path A B | who X | gaps | coverage | impact E
    python sem.py gen all out [--level 2]     # site sql typeql jsonschema openapi mermaid csv
    python sem.py yaml <folder>               # write any model (e.g. an old .sem file via SEM_MODEL) as a YAML tree
    python sem.py diff <old> <new>            # each side a .sem file, a model folder or a model.yaml
    python sem.py ids [--dry-run]             # write `id: <uuid>` under every capability/entity that has none
    python sem.py version [major|minor|patch|1.2.0]   # show, bump or set model.yaml's version

The edit commands (add, set, entity, link, type, relation) only work on legacy `.sem` files; a YAML model is edited in its
files or in the viewer.

## Viewer

    cd web && npm install && npm run build && cd ..
    python server.py                          # http://127.0.0.1:8765  (--model <folder>, --port N)

Browse files, the capability tree and entities; edit YAML with a live preview of the rendered model and its validation; saves
that would add validation errors are rejected unless forced; external file changes reload automatically.

**Capability map** in the top navigation presents a print-friendly enterprise map. Choose a domain and depth, optionally
show coverage, then use **Print / Save PDF**. It follows the live preview, including unsaved edits; verify the preview
before printing. Browser print settings control paper size, orientation and PDF output.

**Edit form** (on any entity or capability) edits it without touching YAML: name, type, properties, relations (targets
come from drop-downs limited to what the relation type allows, attributes get their own controls), and child
capabilities. Form edits rewrite the file's draft keeping comments, so they preview and save like typed edits. Values and
relations merged in from a fragment are shown read-only (a value set in the form overrides it). New entities and child
capabilities get an `id` automatically; **Assign ids** on the Overview fills in missing ones, and the model.yaml page
sets or bumps the version.

**Forms** (top bar) chooses the control for each field: text box, multi-line text, text with suggestions, number box,
slider, drop-down or radio buttons. Enum fields default to a drop-down; a drop-down or radio buttons on a non-enum field
take a list of choices (e.g. `review_cycle_days` offers 30/60/90/180/365). The choices are saved in `model/ui.yaml`, which
nothing includes, so it never affects the model or its validation. For frontend work run
`python server.py` and `npm run dev` in `web/` (http://localhost:5173, proxies /api).

Notes: TypeQL output is an untested draft. The model-level rules (min_level, cycles, satisfied_by) live in semmodel/rules.py; SQL views
reproduce unmet/coverage/closure, but generated JSON Schema/TypeQL do not enforce them.
