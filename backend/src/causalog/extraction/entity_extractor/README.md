# `causalog.extraction.entity_extractor`

**Layer rank:** `L3`

## Single responsibility

Derive `Entity` instances from mapped records (module 3).

## What it produces

`Entity` values sequenced by `entity_id`, their attribute history as a separate artifact, and
a `ReconciliationReport` stating what was created, merged and conflicted.

## Forbidden dependencies

`graph_engine` and above; may never derive an `Event`. **May never merge two entities on a
similarity heuristic** — identity is the content address or it is not identity
(`docs/architecture.md` §2). Attribute history is a separate artifact rather than a field on
`Entity`, because the entity's address excludes its attributes so that enriching one cannot
rename it (`docs/contracts.md` §5).

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
