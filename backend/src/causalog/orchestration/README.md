# `causalog.orchestration`

**Layer rank:** `L9`

## Single responsibility

Compose a Run by wiring adapters into the reasoning pipeline.

## Forbidden dependencies

`api`. The only package permitted to import `causalog.persistence`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
