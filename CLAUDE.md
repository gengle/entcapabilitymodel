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
python sem.py locate <id>        # capability/entity by full id or unique prefix (>= 4 hex digits): what it is + file:line
python sem.py ids [--dry-run]     # add `id: <uuid>` under each capability/entity that lacks one (text insert, keeps comments)
python sem.py version [major|minor|patch|x.y.z]   # show / bump / set model.yaml's version
python sem.py gen all out [--level N]   # or one of: site sql typeql jsonschema openapi mermaid csv (default level 3)
python sem.py yaml <folder>       # write the loaded model as a fresh YAML tree (converter from legacy .sem)
python server.py [--model model] [--port 8765]   # API + built viewer (web/dist)
cd web && npm run build           # tsc --noEmit + vite build; `npm run typecheck` for types only; `npm run dev` on :5173 proxies /api to :8765
```

`<ref>` is an entity name, a capability path (`Finance/Accounts Payable`), a unique capability name, an `id` (UUID), or a unique id prefix (`sem.locate`; the viewer's `#/id/<prefix>` route and `/api/locate` use the same rule). `SEM_MODEL` overrides the model (default: `./model/` if it exists, else `./model.sem`, relative to the cwd).

## Architecture

- **YAML format** (documented at the top of `semyaml.py`): files with `kind` (Model, Schema, Capability, Entity) are documents; files without one are fragments. `include:` (globs, relative to the file, must stay inside the model folder) adds included documents to the model and deep-merges included fragments into the including file first (mappings merge, lists append, includer wins on scalars). Capability documents can attach to an existing node with `parent:`. Entity relations are `{verb: [target | {target, attr: value}]}`; prop specs use the `.sem` syntax string (`enum(a,b) = a inherit required`) or a mapping `{type, description, values, default, inherit, required}` whose `values` may map each enum value to its meaning (`Prop.description`, `Prop.docs`; entity/relation types have `.description`). Field help in the viewer (`web/src/help.tsx`), `sem.py schema`, `diff` and the generators all read these; there is no other place for field documentation.
- **Reference props**: `type: ref, to: [User, Team]` (`.sem`: `ref(User,Team)`, `Prop.targets`) names an entity by name, id or a `key: true` prop such as a User's email, case-insensitive (`Model.ref`). Unresolved values are validation *warnings*; duplicate key values are errors. `sem.refs(m)` lists the resolved ones and feeds `edges()` (label `<prop>`, inverse `<prop>_of`), so `who`/`neighbors`/`path`, "Pointing here", `impact` (`referenced`) and graph outputs include them. The snapshot carries `PropVal.ref` (`ent:<name>` or null).
- **Version and ids**: `model.yaml` has `version` (`m.version`, MAJOR.MINOR.PATCH); every capability and entity has a UUID `id` (`n.uid` / `e.uid`, `uid` in the snapshot, since `id` there is the `cap:`/`ent:` route id). `validate_ids` (YAML models only) warns per file about missing ids and errors on malformed or duplicate ones. `semyaml.assign_ids` / `write_version` edit file text in place (via `yaml.compose` marks) so comments survive; `find_cap` and `entity` also match ids.
- **Provenance**: `semyaml.merge` tracks the source file of every value, so nodes/entities carry `src`, `prop_src`, and each relation `rel["src"]`. Load problems (bad YAML, missing includes, cycles, unknown keys) are collected in `m.load_errors` as `"file: msg"` and surface through `sem.validate`, never as exceptions. All scalar values are normalised to strings, as in the `.sem` loader.
- **Module passing**: `semyaml.load(path, S)` and `gen.run(S, ...)` receive the `sem` module as `S` instead of importing it, because `sem.py` runs as `__main__` and a second import would create distinct classes and break `isinstance` checks.
- **Load → link → validate** (`sem.py`): both loaders build the same `Model`; `Model.link()` resolves relation target text to capability `Node`s or `Entity`s; `validate()` returns `(errs, warns)`. The CLI edit commands go through `commit()`, which refuses YAML models; they and `save()` (which rewrites the whole file, dropping comments) only serve legacy `.sem` files.
- **Property resolution** (`Model.resolve`): local value → nearest ancestor (only if `inherit`) → root default. Entity props come from merging the type chain (`eprop_defs`).
- **Semantic rules live only in `sem.py`** (`validate`, `unmet`, `providers`): `min_level`, `satisfied_by` (a `requires` is met by an active entity that `exposes` it), `conflicts_with`, `no_cycles`, `no_active_under_retired`, retired entities not counting as providers.
- **Generators** (`gen.py`): `run(S, m, kind, outdir, level)` refuses to run if the model has errors. Add a generator by writing `gen_x(S, m, out, level)` and registering it in `GENS`. Everything is derived from model metadata. Output order follows load order (entity files sorted by name).
- **Server** (`server.py`): every request reloads the model from disk; `snapshot()` is the JSON contract mirrored by `web/src/types.ts` (keep them in sync). Preview loads with `overrides` (path → text, `None` = deleted) and writes nothing; PUT/DELETE reject (422) a change that adds validation errors unless `force`. The client polls `/api/version` (hash of YAML mtimes/sizes) for live reload.
- **Web** (`web/src`): `App.tsx` owns state — saved snapshot, per-file drafts, and a debounced preview snapshot built from all dirty drafts, which is what gets rendered. Hash routes `#/`, `#/schema`, `#/forms`, `#/file/<path>`, `#/ent/<name>`, `#/cap/<path>`; ids are `ent:<name>` / `cap:<path>`.
- **Form editing**: `forms.tsx` (entity/capability forms, Forms page) never writes files itself; it calls `ctx.mutate(path, edit)`, which applies a `yamledit.ts` edit to the draft text through the `yaml` Document API (comments and quoting kept), so the normal preview/save/422 flow applies. Only entries whose `src` is the file itself are editable; relation edits address the n-th own entry of a verb. `Field.tsx` renders one value with the control from `ui.ts`, which reads `model/ui.yaml` (`capability.<prop>`, `entity.<prop>`, `relation.<verb>.<attr>`). `ui.yaml` is not included by the model and `server.py` leaves it out of the file list. Server actions that write files (`POST /api/ids`, `POST /api/version`) go through `ctx.run`, which reloads drafts afterwards.
- The SQL output reproduces unmet/coverage/closure as views; JSON Schema and TypeQL do **not** enforce model rules, and TypeQL output is an untested draft.
- `out/` and `web/dist/` are generated; regenerate instead of hand-editing.
- **Changelog**: record every model or tooling change in `CHANGELOG.md` under the model version it ships in, and bump `model.yaml`'s version with `python sem.py version major|minor|patch` (rules at the top of the changelog).
- **Retirement impact**: `sem.impact(m, e)` is the single implementation; the CLI prints it, and `server.impact_json` puts it on every entity in the snapshot (`Ent.impact`).

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
