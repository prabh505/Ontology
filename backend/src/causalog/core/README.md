# `causalog.core`

**Layer rank:** `L0`

## Single responsibility

Declare the canonical types every layer computes over.

## Forbidden dependencies

Every project-local package. `core/` imports the standard library and the data-validation base only (CONVENTIONS.md §6, §12).

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
