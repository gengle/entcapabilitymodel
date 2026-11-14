# Changelog

Changes to the model (`model/`) and to the tooling around it (CLI, generators, server, viewer).
Each release is named after the model version in `model/model.yaml` (`python sem.py version`).

Bump rules: **major** when a change can break existing model files or consumers of the generated output (a removed
or renamed type, property or relation type; a stricter rule), **minor** for additions (new types, properties,
relation types, entities, capabilities, features), **patch** for fixes and changes that don't alter meaning.

## [2.1.0] - 2026-11-14

### Added
- Locate by id. A full id or a unique prefix of at least 4 hex digits (case, hyphens and braces ignored, so the short
  `d54cfb4b` the viewer shows works) finds the capability or entity:
  - `python sem.py locate <id>` prints what it is and `file:line`, e.g.
    `capability L4 Technology/Security/Access Management/Single Sign-On` / `capabilities/technology.yaml:15`.
    Several matches are all listed; no match exits 1.
  - Every CLI command that takes a `<ref>` (`show`, `who`, `neighbors`, `impact`, ...) also accepts an id prefix.
  - `GET /api/locate?id=<id or prefix>` returns the matches with their route id, file and line.
  - Viewer: `#/id/<id or prefix>` opens the object (a shareable link that survives renames), or lists the matches
    when the prefix is ambiguous. Pasting an id into the sidebar filter shows the matching objects whichever tab is
    open.
- `docs/database-targets.md`: research into graph, document and semantic-web databases as further generator targets,
  with a recommendation (RDF/OWL+SHACL, then Cypher, then GraphQL SDL; bring the TypeQL draft up to TypeDB 3).

## [2.0.0] - 2026-11-14

Major: `owner` and `head` change type, and the model now has validation warnings, so `validate --strict` fails until
the existing values are fixed (see below).

### Added
- Reference properties. `type: ref` with `to: [<entity types>]` (in the `.sem` syntax `ref(User,Team)`) holds a
  value that names an entity of one of those types by its **name**, its **id**, or a **key** property, ignoring case.
  `key: true` marks such a property; key values must be unique (a duplicate is an error).
- A value that names no such entity is a **warning**: "owner 'CFO Office' is not a known User or Team (match by name,
  id, email)".
- Viewer:
  - A reference value is a link to the entity; a name given by email or id shows the entity's name with the value
    after it.
  - A value that matches nothing is flagged "not a known User or Team".
  - In the edit form the field is a combo box suggesting the entities it may point at, and the line under it links
    the entity.
  - The referenced entity's "Pointing here" lists who refers to it (e.g. Greg Engle: `owner_of` ConfigService).
  - Its retirement impact lists them too ("owner of …", needs follow-up).
- References count as links everywhere relations do: `sem.py who`, `neighbors`, `path` and `impact`, the generated
  `graph.json`, and links on the static site's pages.

### Changed
- `owner` on capabilities and on assets (applications and services) is now `ref` to `User` or `Team`. `head` on teams
  is now `ref` to `User`. A User's `email` is a `key`, so `owner: greg.engle@outlook.com` or
  `owner: 296ee66b-3cd3-466d-94d1-4ab2bfb185a7` both resolve to Greg Engle.
- The edit form's default control for a `ref` field is a combo box (`ui.yaml` may choose `text` instead).

### Needs fixing (10 warnings)
These existing values don't name an entity yet. Fix each by creating the Team or User or by pointing it at an
existing one:
- Capabilities: `CFO Office` (Finance), `CHRO Office` (Human Resources), `CIO Office` (Technology), `Dana Reyes`
  (Finance/Accounts Payable).
- Entities: `Dana Reyes` (AP Operations head), `Finance IT` (ApproveIt, Match Engine and SAP S/4, through the
  `finance-it` fragment), `Identity Team` (Corporate SSO, PAM Vault).

## [1.4.0] - 2026-11-14

### Added
- White space is explained where it appears:
  - The coverage badges (covered / overlap / white space) explain themselves on hover.
  - A white-space capability's "Provided by" section says what the gap means and what to do about it.
  - The Overview legend has the same explanations.
  - The Schema page has a new **Coverage** section: which levels get a status, which relation provides, and what
    each status means.
- **Add a provider** on every capability that gets a coverage status. Pick an entity and the viewer adds e.g.
  `exposes: [Interview Scheduling]` to that entity's own file as an unsaved draft. The page previews the result at
  once (the badge turns to covered), and the new provider is listed with **Save** and **Discard** buttons for that
  file. Entities that already provide the capability aren't offered. Retired entities, and entities whose existing
  relation conflicts with it (e.g. they `requires` it), are shown disabled. The normal save check applies: a change
  that would add validation errors is refused, with a notice.

