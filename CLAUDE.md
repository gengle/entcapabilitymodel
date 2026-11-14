# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python tool (stdlib + PyYAML) for a self-describing semantic model: a capability tree (L1–L4), typed entities with is-a inheritance, and declared relation types. The source of truth is the YAML tree in `model/` (entry `model/model.yaml`). `semyaml.py` loads it, `sem.py` is the CLI (validate, navigate, generate), `gen.py` derives everything in `out/`, and `server.py` + `web/` (Vite + React + TypeScript) are a live viewer/editor.

## Commands

On this Windows machine use `python`, not `python3` (`python3` resolves to the Microsoft Store stub). There is no test suite or linter; `validate` and the web typecheck are the checks.

```
python sem.py validate            # errors -> exit 1; warnings printed but exit 0
python sem.py validate --strict   # warnings also fail
python sem.py tree | schema | show <ref> | neighbors <ref> | closure <ref> <rel> | path A B | who <ref> | gaps | coverage | impact <Entity>
python sem.py diff <old> <new>    # either side: .sem file, model folder or model.yaml; compares semantics, not order
python sem.py gen all out [--level N]   # or one of: site sql typeql jsonschema openapi mermaid csv (default level 3)
python sem.py yaml <folder>       # write the loaded model as a fresh YAML tree (converter from legacy .sem)
python server.py [--model model] [--port 8765]   # API + built viewer (web/dist)
cd web && npm run build           # tsc --noEmit + vite build; `npm run typecheck` for types only; `npm run dev` on :5173 proxies /api to :8765
```

`<ref>` is an entity name, a capability path (`Finance/Accounts Payable`), or a unique capability name. `SEM_MODEL` overrides the model (default: `./model/` if it exists, else `./model.sem`, relative to the cwd).

## Architecture

- **YAML format** (documented at the top of `semyaml.py`): files with `kind` (Model, Schema, Capability, Entity) are documents; files without one are fragments. `include:` (globs, relative to the file, must stay inside the model folder) adds included documents to the model and deep-merges included fragments into the including file first (mappings merge, lists append, includer wins on scalars). Capability documents can attach to an existing node with `parent:`. Entity relations are `{verb: [target | {target, attr: value}]}`; prop specs use the `.sem` syntax string (`enum(a,b) = a inherit required`) or a mapping.
- **Provenance**: `semyaml.merge` tracks the source file of every value, so nodes/entities carry `src`, `prop_src`, and each relation `rel["src"]`. Load problems (bad YAML, missing includes, cycles, unknown keys) are collected in `m.load_errors` as `"file: msg"` and surface through `sem.validate`, never as exceptions. All scalar values are normalised to strings, as in the `.sem` loader.
- **Module passing**: `semyaml.load(path, S)` and `gen.run(S, ...)` receive the `sem` module as `S` instead of importing it, because `sem.py` runs as `__main__` and a second import would create distinct classes and break `isinstance` checks.
- **Load → link → validate** (`sem.py`): both loaders build the same `Model`; `Model.link()` resolves relation target text to capability `Node`s or `Entity`s; `validate()` returns `(errs, warns)`. The CLI edit commands go through `commit()`, which refuses YAML models; they and `save()` (which rewrites the whole file, dropping comments) only serve legacy `.sem` files.
- **Property resolution** (`Model.resolve`): local value → nearest ancestor (only if `inherit`) → root default. Entity props come from merging the type chain (`eprop_defs`).
- **Semantic rules live only in `sem.py`** (`validate`, `unmet`, `providers`): `min_level`, `satisfied_by` (a `requires` is met by an active entity that `exposes` it), `conflicts_with`, `no_cycles`, `no_active_under_retired`, retired entities not counting as providers.
- **Generators** (`gen.py`): `run(S, m, kind, outdir, level)` refuses to run if the model has errors. Add a generator by writing `gen_x(S, m, out, level)` and registering it in `GENS`. Everything is derived from model metadata. Output order follows load order (entity files sorted by name).
- **Server** (`server.py`): every request reloads the model from disk; `snapshot()` is the JSON contract mirrored by `web/src/types.ts` (keep them in sync). Preview loads with `overrides` (path → text, `None` = deleted) and writes nothing; PUT/DELETE reject (422) a change that adds validation errors unless `force`. The client polls `/api/version` (hash of YAML mtimes/sizes) for live reload.
- **Web** (`web/src`): `App.tsx` owns state — saved snapshot, per-file drafts, and a debounced preview snapshot built from all dirty drafts, which is what gets rendered. Hash routes `#/`, `#/schema`, `#/file/<path>`, `#/ent/<name>`, `#/cap/<path>`; ids are `ent:<name>` / `cap:<path>`.
- The SQL output reproduces unmet/coverage/closure as views; JSON Schema and TypeQL do **not** enforce model rules, and TypeQL output is an untested draft.
- `out/` and `web/dist/` are generated; regenerate instead of hand-editing.

<!-- hippo:start -->
## Project Memory (Hippo)

The installed UserPromptSubmit hook injects pinned rules and the memories
that match each prompt, so never load them yourself. If no hippo memory
block has appeared in this session, run this at the start of a task:
```bash
hippo context --auto --budget 1500
```

The installed hooks store failed tool calls and capture the session when it
ends, so there is nothing to record or run by hand.
<!-- hippo:end -->
