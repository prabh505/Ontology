# `causalog.graph_engine.temporal_graph_builder`

**Layer rank:** `L4`

## Single responsibility

Project observed events, states, and relationships into the temporal graph (module 8).

## Forbidden dependencies

`causal_engine` and above. Writes `PRECEDES`, never `CAUSES` (prd.md §44).

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
