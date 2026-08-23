# `causalog.graph_engine.relationship_resolver`

**Layer rank:** `L4`

## Single responsibility

Resolve structural `Relationship` instances between entities (module 7).

## Forbidden dependencies

`causal_engine` and above; structural relationships are never causal edges.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
