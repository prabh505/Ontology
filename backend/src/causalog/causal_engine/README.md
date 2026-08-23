# `causalog.causal_engine`

**Layer rank:** `L6`

## Single responsibility

Produce scored causal structure from the observed temporal graph.

## Forbidden dependencies

`counterfactual_engine`, `recommendation_engine`, `explanation_engine`, `orchestration`, `api`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
