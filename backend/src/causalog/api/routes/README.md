# `causalog.api.routes`

**Layer rank:** `L10`

## Single responsibility

Declare HTTP endpoints per prd.md §53.

## Forbidden dependencies

`persistence`, `graph_engine`, `causal_engine` directly.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
