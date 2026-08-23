# `causalog.persistence`

**Layer rank:** none — this package is a driven adapter, not a layer.

## Single responsibility

Implement the `core/ports` capabilities against Postgres, Neo4j, and Redis.

## Forbidden dependencies

Every reasoning package. Imported only by `orchestration`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
