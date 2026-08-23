# `causalog.graph_engine.state_engine`

**Layer rank:** `L4`

## Single responsibility

Derive `State` and `Transition` from events (module 6).

## Forbidden dependencies

`causal_engine` and above; may never invent a state absent from the ontology.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
