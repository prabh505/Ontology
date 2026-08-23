# `causalog.graph_engine`

**Layer rank:** `L4`

## Single responsibility

Assemble observed structure into the Temporal Property Graph.

## Forbidden dependencies

`rule_engine`, `causal_engine`, and everything above. May never write a `CAUSES` edge.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
