# `causalog.graph_engine.state_engine`

**Layer rank:** `L4`

## Single responsibility

Derive `State` and `Transition` from events (module 6).

## What it produces

`State` and `Transition` values plus a `StateQualityReport` -- illegal-transition
findings (with the offending event named, never silently skipped), assumed-initial-state
and uncertain-boundary counts, and duration statistics for every pack-declared
`DURATION`/`DELAY` measurement. An illegal transition stops that entity's replay at the
offending event and is reported; it never aborts the whole run and never corrects itself
into a legal shape.

## Forbidden dependencies

`causal_engine` and above; may never invent a state absent from the ontology.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
