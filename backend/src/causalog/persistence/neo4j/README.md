# `causalog.persistence.neo4j`

**Layer rank:** none — this package is a driven adapter, not a layer.

## Single responsibility

Implement the derived, rebuildable graph projection.

## Contents

| Module | Role |
|---|---|
| `schema.py` | prd.md §47 labels and types, their constraints and indexes |
| `cypher.py` | Every statement as a named constant; explicit Cypher, no builder |
| `projection.py` | `GraphProjection`: the six-step rebuild, the drift surface, `drop_run` |

## The two edge families

The load-bearing distinction. **Observed** (`PRECEDES`, `BELONGS_TO`, `LOCATED_AT`,
`TRANSITIONS_TO`, `PART_OF`) carry `dataset_version` and never `run_id`. **Inferred**
(`CAUSES`, `AFFECTS`, `BLOCKS`, `AMPLIFIES`, `REDUCES`, `RECOMMENDS`) carry `run_id` under an
existence constraint. So dropping one run's inferences is *incapable* of touching observed
structure, and `PRECEDES` — which is temporal order, never causation — cannot be confused
with `CAUSES` by any query that scopes itself.

## Forbidden dependencies

Every reasoning package. **May never hold a fact that has no Postgres row** (ADR-0001) — the
rebuild's verification step exists to catch exactly that, and it runs before any swap.

**Forbidden behaviours:** being asked which version it is serving (PostgreSQL is asked);
repairing a drifted projection (it is rebuilt); computing a value the system of record
cannot reproduce.

See `docs/data-model.md` §6 for the graph model and the mapping from canonical types.
