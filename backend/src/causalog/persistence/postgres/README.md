# `causalog.persistence.postgres`

**Layer rank:** none — this package is a driven adapter, not a layer.

## Single responsibility

Implement fact storage and the append-only audit against the system of record.

## Forbidden dependencies

Every reasoning package.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
