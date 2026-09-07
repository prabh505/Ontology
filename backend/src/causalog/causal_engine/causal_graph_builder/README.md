# `causalog.causal_engine.causal_graph_builder`

**Layer rank:** `L6`

**Not one of the sixteen §36 modules.** prd.md §36 names no owner for §25 (the causal
graph), §26 (the edge taxonomy) or §31 (feedback loops). This package is that assembly step,
landed the way the ontology layer and the rule engine were (ADR-0054); OQ-025 records the
PRD gap. Modules 11 and 12 keep their numbers and consume this package's output.

## Single responsibility

Decide which of module 10's scored claims the engine will **assert**, type them, weight
them, look for feedback loops, and publish what the resulting graph does *not* contain.

## What it produces

| Artifact | Holds |
|---|---|
| `PromotedGraph` | the stated view (`PromotedEdge`), the rejection ledger (`DemotionRecord`), and the joint cause groups — all three of equal standing |
| `LoopDetectionResult` | classified circuits, with artifacts kept apart from findings |
| `GraphQualityReport` | counts, degrees, orphan effects, contradictions, and the `ASSUMED` share |

## What it does not do

- **It does not rank.** Sequencing is canonical `(source, target, kind)`, never by score.
  Ranking is module 11's, and a ranked artifact invites position to be read as a finding.
- **It does not score.** Every number about a claim's strength came from module 10.
- **It does not propose.** A pair nobody proposed is absent, and the report says so.
- **It does not resolve a disagreement.** A typing conflict between a rule and a payload, a
  contradictory promoted pair, a group whose membership exceeds the graph — all reported,
  none resolved (the ADR-0051 idiom).

## Rules this module holds

- **Promotion happens here and nowhere else.** `ProvenanceClass.INFERRED` appears in
  `policy.py` alone, asserted structurally by
  `tests/law/test_law_time_gates_every_promotion.py`.
- **LAW-TIME is re-verified at promotion, twice.** Explicitly against the two `Event`
  intervals — the check a stored `CausalEdge` cannot perform on itself, because it holds
  identifiers and not intervals (DEF-0002) — and again through `core.immutability.revise`,
  which re-runs the frozen type's `INFERRED ⇒ CERTAIN ∧ ¬temporally_unverifiable` invariant.
  Neither check is redundant: the first catches a stored verdict the data does not support,
  the second catches a promotion path that never consulted the first.
- **Inferred never overwrites observed.** Promotion is a revision of an already-inferred
  artifact; `revise` refuses an `OBSERVED` one outright, and every promoted edge stays scoped
  to its `run_id` while observed facts are scoped to `dataset_version` (ADR-0013).
- **Nothing is dropped.** `promoted + demoted == considered` is checked at construction, so a
  claim that went missing raises rather than being published as an absence.
- **Every threshold is a pack declaration.** No numeric comparison literal appears in
  `policy.py`, `select.py` or `weights.py`, and a test asserts it.
- **Absent means NOT RUNNABLE.** An undeclared policy is reported with its requirement, never
  defaulted and never reported as a clean zero (ADR-0049's rule, third application).

## Two design decisions worth reading before changing anything

**Cycles are detected over the event-TYPE projection, not over event instances.** At the
instance level a genuine loop is arithmetically impossible: a `CERTAIN` verdict is a strict
precedence relation, and strict precedence admits no cycle. Any instance-level circuit
therefore contains an
`UNDETERMINED` or unverifiable link and exists *because* precedence was unresolvable — so a
detector running there could only ever find artifacts. prd.md §31's loop closes across
process instances, which is what makes it a mechanism rather than a sorting error.

**Joint causes are promoted all-or-nothing.** A `CONTRIBUTING` group asserts that several
causes *jointly* produce an outcome and that none is sufficient alone. Promoting a subset
would tell module 13's counterfactual surgery and module 14's ranking that removing any one
member prevents the effect — the opposite of what the group says.

## Forbidden dependencies

| | Why |
|---|---|
| `causalog.ontology_runtime` | forbidden edge F3; the pack arrives as `core.ontology_view` values |
| `causalog.persistence.*` | forbidden edge F4; facts arrive by value through `GraphFacts` |
| any tabular library | forbidden edge F7; nothing below module 4 sees a row |
| `counterfactual_engine`, `recommendation_engine`, `explanation_engine`, `api` | forbidden edge F2 |
| domain vocabulary | LAW-DOMAIN; every type, kind and identifier is a string from a pack |

## Configuration

The rule pack's `graph_construction` namespace, at `rule_pack_schema_version` 1.3.0
(ADR-0055): `promotion_thresholds` (per edge kind), `competing_effect_policy`,
`competing_retain_count`, `diversity_credit_ceiling`, `magnitude_attributions`,
`weight_normalization`, `circuit_enumeration_cap`, `loop_minimum_participants`.

**Cycle classification is deliberately NOT configurable.** Whether a circuit resting on
unresolvable precedence is a discovery is not a domain judgement; if a pack could decide it,
"the engine detected a reinforcing loop" would mean two different things in two packs.
