# `causalog.recommendation_engine`

**Layer rank:** `L7`

## Single responsibility

Rank interventions by benefit against cost (module 14).

## Forbidden dependencies

`explanation_engine`, `orchestration`, `api`; may never infer a cost.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