### Internal
- App context: `mutateFile(path, edit)` edits any file, loading it as a draft first, and `saveFile(path)` saves a
  file that isn't the open one. A refused save of a file other than the open one now shows a notice, since the
  refusal banner only appears in the open file's editor.

## [1.3.2] - 2026-11-14

### Added
- **Cancel** button in the edit form, next to Save. It discards the file's unsaved changes (form edits and typed edits
  alike, the same as the editor's Revert) and leaves edit mode. With nothing unsaved it just leaves edit mode.

### Internal
- `revert(path)` is on the model context and backs both Cancel and the editor's Revert button.

## [1.3.1] - 2026-11-14

### Changed
- Field help no longer uses a **?** button, which read as part of the name (`owner*?`). The field name itself opens
  the help when the schema documents it: it has a dotted underline, and hovering it shows the help.
- Under each field the viewer now shows the value that applies when nothing is set here and where it comes from:
  "CIO Office inherited from Technology" (a link to that capability), "180 default from the schema", or
  "active default from the Asset type". An enum value's meaning follows it.
- Form labels align with the top of their control instead of floating in the middle of a tall row.

## [1.3.0] - 2026-11-14

### Added
- Field documentation in the schema. A property in mapping form takes a `description`, and its `values` can map each
  enum value to what it means (`values: {low: ..., medium: ..., high: ...}`). Entity types and relation types take a
  `description`. The mapping form now rejects unknown keys and a `default` that isn't one of the values.
- Descriptions for every capability property, entity type, entity property, relation type and relation attribute, and
  a meaning for every enum value (`model/schema/*.yaml`). For example `criticality = high`: an outage stops core
  operations within hours and needs a recovery plan, tested failover and named on-call support.
- Viewer help:
  - A **?** next to each field in the property tables and edit forms opens the field's description and every value's
    meaning, with the current value highlighted and the default marked.
  - The meaning of the value that applies is shown under it, labelled *inherited* or *default* when it isn't set
    locally.
  - Dropdown options, radio buttons and relation attributes show value meanings on hover; entity types and relation
    types show their description on hover.
  - The Schema page has a "meaning" column for capability properties, and lists each entity type's and relation
    type's description, field descriptions and value meanings.
- `sem.py schema` prints the descriptions and value meanings.
- Generators:
  - **jsonschema / openapi:** `description` on properties, entity types and relations; `x-enumDescriptions` next to
    `enum`.
  - **site:** descriptions and value meanings on capability, entity and schema pages.
  - **sql:** a `description` column on `entity_type` and `relation_type`, new `property` and `property_value` tables,
    and comments for the capability columns.
  - **typeql:** description comments.

### Changed
- `sem.py diff` now compares the capability property schema and all descriptions; before, it compared neither.
- `sem.py yaml` writes documented props in mapping form so the docs survive a round trip.

## [1.2.0] - 2026-11-14

### Added
- Entity type `User` (`model/schema/entity-types.yaml`) with `email` (string, required) and `lifecycle`
  (plan / active / retire, default active).
- Entity `Greg Engle` (`model/entities/greg-engle.yaml`), a `User`.
- `CHANGELOG.md`.

### Changed
- Retirement impact redesigned. The viewer's entity page now always shows a **Retirement impact** section instead of
  a "What breaks if X is retired?" button. It opens with a verdict (safe to retire / needs follow-up / breaks the model
  / already retired) and a one-line summary, then lists only what applies: the capabilities the entity provides
  (marked "sole provider" or "also by …"), any other capabilities left uncovered, requirements left unmet (hard or
  soft), and dependents through transitive relations, with hop counts.
- The impact is part of each entity in the snapshot (`Ent.impact`), so it follows unsaved drafts like the rest of the
  page, instead of being fetched separately from the saved files.
- Capabilities left without a provider are now counted only at or above the coverage level, matching `coverage` and
  the white-space status, rather than also listing their L1/L2 ancestors.
- `python sem.py impact <Entity>` prints the same verdict and sections.

### Internal
- One `sem.impact(m, e)` now backs both the CLI and the server (`server.impact_json`); the copies in `cmd_impact`
  and `server.impact` and a leftover no-op check in `cmd_impact` are gone. `GET /api/impact` returns the new shape
  plus `entity`.

## [1.1.0] and earlier

Before this file existed. See the git history: YAML model sources and the live viewer (`f90752e`), form editing,
model version and universal ids (`38165dc`).
