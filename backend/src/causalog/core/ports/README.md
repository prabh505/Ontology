# `causalog.core.ports`

**Layer rank:** `L0`

## Single responsibility

Declare the abstract capabilities the reasoning layers require from infrastructure.

## Forbidden dependencies

Every concrete adapter; a port may never import `causalog.persistence`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
