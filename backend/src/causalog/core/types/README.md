# `causalog.core.types`

**Layer rank:** `L0`

## Single responsibility

Declare the five canonical entities plus provenance, time, and confidence structures.

## Forbidden dependencies

Every project-local package outside `core/`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
