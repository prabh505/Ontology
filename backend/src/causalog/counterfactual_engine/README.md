# `causalog.counterfactual_engine`

**Layer rank:** `L7`

## Single responsibility

Simulate hypothetical worlds by graph surgery over frozen edges (module 13).

## Forbidden dependencies

`recommendation_engine`, `explanation_engine`, `orchestration`, `api`. May NEVER write to the base world.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
