# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A dependency-free (stdlib only) Python tool for a self-describing semantic model: a capability tree (L1–L4), typed entities with is-a inheritance, and declared relation types. `model.sem` is the single source of truth; `sem.py` is the CLI (parse, validate, edit, navigate) and `gen.py` derives all outputs in `out/` from it.

## Commands

On this Windows machine use `python`, not `python3` (`python3` resolves to the Microsoft Store stub). There is no test suite, linter or build step; `validate` is the check.

```
python sem.py validate            # errors -> exit 1; warnings printed but exit 0
python sem.py validate --strict   # warnings also fail (currently fails: ApproveIt requires Privileged Access, which nothing exposes)
python sem.py tree | schema | show <ref> | neighbors <ref> | closure <ref> <rel> | path A B | who <ref> | gaps | coverage | impact <Entity>
python sem.py diff old.sem new.sem
python sem.py gen all out [--level N]   # or one of: site sql typeql jsonschema openapi mermaid csv (default level 3)
```

`<ref>` is an entity name, a capability path (`Finance/Accounts Payable`), or a unique capability name. Set `SEM_MODEL` to operate on a different model file (default `./model.sem` relative to the cwd).

## Architecture

- **`model.sem` format** – indentation-based. Sections: `root` (levels, inheritable props, rules), `entity_type X : Parent` (props), `relation` (`from`/`to` type unions, `attr`, `inverse`, `min_level`, `satisfied_by`, `conflicts_with`, `transitive`, `no_cycles`), nested `capability` blocks with `set k = v`, and `entity <Type> <Name>` blocks whose lines are `<relation> <target> [k=v]`. Prop syntax: `name: type[(enum,vals)] [= default] [inherit] [required]`.
- **Load → link → validate → save** (`sem.py`): `load()` parses into `Model`; `Model.link()` resolves relation target text to capability `Node`s or `Entity`s; `validate()` returns `(errs, warns)`. Every edit command goes through `commit()`, which validates and either rejects the whole change (model untouched) or calls `save()`.
- **`save()` regenerates `model.sem` from scratch** in canonical order. Edits made via the CLI drop comments and hand formatting; edit the file directly if you need to preserve them.
- **Property resolution** (`Model.resolve`): local value → nearest ancestor (only if `inherit`) → root default. Entity props come from merging the type chain (`eprop_defs`).
- **Semantic rules live only in `sem.py`** (`validate`, `unmet`, `providers`): `min_level`, `satisfied_by` (a `requires` is met by an active entity that `exposes` it), `conflicts_with`, `no_cycles`, `no_active_under_retired`, retired entities not counting as providers.
- **Generators** (`gen.py`): `run(S, m, kind, outdir, level)` gets the `sem` module passed in as `S` (to avoid a circular import) and refuses to run if the model has errors. Add a generator by writing `gen_x(S, m, out, level)` and registering it in `GENS`. Everything is derived from the model's metadata, so new types/relations/props flow through without generator changes.
- The SQL output reproduces unmet/coverage/closure as views; JSON Schema and TypeQL do **not** enforce model rules, and TypeQL output is an untested draft.
- `out/` is generated; regenerate it instead of hand-editing.
