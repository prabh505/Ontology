# `causalog.causal_engine.confidence_scorer`

**Layer rank:** `L6`

## Single responsibility

Decompose edge support into named confidence components (module 10), and construct the
`CausalEdge` values that carry them.

## What it produces

`CausalGraph` — one `ScoredEdge` per `(source_event_id, target_event_id, edge_kind)`, each
holding a frozen `CausalEdge` with a `ConfidenceVector` of **eight** components, and a
`ComponentExplanation` per component saying in words and in arithmetic why that component
holds the value it holds. Beside it, a `ConfidenceReport` whose first section is what is
*not* calibrated.

## The eight components

`confidence_schema_version` **2.0.0**. Six are prd.md §49's; `evidence_diversity` and
`contradiction_freedom` are added by ADR-0052 because §49's list cannot express that
independent evidence beats repeated evidence, or that counter-evidence lowers a score.

| component | role | notes |
|---|---|---|
| `rule_support` | addend, 0.28 | noisy-OR over authored rule strengths |
| `historical_support` | addend, 0.17 | **lift**, not raw count; small samples discounted |
| `statistical_support` | addend, 0.17 | lift + effect size + sample size + explicit caveats |
| `evidence_diversity` | addend, 0.16 | distinct kinds and generators, not volume |
| `evidence_count` | addend, 0.12 | saturating volume |
| `graph_connectivity` | addend, 0.10 | **missing on every edge until module 7 exists** |
| `temporal_support` | **gate** | ceiling, not addend — unestablished precedence is a hard cap |
| `contradiction_freedom` | **gate** | ceiling; inverted name so every component rises with support |

## Rules this module holds

- **Never a bare float.** `CausalEdge.confidence` is a `ConfidenceVector`; the type refuses
  an empty component set. A confidence without components is a `LawViolationError`.
- **Never a skipped component.** Every edge carries all eight. A component whose data is
  absent is emitted at zero, marked `missing`, and counted — absence costs score rather
  than abstaining. `ComponentScorer.score` has no `None` return.
- **Never a count without its denominator.** `base_rates.py` computes the instance-level
  contingency table; a pattern present everywhere has lift 1.0 and scores zero.
- **Never "we didn't measure" shown as "this is weak."** `INSUFFICIENT_EVIDENCE` is a
  distinct outcome, gets no band, and is never promoted.
- **Never an invented band.** Thresholds and wording are declared in the rule pack
  (ADR-0053), never in engine or UI code.
- **Never a ranking.** `CausalGraph.edges` is sequenced canonically. Ranking is module 11's.

## Forbidden dependencies

Everything above L6. Owns the LAW-EVIDENCE gate; may never emit a bare float.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges),
`scripts/check_confidence_is_a_vector.py` (LAW-EVIDENCE), and
`scripts/check_domain_independence.py` (LAW-DOMAIN — one of DataCo's entity-type stems is
also the ordinary English word for temporal sequence, and it is banned vocabulary in a
reasoning package. So this package says "precedence" and "sequenced" throughout. This README
was itself rejected once for spelling the banned stem out, which is the lint working.)

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract; ADR-0052 for the aggregation strategy and ADR-0053 for the config split.
