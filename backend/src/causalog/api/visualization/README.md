# `causalog.api.visualization`

**Layer rank:** `L10`

## Single responsibility

Shape graph and timeline payloads for the six workspaces (module 16, prd.md §51).

## Forbidden dependencies

`persistence`, `graph_engine` directly.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
