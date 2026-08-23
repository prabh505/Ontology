# `causalog.extraction.event_generator`

**Layer rank:** `L3`

## Single responsibility

Emit zero or more `Event` instances per evidence record (module 4).

## Forbidden dependencies

`graph_engine` and above; may never emit a causal edge. THIS IS THE LAW-EVENT BOUNDARY: no row, DataFrame, or CSV column may cross out of this package.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
