# Generator targets: graph, document and semantic-web databases

Research from 2026-11-14 (model 2.1.0). Statuses were checked by web search on that date (sources at the end). Nothing
here is implemented yet. A new target is a `gen_x(S, m, out, level)` in `gen.py`, registered in `GENS`.

Existing targets: static site, SQLite SQL (views for unmet / coverage / closure), TypeQL (draft), JSON Schema,
OpenAPI, Mermaid, CSV.

## Comparison

| Option | Kind | Status / licence | Fit | Rules it can enforce itself | Effort |
|---|---|---|---|---|---|
| **RDF + OWL + SHACL** (Turtle; Jena Fuseki, GraphDB, Oxigraph) | Semantic web | W3C standards. Jena is Apache 2.0. GraphDB is now Graphwise, with a free edition. Oxigraph has no SHACL in its core. | Excellent. Is-a → `rdfs:subClassOf`; tree → `skos:broader`; relation types → `owl:ObjectProperty` with `owl:inverseOf` and `owl:TransitiveProperty`; enums with meanings → SKOS concept schemes; UUIDs → `urn:uuid:` IRIs; version → `owl:versionInfo`. Relation attributes need RDF 1.2 triple terms or a link node. | The most of any option (SHACL): enums, cardinality, datatypes, the class of a ref, `min_level`; `satisfied_by`, `conflicts_with`, `no_active_under_retired` and `no_cycles` as SHACL-SPARQL. Closure, coverage and unmet requirements as SPARQL queries. | Medium |
| **Cypher**: Neo4j, Memgraph, FalkorDB, Neptune openCypher | Property graph | Neo4j Community is GPLv3 (several constraint types are Enterprise-only); Memgraph is BSL; FalkorDB is SSPL. | Very good. Stacked labels for is-a; attributes on relationships; `PARENT_OF` edges for the tree. Edges are one-way, so inverse names are lost; enums and meanings can only live in a metadata subgraph. | Unique ids (all editions); existence, type and key constraints on Neo4j Enterprise. Everything else as queries (`-[:DEPENDS_ON*]->`). | Low |
| **GraphQL SDL** | API schema | Specification | Good. Interfaces for the type chain; enums with descriptions; unions for ref props (`User \| Team`); edge types for relation attributes. | The type system only | Low |
| **TypeDB 3** (TypeQL) | Typed hypergraph | Active (3.x, Rust rewrite). Licence not verified. | Closest semantic match: relations that carry attributes, `sub` inheritance, roles. | `@key`, `@unique`, `@card`, `@values` (enums), `@range`, `@abstract`; functions for closure and unmet requirements. | Low–medium (fix the draft) |
| **Apache AGE** (Cypher in Postgres) | Property graph | Apache 2.0 | Good, but one label per vertex, so is-a needs a property. | Weak (hand-written Postgres constraints) | Low–medium |
| **SurrealDB** | Multi-model | BSL 1.1 → Apache 2.0 after 4 years; 3.0 in Feb 2026 | Good: schema-full tables, typed `record<user\|team>` refs, `RELATE` edges with fields. | `ASSERT` (enums), field types | Medium |
| **ArangoDB** | Document + graph | BSL 1.1; free Community use is non-commercial and capped | Good: edge collections with attributes. | Per-collection JSON Schema validation | Medium |
| **MongoDB** (`$jsonSchema`) | Document | SSPL | Fair: refs by id, no graph semantics. | Enums, required fields, types. Closure via `$graphLookup`. | Low (reuses JSON Schema) |
| **TinkerPop / Gremlin**: JanusGraph, Neptune, Cosmos DB | Property graph | JanusGraph active; Cosmos Gremlin de-emphasised in favour of Fabric | Medium: imperative load scripts, no schema file. | JanusGraph's management API only | Medium |
| **Kùzu forks** (LadybugDB, RyuGraph) | Embedded graph | Kùzu archived 2025-10-10; forks are young | Strong typed DDL, no inheritance | Typed schema, primary keys | Low–medium |

## Recommendation

1. **RDF / OWL + SHACL** (`ontology.ttl`, `shapes.ttl`, `data.ttl`, `queries.rq`).
   - It's the only target that is both interoperable (IRIs, SKOS, OWL) and able to enforce most of `validate()` portably: any SHACL engine (Jena, pySHACL, GraphDB) can check the data.
   - The Turtle can be written with the standard library alone.
   - It serves architecture, knowledge-graph and governance teams.
   - The one awkward part is relation attributes (use RDF 1.2 triple terms or a link node).
