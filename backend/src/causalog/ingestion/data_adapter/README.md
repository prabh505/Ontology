# `causalog.ingestion.data_adapter`

**Layer rank:** `L2`

## Single responsibility

Read, validate, and reject raw source records (module 1).

## Forbidden dependencies

`extraction` and above; may never emit an `Event`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
