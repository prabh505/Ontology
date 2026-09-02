# `causalog.extraction.event_generator`

**Layer rank:** `L3`

## Single responsibility

Emit zero or more `Event` instances per evidence record (module 4).

## What it produces

`Event` values and an `EventQualityReport` — counts by type and provenance class, timestamp
precision, orphans, and process coverage. The report is a first-class output: the causal
engine's honesty depends on knowing what the log does not contain.

## Forbidden dependencies

`graph_engine` and above; may never emit a causal edge. THIS IS THE LAW-EVENT BOUNDARY: no
row, DataFrame, mapped record or CSV column may cross out of this package.

**No code path here may name a provenance class.** An emitted event takes the class its
ontology event type declares, and the pack refuses `OBSERVED` on a derived type (ADR-0029),
so a heuristic has no route to an observed event. Asserted over the AST by
`tests/law/test_derived_events_are_never_observed.py`.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