2. **Cypher** (`constraints.cypher`, `load.cypher`, `queries.cypher`).
   - One generator reaches the largest graph-database audience: Neo4j, Memgraph, FalkorDB, AGE with small tweaks, and Neptune.
   - `MERGE` makes loading repeatable.
   - `queries.cypher` would port the SQL views: unmet, coverage, closure and cycle checks.
   - It can enforce little but takes the least effort.
3. **GraphQL SDL** (`schema.graphql`): for API and front-end consumers, next to the OpenAPI output. Low effort.

Runner-up: **bring the TypeQL draft up to TypeDB 3** (below). TypeDB fits the model best and can enforce enums and
cardinality natively.

## The existing TypeQL draft

- **Syntax:** the schema already uses TypeDB 3 syntax (`attribute x, value string`, `entity x sub y`, `integer`).
- **Relation inserts** read `insert depends_on(source: $s, target: $t) has depends_on_criticality "high";`. TypeDB 3 may need a variable and commas there (`$r isa depends_on, links (...), has ...`). *Not verified against a server.*
- **Attributes are global,** so two entity types with a same-named prop of different types would collide.
- **3.x features not used yet:** `@values` for enums, `@doc`, `@abstract`, `@card`, `@unique` on ids, and functions for transitive `depends_on`, unmet requirements and coverage.
- **Integers:** the research suggested they are quoted. They are not (`has review_cycle_days 90`).
- **Effort:** about half a day to a day, plus a test against a TypeDB 3 container.

## Avoid

- **Archived or end-of-life:**
  - Kùzu (archived; the forks are young).
  - RedisGraph (end of life; FalkorDB is the successor).
  - Gel/EdgeDB (the team joined Vercel and Gel Cloud shut down on 2026-01-31).
- **Uncertain future:**
  - Dgraph (ownership has changed twice).
  - Cosmos DB Gremlin (de-emphasised).
- **Licences to flag to users** (fine as generator targets): SSPL for FalkorDB and MongoDB; BSL for Memgraph, ArangoDB and SurrealDB.
- **ISO GQL:** engines don't share a portable GQL dialect yet, so emit Cypher rather than "GQL".
- **Also worth knowing:** LinkML (YAML schemas that generate OWL, SHACL, JSON Schema, GraphQL and SQL) is a useful reference design or interop export.

## Sources

**Kùzu and forks**
- https://www.theregister.com/2025/10/14/kuzudb_abandoned/
- https://oneuptime.com/blog/post/2026-08-12-kuzu-archived-pin-0-11-3-fork-or-migrate/view
- https://github.com/predictable-labs/ryugraph

**Dgraph**
- https://www.istaridigital.com/resources/istari-acquires-dgraph
- https://discuss.dgraph.io/t/dgraph-new-chapter/20020

**Gel (EdgeDB)**
- https://vercel.com/blog/investing-in-the-python-ecosystem
- https://www.geldata.com/blog

**FalkorDB / RedisGraph**
- https://docs.falkordb.com/References/license.html
- https://redis.io/blog/redisgraph-eol/

**Neo4j**
- https://neo4j.com/docs/cypher-manual/25/schema/constraints/
- https://neo4j.com/licensing/
- https://neo4j.com/blog/developer/graph-type-schema-enforcement-made-easy-preview/

**ISO GQL**
- https://www.wikipedia.org/wiki/ISO/IEC_39075

**Memgraph**
- https://github.com/memgraph/memgraph

**Apache AGE**
- https://age.incubator.apache.org/download

**SurrealDB**
- https://surrealdb.com/license.md
- https://surrealdb.com/blog/introducing-surrealdb-3-0-the-future-of-ai-agent-memory

**ArangoDB**
- https://en.wikipedia.org/wiki/ArangoDB

**JanusGraph**
- https://docs.janusgraph.org/changelog

**Cosmos DB Gremlin**
- https://learn.microsoft.com/azure/cosmos-db/gremlin/faq

**TypeDB**
- https://typedb.com/docs/reference/typedb-2-vs-3/diff/index.md
- https://typedb.com/docs/typeql-reference/annotations/
- https://typedb.com/docs/typeql-reference/functions/functions-vs-rules/

**Jena SHACL**
- https://jena.apache.org/documentation/shacl/

**GraphDB (Graphwise)**
- https://graphwise.ai/?p=166320
