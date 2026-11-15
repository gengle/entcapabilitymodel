# Python refactor plan

Goal: make the Python code smaller, simpler and reusable **without changing behaviour**.

## Why

| Measure (before) | Value |
|---|---|
| Python lines (`sem.py`, `semyaml.py`, `gen.py`, `server.py`) | 2,475 |
| `sem.py` | 1,193 lines in one file: data model, validation rules, `.sem` loader/saver, every CLI command |
| Longest functions | `validate` 155, `main` 145, `load_sem` 83, `gen_sql` 72, `gen_site.tree` 63, `gen_typeql` 56, `assign_ids` 52, `server.issue` 51, `semyaml.load` 48 |
| Module wiring | `semyaml.load(path, S)` and `gen.run(S, ...)` take the `sem` module as a parameter, because `sem.py` runs as `__main__` and a second import would create duplicate classes |
| Duplicated helpers | `slug` (gen, semyaml), `sval`/`names`/`unq`/`fmt` string coercion, repeated "load model or exit" and print patterns in `cmd_*` |

Root cause of the weak reuse: everything lives in the entry-point script, so nothing else can import it.

## Target layout

```
sem.py            thin entry point + facade: re-exports every public name, `python sem.py ...` still works
semyaml.py        facade/loader (kept at top level; other tools import it)
gen.py, server.py keep their top-level names
semmodel/         new package: the code that used to live in sem.py
  model.py        Prop, Node, Entity, EType, RType, Model, parse_prop (data + resolution, no printing)
  rules.py        providers/unmet/edges/refs/adjacency/validate/impact/locate (semantic rules, pure functions)
  legacy.py       .sem loader/saver and the CLI edit commands
  cli.py          commands + dispatch table (output only)
```

Because the classes live in the package, they exist once whoever imports them; the "pass the `sem` module around" wiring
can go.

## Rules for every step

1. **Behaviour must not change.** The check is the golden snapshot:
   `python <scratchpad>/golden.py check <scratchpad>/baseline` (run from the repo root) must print `IDENTICAL`. It
   covers every CLI command, a deliberately broken model, the legacy `.sem` model, all generator output at levels 2 and
   3, the server snapshot / impact / preview JSON and the ids/version editing. It uses its own frozen model copy.
2. **Public names stay.** Anything another module, the web client (`web/src/types.ts` mirrors `server.snapshot()`),
   `CLAUDE.md` or the README names must keep its name, arguments and return shape until the last phase.
3. **Simplify, don't golf.** Fewer lines by removing duplication, splitting long functions into named steps and using
   data-driven tables. Not by cramming. Keep comments that explain *why*; docstrings stay short.
4. No new dependencies (standard library + PyYAML).
5. Each agent edits only the files it owns.

## Phases

**Phase 1 (one agent, sequential): split `sem.py` into the package.** Pure move. `sem.py` keeps re-exporting every
public name so `sem.X` and `S.X` still resolve. Golden check passes.

**Phase 2 (five agents in parallel, one git worktree each, disjoint files):**

| Agent | Owns | Targets |
|---|---|---|
| A rules | `semmodel/model.py`, `semmodel/rules.py` | `validate` (155 lines) becomes a list of small rule functions; shared lookups; `Model` helpers deduplicated |
| B cli | `semmodel/cli.py`, `semmodel/legacy.py` | `main` (145) becomes a dispatch table; shared "load, resolve ref, print" helpers; `load_sem` / `save` simplified |
| C loader | `semyaml.py` | `load` (48), `schema` (35), `prop` (32), `assign_ids` (52); one string-coercion helper set; text-editing helpers shared |
| D generators | `gen.py` | shared emit/format helpers; `gen_sql` (72), `gen_typeql` (56), `gen_site.tree` (63) split into steps; common iteration over props/types written once |
| E server | `server.py` | `snapshot` builders, `issue` (51) and the handler routing become tables; shared JSON helpers |

Each agent commits on its own worktree branch; I merge them (files are disjoint) and re-run the golden check.

**Phase 3 (one agent): integrate.** Remove the module-passing (`S`) parameters now that the classes can be imported
directly, move the helpers still duplicated across files into one place, update `CLAUDE.md` / README, rebuild
`out/` and check it is unchanged, final golden check, line and function-size report.

## Definition of done

- Golden check `IDENTICAL`; `python sem.py validate --strict` clean; web `npm run build` clean; `out/` regenerates
  to the same files.
- `validate` and `main` no longer exceed ~40 lines; no function over ~60 lines without a reason noted.
- Total Python lines noticeably below 2,475 with the same features.
- `CLAUDE.md` architecture notes describe the new layout.

## Result (phase 3)

- The `S` (sem module) parameters and `semmodel.model.facade()` are gone: `semyaml.load(path, overrides=None)`, `gen.run(m, kind, outdir, level)`, `gen_x(m, out, level)`. `sem.py` is a 6-line entry point; `server.py` imports `semmodel.rules` / `semmodel.model` directly.
- One home per helper: `slug` (model), `bump` (semyaml, next to `read_version`/`write_version`), `dependency`, `directly_provides`, `reach` (rules; the closure command and `impact` shared a BFS), `yaml_files` (semyaml; the server used a copy), `_after`/`_new_line` merged, `validate_ids` registered directly as a rule.
- Python lines 2,880 -> about 2,820 (2,475 before the whole refactor). The remaining code has little duplication left; reaching ~2,300 would need dropping the two-blank-lines-between-top-level-definitions convention (about 200 lines) or features.
- Golden check IDENTICAL after every step. `tools` that called `semyaml.load(path, sem)` must drop the second argument.
