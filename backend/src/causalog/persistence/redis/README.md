# `causalog.persistence.redis`

**Layer rank:** none — this package is a driven adapter, not a layer.

## Single responsibility

Cache recomputable derived values keyed by `run_id`.

## Forbidden dependencies

Every reasoning package. May never be a source of truth.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
