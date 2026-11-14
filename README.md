# Dynamic semantic model (sem.py + gen.py)
Model file `model.sem` is the single source of truth. It defines capability levels/props, entity types (is-a),
and relation types (domain/range, attrs, inverse, min_level, satisfied_by, conflicts_with, transitive, no_cycles).
Every edit is validated and rejected atomically. Generators read the model, so schema changes flow through.

    python3 sem.py tree | schema | validate | show X | neighbors X | closure X rel | path A B | who X | gaps | coverage | impact E
    python3 sem.py add "Finance/AP/New thing" -p | entity add Type Name k=v | link E relation Target [k=v]
    python3 sem.py type add Database Asset | type prop Database "engine: string" | relation add hosted_on Application Database inverse=hosts
    python3 sem.py gen all out [--level 2]     # site sql typeql jsonschema openapi mermaid csv

Notes: TypeQL output is an untested draft. The model-level rules (min_level, cycles, satisfied_by) live in sem.py; SQL views
reproduce unmet/coverage/closure, but generated JSON Schema/TypeQL do not enforce them.
