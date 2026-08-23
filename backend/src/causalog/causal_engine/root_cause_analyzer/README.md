# `causalog.causal_engine.root_cause_analyzer`

**Layer rank:** `L6`

## Single responsibility

Rank causes by impact averted and structural earliness (module 11).

## Forbidden dependencies

Everything above L6; may never create an edge.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
