# `causalog.persistence`

**Layer rank:** none — this package is a driven adapter, not a layer.

## Single responsibility

Implement the `core/ports` capabilities against Postgres, Neo4j, and Redis.

## Contents

| Package | Implements |
|---|---|
| `postgres/` | `FactRepository`, `BulkFactWriter`, `AuditSink`, `SchemaMigrator` — the system of record |
| `neo4j/` | `GraphProjection` — the derived, rebuildable graph |
| `redis/` | `DerivedCache` — recomputable values only |
| `memory/` | In-memory fakes of all four, so the unit suite runs with no services |
| `sources/` | `SourceReader` implementations — extension seam 1; empty until module 1 |

The realised schema, the graph model, and the boundary rule are `docs/data-model.md`.

## Forbidden dependencies

Every reasoning package. Imported only by `orchestration` (forbidden edge F4). A package
importing *itself* is not a forbidden edge — "a package may import its own layer" — and
`scripts/check_layers.py` once got that wrong here, the same way it once got it wrong for
`ontology_runtime`; both now carry a `MUST_ACCEPT` self-test case.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`. Note that
`persistence` is deliberately **outside** LAW-DOMAIN's scan: a `SourceReader` must name the
real columns of a real dataset, and that is domain vocabulary doing its job.

See `docs/architecture.md` §1 for the full layer map and §3 for the storage boundary.
