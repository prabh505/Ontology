# `causalog.causal_engine.propagation_analyzer`

**Layer rank:** `L6` · **Module 12** · Status `built-unverified`

## Single responsibility

Measure how an effect spreads through the causal graph.

## What it produces

| Artifact | What it holds |
|---|---|
| `PropagationTree` | one seed's consequences, each at its shortest depth, with its attributed magnitude, its route confidence, its participants and its process instances |
| `ConsequenceSet` | the membership the magnitude is combined over — keyed by identifier and validated unique, which is the no-double-counting guarantee held by a type |
| `PathConfidence` | belief about one route: the composed value, the function that composed it, the length-sensitive product beside it, and the per-link inputs |
| `TruncationRecord` | every place the walk stopped early, with what was on the frontier |
| `PropagationReport` | the seven prd.md §30 measures, none of them combined, and the account of what was not measured |

## What it does not do

- **It creates no link.** `CausalEdge` is never constructed here and `ProvenanceClass.INFERRED` is never assigned here. Asserted over the AST by `tests/law/test_ranking_never_collapses.py`.
- **It ranks nothing.** The tree is sequenced by depth and identifier, canonically and deliberately not by consequence. Ranking is module 11's.
- **It recomputes no domain metric.** Every magnitude is a walk of an ontology-declared operator tree through `core.measurement`. No formula appears anywhere in the package.
- **It never reports an absence as a zero.** A consequence whose measurement could not be evaluated carries a reason and is excluded from the total, and the total says how many members it rests on.

## Rules this module holds

**Depth and breadth are two measures and are never averaged.** One figure combining them would rise for two unrelated reasons and could not tell a deep narrow chain from a shallow wide fan-out.

**A magnitude belongs to a node, never to a route.** A consequence reachable four ways is one consequence. `route_count` is reported as structure and multiplies nothing.

**A chain is only as strong as its weakest link.** Composition is a named function in `causalog.core.composition`; the default is the minimum and the argument for it is written out there in four parts. The length-sensitive product is carried beside it in its own column and the two are never blended.

**A bound that was reached is truncation, and truncation is printed above the numbers.** A traversal that stopped has measured the first part of propagation, not propagation, and every figure it produced is a lower bound.

**A reinforcing loop is a requirement, not a defect** (prd.md §31). A circuit terminates its route, is recorded, and the traversal continues.

## Two standings, and why the second exists

The traversal walks a `GraphView`. `STATED` is the promoted graph and its findings are the engine's. `UNPROMOTED_DIAGNOSTIC` is module 10's scored graph before the promotion decision, and everything derived from it is disowned by the type that carries it, refused `INFERRED` by a validator, and printed under a fixed notice held as a property so no revision can soften it.

It exists because on the committed bounded run **the stated graph is empty** — 0 of 9,492 claims promoted, 79.3% of them stopped by the temporal verdict rather than by any threshold. A strict traversal answers every question with silence, and silence is a true answer that shows a reader nothing about whether the machinery works. See `view.py` for the four structural mechanisms that keep the second standing from contaminating the first.

## Forbidden dependencies

| Forbidden | Why |
|---|---|
| Everything above `L6` | the one-directional rule (`docs/architecture.md` §1) |
| `ontology_runtime` | forbidden edge F3 — the pack arrives already flattened into `core.ontology_view` values |
| `causalog.persistence` | forbidden edge F4 — the cache arrives as an injected `DerivedCache` protocol value |
| Creating a `CausalEdge` | the Causal Graph Builder's, and only `causal_graph_builder/policy.py` may assign `INFERRED` |
| Ranking | module 11's |

Enforced by `scripts/check_layers.py` and `scripts/check_domain_independence.py`.

## Every parameter is declared, none is a literal

`maximum_depth`, `traversal_node_cap`, the combination operator per measurement, and the composition function name are all read from the pack's `propagation_analysis` block (`rule_pack_schema_version` 1.5.0). An absent declaration means the policy **cannot run**, is reported as a `PolicyGap` naming what it would have needed, and is never defaulted (ADR-0049).

The one number written in code is `MAX_PROPAGATION_DEPTH`, and it is a ceiling rather than a default: past it a walk over a graph that should be acyclic is evidence that it is not, and continuing would be looping rather than measuring. A pack that declares nothing gets no traversal — never this number.

See `docs/architecture.md` §1 for the layer map and §2 for this package's module contract.
