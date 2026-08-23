# `causalog.graph_engine.timeline_builder`

**Layer rank:** `L4`

## Single responsibility

Group events into per-process sequenced timelines (module 5).

## Forbidden dependencies

`causal_engine` and above; timeline adjacency is sequence, never causation.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
