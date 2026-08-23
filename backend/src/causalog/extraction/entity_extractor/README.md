# `causalog.extraction.entity_extractor`

**Layer rank:** `L3`

## Single responsibility

Derive `Entity` instances from mapped records (module 3).

## Forbidden dependencies

`graph_engine` and above; may never derive an `Event`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
