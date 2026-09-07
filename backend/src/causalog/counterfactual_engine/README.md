# `causalog.counterfactual_engine`

**Layer rank:** `L7` · **Module 13** · Status `built-unverified`

## Single responsibility

Simulate hypothetical worlds by graph surgery over frozen links, and say what the answer is
worth (prd.md §33, ADR-0065).

## What it produces

| Artifact | What it holds |
|---|---|
| `SimulatedWorld` | One hypothetical: the changes that made it, every occurrence it reached in that world's terms, and the diff against the world that happened. Addressed `sim:digest(base_graph_id \| mutations)`. |
| `WorldDiff` / `EventDelta` | The comparison, occurrence by occurrence, with the unchanged and reached counts beside it so a list of changes always has a denominator. |
| `RejectedIntervention` | One change the engine refused, the declaration it was checked against, and why. Of equal standing to the world. |
| `ValidityAssessment` | The support envelope per moved quantity, the extrapolation verdict, the sensitivity sweep, the enumerated assumptions, and the belief composed along the links the change travelled. |
| `CounterfactualReport` | All of it, rendered for a person and for a machine from one object. |

## What it does not do

- **It never writes to the base world.** Nothing here holds an `Event` it could modify, and
  `core.immutability.revise` is never called on a base-world artifact
  (`tests/law/test_simulation_never_writes_back.py`, asserted over the AST).
- **It never states a causal claim.** No `CausalEdge` is constructed and `INFERRED` is never
  assigned (same law test). `causal_graph_builder/policy.py` is the engine's one promotion
  site.
- **It never produces a non-`SIMULATED` value.** `SimulatedWorld` refuses any other class at
  construction.
- **It never predicts.** Every statement is about a world that did not happen, in the past
  conditional (`tests/counterfactual/`).
- **It never simulates a world the ontology does not admit.** See below.

## Rules this module holds

**A contributing cause removed reduces the outcome; it does not prevent it.** Elimination is
a re-reachability question -- does anything still transmit into this consequence -- and
reduction is what is left when some causes stop and others do not. They are computed
separately, held in separate fields, counted separately, and never summed. This is the single
most common counterfactual error, and merging the two produces a confident wrong answer with
every downstream check passing.

**A joint cause group is removed as a unit, never member by member.** ADR-0061, and
`JointCauseGroup`'s own note names this module.

**An impossible premise is refused, never simulated and flagged.** A change is validated
against the declared lifecycle, the declared process sequences and the declared changeable
attributes before anything propagates, and LAW-TIME is re-checked over the moved bounds. A
hypothetical is not an exemption from LAW-TIME. Every check after an unreachable premise
passes on it, so the refusal has to happen at the boundary.

**An absent declaration refuses; it never permits.** Whether an attribute could have been set
differently is a claim about the domain, read from the pack and never decided here
(ADR-0067). No declaration means no attribute change is admissible on that kind of
occurrence, reported as a `PolicyGap`.

**No instant moves without a measurement saying it was computed.** The graph declares no
transfer function for time. A consequence is re-timed exactly when module 1's
`DerivedPrecedence` says the source COMPUTED its instant from one the change moved, and
everything else is reported as `NOT_RETIMED` rather than silently left alone.

**An extrapolation verdict replaces the figure; it does not sit beside it.** A number a
reader can quote without its warning is a number that will be quoted without its warning.

**Nothing here is calibrated, and the artifact says so first.** `NOT_CALIBRATED_NOTICE` is
the report's opening section. A decomposed, envelope-checked, sensitivity-swept figure is
more persuasive than a bare one and is not more accurate -- risk R-23.

## Two standings, and why one is refused by default

`propagation_analyzer/view.py` states in fixed text that a diagnostic graph "is not an input
to simulation or to recommendation", and OQ-026 requires this module to refuse one. It does,
by default. A caller may opt in explicitly with `accept_unpromoted=True`, because on the
committed slice the stated graph is empty (R-22) and a strict run demonstrates nothing about
the machinery. Everything produced under the opt-in is disowned: the report carries
`DIAGNOSTIC_NOT_STATED_NOTICE`, imported from module 12 rather than restated, and the two are
written to separate files that nothing merges. This module never names
`UNPROMOTED_DIAGNOSTIC`; it compares against `STATED`, so module 12 keeps the engine's only
construction site of that member.

## Forbidden dependencies

| Forbidden | Why |
|---|---|
| `ontology_runtime` | **F3.** Declarations arrive already flattened as `core.ontology_view` values via `extraction.ontology_adapters`. |
| `causalog.persistence.*` | **F4.** The derived cache arrives as the `core.ports.persistence.DerivedCache` protocol; `None` means recompute. |
| `explanation_engine`, `orchestration`, `api` | **F2.** Higher ranks. |
| `recommendation_engine` | Same rank, and still forbidden: module 14 consumes a `SimulatedWorld`, so an edge back would be circular. |
| `pandas`, `csv`, `numpy`, … | **F7.** The LAW-EVENT boundary at import level. |
| Any domain vocabulary | **LAW-DOMAIN.** This README is scanned too. |

Enforced by `scripts/check_layers.py` and `scripts/check_domain_independence.py`.

## Every parameter is declared, none is a literal

`maximum_simulation_depth`, `affected_subgraph_node_cap`, `support_envelope_tolerance`,
`sensitivity_perturbations` and `path_composition` all come from the pack's
`counterfactual_simulation` block at `rule_pack_schema_version` 1.6.0 (ADR-0071). An absent
declaration means the policy **cannot run**, is reported as a `PolicyGap` naming what it
would have needed, and is never defaulted (ADR-0049). The only in-code number is
`MAX_SIMULATION_DEPTH`, a ceiling that bounds a declaration rather than substituting for one.

See `docs/architecture.md` §1 for the layer map and §2 for this package's module contract.
