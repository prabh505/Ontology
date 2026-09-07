# CONTEXT.md — Project CausaLog

> **Canonical living state.** This file is the single authoritative answer to "where is
> this project right now." It is optimized to be read by an AI at session start.
> `docs/prd.md` is the truth about *intent*. `docs/architecture.md` is the truth about
> *structure*. This file is the truth about *state*.
> The code is the truth about what *is* (see `HANDOFF.md`).

---

## 0. IF YOU ARE A NEW AI SESSION, READ THIS FIRST

```
STOP. Do not write code yet.

1. Read, in full, in this order:
      CONTEXT.md      (this file)      — state
      CONVENTIONS.md                   — rules you may not break
      DECISIONS.md                     — decisions already made; do not re-litigate
      PROGRESS.md                      — what exists and what its evidence was
   Then read only the prd.md sections relevant to the task you were given.

2. Summarize in <=10 bullets: current phase, last completed module, open risks,
   and any constraint that applies to today's task.

3. Only then accept the module prompt.

HARD RULES FOR EVERY SESSION:
 - Do not invent requirements. If the PRD is silent, STOP and ask, or record the
   gap in section 8 (Open Questions) with a proposed default.
 - Do not expand scope. See section 10 (Deferred / Out-of-Scope).
 - Do not add ML where rules suffice. V1 intelligence comes from architecture.
 - Do not modify files outside the module you were told to build.
 - If you must deviate from a prior decision, write an ADR in DECISIONS.md FIRST.
 - Update CONTEXT.md / PROGRESS.md / DECISIONS.md in the SAME commit as the code.

THE `causalog.core` CONTRACTS ARE FROZEN as of 2026-08-25 (ADR-0025). Their
specification is docs/contracts.md v1.3.0. Changing a frozen type requires an ADR
and a coordinated update of every consumer -- it is not an edit. Everything
outside core/ is still `draft` EXCEPT the ontology pack schema, frozen at 1.0.0
by ADR-0026 and specified in docs/ontology.md. See section 6. The schema mapping DSL
(ADR-0036) is STILL `draft` at mapping_schema_version 1.1.0, and now for a better reason
than when it was written: it has consumers, and the first thing they did was change it
(ADR-0039 added `event_emissions`). Freezing it before that had settled would have been the
assertion-not-specification error OQ-009 exists to prevent.

The PRD is at docs/prd.md. The architecture blueprint is at docs/architecture.md;
read it before touching any module boundary, dependency, or storage decision.
```

**Current status in one line:** Phase P0 (Governance) closing, architecture blueprint and
scaffold complete, the canonical core (`causalog.core`) implemented and frozen at
`docs/contracts.md` v1.3.0, the **ontology layer** built (a versioned declarative pack DSL
with a loader, validator and content-addressed versioner — `causalog.ontology_runtime`, L1 —
plus the DataCo pack and an unrelated hospital pack), the **persistence layer** built (a
bi-temporal PostgreSQL schema in fifteen paired migrations with append-only enforcement at
the database, the Neo4j projection with its rebuild and drift commands, a Redis cache, and
in-memory fakes), and **the first six §36 modules built**: 1 Data Adapter, 2 Schema Mapper,
3 Entity Extractor, 4 Event Generator, 5 Timeline Builder, and 6 State Engine, all six
`built-unverified`. The DataCo file is
pinned by hash (`datasets/dataco.pin.json`), its column manifest is verified against the real
header, and a committed Data Quality Report measures it. **`Event` and `Entity` now exist as
artifacts rather than as contracts**: the LAW-EVENT boundary is crossed, and modules 3 and 4
ship a Reconciliation Report and an Event Quality Report that say what the reconstructed log
does and does not contain. **`Timeline`, `State`, and `Transition` now exist as artifacts
too**: modules 5 and 6 open the graph layer (L4) with a `TimelineQualityReport` and a
`StateQualityReport`, and neither module may import `ontology_runtime` directly (forbidden
edge F3) — `causalog.extraction.ontology_adapters` is the one place that boundary is
crossed, translating the pack into the plain `causalog.core.ontology_view` shapes `graph_engine`
consumes (ADR-0042). **The inference boundary is now crossed: module 9, the Candidate Cause
Generator, is built** (2026-09-02, ADR-0048 through ADR-0051) — seven independent generators,
one LAW-TIME gate, structural confounder flagging, a round-robin explosion bound, and a
Candidate Graph Report. It is `built-unverified`. **Module 10, the Confidence Scorer, is built
too** (2026-09-03, ADR-0052 and ADR-0053) — eight named components at
`confidence_schema_version` 2.0.0, two of them **gates rather than addends**, an explanation
per component carrying its arithmetic and its caveats, an `INSUFFICIENT_EVIDENCE` outcome
kept distinct from a low score, bands declared in the rule pack rather than in UI code, and
a Confidence Report whose first section is what is **not** calibrated. It is
`built-unverified`, and it is the first module to construct a `CausalEdge`. **On the measured
150-row slice no edge scores above 0.40 and none is promoted to `INFERRED`** — the honest
consequence of scoring a day-granular source with module 7 unbuilt, not a tuning problem
(R-14, OQ-024). **The inference layer now has an assembly step: the Causal Graph Builder**
(2026-09-04, ADR-0054 through ADR-0056) — the assembly step prd.md §25/§26/§31 describe and
§36 names no owner for, landed at L6 as a package that is deliberately **not** one of the 16
modules (OQ-025). It owns the promotion decision, which **moved out of module 10**: an
explicit per-edge-kind policy in a new `graph_construction` rule-pack namespace, LAW-TIME
re-verified at promotion by two independent mechanisms, a rejection ledger of equal standing
to the graph itself, propagation weights attributed from ontology `measurement_definitions`,
and feedback-loop detection over the **event-type projection** rather than over event
instances. It is `built-unverified`. **On the same 150-row slice the stated causal graph is
EMPTY**: 0 of 9,492 claims promoted, and the ledger says why — 65.5% `TEMPORALLY_UNVERIFIABLE`,
20.6% `INSUFFICIENT_EVIDENCE`, 13.8% `TEMPORAL_NOT_CERTAIN`, and only **8 claims** ever
reached the band comparison at all. The binding constraint is time, not the threshold, and
200 circuits were found of which **zero** are feedback loops and all 200 are temporal
artifacts (R-14 realised a third time, R-21). Seven of the 16 modules remain, and modules 7
and 8 are among them: both
module 9 and module 10 consume facts by value through the `GraphFacts` protocol the rule
engine established, so neither waited for the temporal property graph — module 9's
structural-path generator reports zero over zero relationships, and module 10's
`graph_connectivity` component is reported MISSING on 100% of edges, which costs every edge
score rather than being quietly renormalized away. **Modules 11 and 12 are built as of
2026-09-06 (ADR-0059 through ADR-0064), and the structural pattern miner with them** — the
Root Cause Analyzer emits ADR-0008's four labelled views as four fields with a trade-off per
disagreeing pair and no root-cause score anywhere on the type; the Propagation Analyzer
attributes consequence to the node SET rather than to the routes, so a diamond is counted once
by a type's own validator; and both traverse a `GraphView` that declares **which graph it
walked**. All three are `built-unverified`. **prd.md §55's root-cause budget is measured for the
first time** — 0.5 s against 3 s, over a graph at the committed slice's scale, with the three
orders of magnitude that measurement does NOT cover printed beside it. **On the 150-row slice
all five worked cases return no cause under the stated standing**, because the promoted graph is
still empty; the disowned diagnostic run produces five full rankings and every one of them is
unconvincing for reasons the reports state — the chain floor rejects all of them, the candidate
cap binds on all of them, all 500 chains in every case carry a partial-data flag, and the scored
graph is near-complete rather than causal (one event type touches 4,517 of 9,492 claims). **Module
13, the Counterfactual Simulator, is built as of 2026-09-07** (ADR-0065 through ADR-0072) — five
typed interventions validated against the ontology BEFORE anything simulates, so an impossible
premise is refused rather than simulated and flagged; propagation correct per edge KIND, where
**removing one of several contributing causes reduces the outcome and never eliminates it**; a
simulated world holding no `Event` and no `TimeInterval`, so prd.md §37's non-conflation is a
property of the types rather than a field a consumer must remember to read; and a validity
assessment whose `EXTRAPOLATION` verdict REPLACES the figure instead of sitting beside it. It is
`built-unverified`. **Its stated prerequisite had never been written** — three documents named a
reserved ADR number skipped at the scaffold, and `check_governance_consistency.py` could not see
it because all six of its rules fire on an ADR that exists; a seventh rule now closes that and
found two of the three dangling references itself. **prd.md §55's 5-second counterfactual budget
is measured for the first time.** On the 150-row slice **the PRD's own worked example cannot be
posed at all**: the step it names is emitted 48 times and placed in time zero times, and only 3
of 16 event types carry an instant at all. **Module 14, the Intervention Optimizer, is built as
of 2026-09-07** (ADR-0073 through ADR-0079) — the first artifact in this system that is an
INSTRUCTION rather than a description, and engineered from that fact: Principle 5 is enforced by
the TYPE (`min_length=1` on evidence and on assumptions, a `ConfidenceVector` with no default), so
an unsupported recommendation cannot be instantiated rather than being filtered out later; benefit
is obtained ONLY by calling module 13, asserted both numerically and over the AST, so a recommender
and a counterfactual over one act cannot disagree; two acts on one chain are simulated as a SET and
the naive sum is published beside the joint figure so the overlap is visible rather than merely
corrected; and cost and operational risk are read from the pack under closed two-member bases with
no `DERIVED` member, which is how this package's README sentence "may never infer a cost" stopped
being prose. **Operational risk had never been declared anywhere** — prd.md §50 requires it and
neither pack nor schema had it — so ADR-0073 adds a `risk_classes` vocabulary at pack schema 1.2.0,
mandatory-cost against optional-risk, because an absent cost ranks a candidate as FREE (a wrong
number) while an absent risk ranks it NOWHERE (a true statement about the pack). It is
`built-unverified`. **prd.md §55's 5-second recommendation budget is measured for the first time**
— 1.2 s — and its first version passed in 0.037 s while refusing all 1,223 candidates at the gate,
which is the "passed on having no work to do" failure the file's own docstring warns about; it now
refuses emptiness at three stages. **On the 150-row slice the run publishes ZERO recommendations
under BOTH standings**: every diagnostic candidate composes to a belief of 0.03 against a declared
floor of 0.50 that was chosen on principle and not to make the run produce output. The ten that came
closest are dominated by proposals to prevent a delay by removing the delay — circular, and an
artifact of the near-complete scored graph rather than a defect in module 14 (R-26). Four of the 16
modules remain.

**CORRECTION, on the record rather than overwritten (DEF-0004).** The previous revision of
this line claimed the column manifest "is verified against it". It was not: the manifest read
`UNVERIFIED_AGAINST_LOCAL_FILE` and a test asserted that it did. Prose and record disagreed in
the direction of claiming more verification than existed — the OQ-004 / OQ-008 class, third
instance. It is true as of 2026-08-30 because module 1 made it true.

---

## 1. Project identity

Project CausaLog is a **domain-agnostic Causal Intelligence Engine**. It ingests
historical event data and produces an explainable causal knowledge graph that supports
root-cause identification, propagation measurement, counterfactual simulation, and
ranked intervention recommendation — with every assertion carrying inspectable evidence
and an explicit provenance class. The reasoning core computes only over `Event`,
`Entity`, `State`, `Transition`, and `Relationship`; all domain vocabulary lives in a
replaceable ontology layer. The first implementation uses the DataCo SMART Supply Chain
dataset because it is a convenient reference domain, not because the system is about
logistics.

### Non-negotiable framing (prd.md §62)

This project is **not** a logistics dashboard.
It is **not** a predictive analytics platform.
It is **not** a machine learning model that predicts delays.
It is a **Causal Intelligence Platform** whose first implementation happens to use
logistics data. The domain is replaceable. The reasoning engine is not.

A proposed feature that improves dashboards but not causal reasoning does not belong in
the core engine (prd.md §17, Appendix B).

---

## 2. The Five Inviolable Laws

> Reproduced verbatim. Also present in `CONVENTIONS.md`. These two copies must remain
> byte-identical; a divergence between them is a defect, not a style difference.

1. **LAW-EVENT** — The reasoning core computes over `Event`, `Entity`, `State`, `Transition`, `Relationship`. Never over rows, never over DataFrames, never over CSV columns.
2. **LAW-TIME** — No causal edge may exist where `cause.timestamp >= effect.timestamp`. This is enforced in code, not by convention, and is unit-tested.
3. **LAW-PROVENANCE** — Every assertion carries a provenance class: `OBSERVED | ASSUMED | STATISTICAL | INFERRED | SIMULATED`. These are never merged, never silently promoted, and are visually distinct in the UI. Inferred results never overwrite observed facts.
4. **LAW-DOMAIN** — No file under `core/`, `graph_engine/`, `causal_engine/`, `counterfactual_engine/`, `recommendation_engine/` may contain the strings `warehouse`, `shipment`, `order`, `carrier`, `customer`, `delivery`, `inventory` (case-insensitive) outside of test fixtures. Enforced by a CI lint job.
5. **LAW-EVIDENCE** — Every confidence number decomposes into named, inspectable components with the evidence records that produced them. A bare float is a defect.

---

## 3. Current phase and module status

**Current phase: P0 — Governance.** Exit criterion: the six governance files exist, the
module contract document ("Prompt 02") exists, and OQ-001 through OQ-004 are resolved.
OQ-001 through OQ-004 are now all resolved (ADR-0006, ADR-0007, ADR-0008, ADR-0001), and
OQ-012 with them (ADR-0020), which unblocks module 4. **P0's exit criterion is still unmet:
the module contract document ("Prompt 02") does not exist, so OQ-009 stands and no interface
may be frozen.** That document is now the sole remaining P0 blocker. The architecture
blueprint (`docs/architecture.md`) and
the repository scaffold are in place, and the LAW-DOMAIN, layer-boundary, dependency-policy,
and law-copy checks now fail the build rather than existing as prose.

The ontology layer landed on 2026-08-28 (ADR-0026 through ADR-0029). It is **not** one of
the 16 modules: it is extension seam 2 of `docs/architecture.md` §5, and it exists at L1 so
that modules 2, 3 and 4 have a domain description to read when they are built. Its arrival
sets `ontology_version` (§7), which removes one of the two blockers on the determinism gate
— the other, the pipeline itself, is still OQ-014.

It was then put through a five-item acceptance checklist (ADR-0030, evidence in
`PROGRESS.md` §00c). Traceability, located diagnostics, and hash sensitivity/stability
needed no work. Two items were true and enforced by nothing: onboarding a pack required
editing three test files despite the layer's whole premise being that it does not, and
nothing stopped a reasoning module recomputing a metric the pack already declares. Both are
now checks — pack discovery is derived from the pack directory, and
`scripts/check_metrics_are_declared.py` refuses metric arithmetic in the reasoning packages,
reporting **exit 2 NOT-YET-RUNNABLE** until the first of them holds code. ADR-0031 then closed
that lint's own two stated holes the same day: it follows the value through a rebinding rather
than reading names, and it refuses a metric compared against a numeric literal.

Module list is prd.md §36, verbatim and in order. Phase grouping is **proposed, not
ratified** — see OQ-011.

| # | Phase | Module | Package path (`backend/src/causalog/…`) | Owner prompt | Status | Contract frozen? | Tests | Last touched |
|---|---|---|---|---|---|---|---|---|
| 1 | P1 Ingestion | Data Adapter | `ingestion/data_adapter` | TBD | **built-unverified** | no | 75 across unit/law/determinism, shared with module 2 | 2026-08-30 |
| 2 | P1 Ingestion | Schema Mapper | `ingestion/schema_mapper` | TBD | **built-unverified** | no | 13 unit tests are its own; shares the other 62 | 2026-08-30 |
| 3 | P1 Ingestion | Entity Extractor | `extraction/entity_extractor` | TBD | **built-unverified** | no | 14 unit tests are its own; shares the 34 law/determinism/ontology/integration tests with module 4 | 2026-08-30 |
| 4 | P1 Ingestion | Event Generator | `extraction/event_generator` | TBD | **built-unverified** | no | 76 its own (40 against the hand-derived ground truth, 36 unit); shares the other 34 | 2026-08-30 |
| 5 | P2 Graph | Timeline Builder | `graph_engine/timeline_builder` | TBD | **built-unverified** | no | 5 unit, 2 determinism, 1 law | 2026-08-31 |
| 6 | P2 Graph | State Engine | `graph_engine/state_engine` | TBD | **built-unverified** | no | 6 unit, 2 determinism (shared with module 5) | 2026-08-31 |
| 7 | P2 Graph | Relationship Resolver | `graph_engine/relationship_resolver` | TBD | not-started | no | none | — |
| 8 | P2 Graph | Temporal Graph Builder | `graph_engine/temporal_graph_builder` | TBD | not-started | no | none | — |
| 9 | P3 Inference | Candidate Cause Generator | `causal_engine/candidate_cause_generator` | TBD | **built-unverified** | no | 60 unit, 8 law, 7 determinism, 7 graph-invariant | 2026-09-02 |
| 10 | P3 Inference | Confidence Scorer | `causal_engine/confidence_scorer` | TBD | **built-unverified** | no | 50 unit, 7 law, 3 determinism; plus 10 added to `tests/unit/core/test_confidence_aggregation.py` for the gated strategy | 2026-09-03 |
| 11 | P3 Inference | Root Cause Analyzer | `causal_engine/root_cause_analyzer` | TBD | **built-unverified** | no | 8 unit, 45 law (parametrized over three packages), 11 graph-invariant and 6 diamond (shared with 12), 5 determinism (shared), 1 integration budget | 2026-09-06 |
| 12 | P3 Inference | Propagation Analyzer | `causal_engine/propagation_analyzer` | TBD | **built-unverified** | no | 10 unit; shares the 45 law, 17 graph-invariant, 5 determinism and 1 budget test with module 11; plus 11 added to `tests/unit/core/test_composition.py` | 2026-09-06 |
| 13 | P4 Simulation | Counterfactual Simulator | `counterfactual_engine` | TBD | **built-unverified** | no | 11 unit (edge kinds), 12 unit (validation gates), 5 property, 5 counterfactual-consistency, 48 law (parametrized per source file), 4 determinism, 8 graph (extrapolation), 1 integration budget | 2026-09-07 |
| 14 | P4 Simulation | Intervention Optimizer | `recommendation_engine` | TBD | **built-unverified** | no | 6 gate unit, 10 Principle-5 type, 17 scalarization (in `unit/core/`), 10 cut-set, 5 portfolio, 40 law (parametrized per source file), 3 added to `tests/counterfactual/`, 4 determinism, 1 integration budget | 2026-09-07 |
| 15 | P5 Surface | Explanation Generator | `explanation_engine` | TBD | not-started | no | none | — |
| 16 | P5 Surface | Visualization API | `api/visualization` | TBD | not-started | no | none | — |

**The Causal Graph Builder landed on 2026-09-04 (ADR-0054 through ADR-0056).** Like the
ontology layer and the rule engine it is **not** one of the 16 modules — it is the assembly
step between modules 10 and 11 that prd.md §25, §26 and §31 describe and that §36 names no
owner for. It lives at `causal_engine/causal_graph_builder` (L6), it is `built-unverified`,
and it has **106 tests** (50 unit, 13 graph-invariant including the planted-loop pair, 4
determinism, and 39 law tests in `tests/law/test_law_time_gates_every_promotion.py`,
parametrized per source file so the structural assertions grow with the package).

Two of its decisions are load-bearing and are recorded here because a later session will
otherwise re-derive them badly:

1. **Promotion moved here from module 10** (ADR-0054). `ProvenanceClass.INFERRED` is now
   assigned in exactly one file in the whole engine, `causal_graph_builder/policy.py`, and a
   law test asserts it structurally over the AST. `confidence_scoring.promotion_band` is
   deprecated; `ConfidenceReport.promoted_count` is structurally zero from this commit and
   the report says so rather than reading as a finding.
2. **Feedback loops are detected over the event-TYPE projection, never over event
   instances.** At the instance level a `CERTAIN` verdict is a strict precedence relation
   and strict precedence admits no cycle, so an all-`CERTAIN` circuit over instances is
   arithmetically impossible and a detector running there could only ever find artifacts.
   prd.md §31's loop closes across process instances. This is asserted by
   `tests/graph/test_feedback_loops.py::test_no_instance_level_cycle_is_all_certain` so it
   cannot be quietly reversed.

**Modules 11 and 12 landed on 2026-09-06 (ADR-0059 through ADR-0064), and the structural
pattern miner with them.** Like the ontology layer, the rule engine and the Causal Graph
Builder, `causal_engine/pattern_miner` is **not** one of the 16 modules — it is the answer to
prd.md §10's Executive Leadership user, whom §36 names no owner for (OQ-025's shape a second
time, ADR-0064). Three of its decisions are load-bearing and are recorded here because a later
session will otherwise re-derive them badly:

1. **A traversal declares which graph it walked** (ADR-0059). `GraphStanding` is a required
   field with no default on every artifact these packages produce. `STATED` walks the promoted
   graph; `UNPROMOTED_DIAGNOSTIC` walks module 10's scored graph before promotion and everything
   derived from it is disowned — refused `INFERRED` by a validator, printed under a fixed notice
   held as a property, and written to separate files that nothing merges. It exists because the
   stated graph is EMPTY on this slice and silence exercises none of the machinery.
2. **Consequence is attributed to the node SET, never to the routes** (ADR-0061). A consequence
   reachable four ways is one consequence, and `ConsequenceSet` validates its own membership
   unique so the guarantee is a type's rather than a call site's. Counterfactual-lite is a
   re-reachability diff and not a subtraction, which is what makes it correct on diamonds; a
   joint cause group is removed as a unit.
3. **A chain is only as strong as its weakest link, and the composition is named** (ADR-0060).
   `core.composition` registers `weakest_link_v1` (the default) and `independent_product_v1`
   beside it. The product is reported in its own column and never blended, and **path length is
   a separate field** — ADR-0008's never-blend ruling one level down. The minimum's cost is that
   it ties heavily, and a PLATEAU is reported as a plateau rather than broken arbitrarily.

**ADR-0008's four views are four fields.** `RootCauseRanking` carries `earliest_cause`,
`highest_consequence_cause`, `most_actionable_cause` and `actionable_root_causes`, with a
`TradeOff` emitted for every pair naming different events. There is **no root-cause score
anywhere in the package**: the number would have to weight a quantity against a position in a
chain, so any figure produced would be a judgement disguised as arithmetic.

**The prd.md §55 root-cause budget is now measured rather than quoted.** `make bench` runs a
real benchmark for the first time (0.5 s against a 3 s budget over a graph at the committed
slice's scale), and `make laws` lost the `check_metrics_are_declared.py` exit-2 tolerance
exactly as that guard's own comment instructed — the scan now covers 84 files across five
packages.

**Extension seam 4 — the rule engine — landed on 2026-09-01 (ADR-0044 through ADR-0047).**
Like the ontology layer it is **not** one of the 16 modules: it is the mechanism prd.md §46
requires (`docs/architecture.md` §1.2, L5), and it exists so that modules 9 and 10 have rules
to evaluate when they are built. Its arrival sets `rule_pack_version` (§7), which was the
**last unset `RunKey` input** — every one of the five now has a real value, so a `run_id` can
be minted for the first time. It also closes the ontology loader's only `NOT_RUNNABLE`
finding: `ONT-N-RULE-COVERAGE` reported that "every event type has a producing rule" was not
checked because no rule pack existed, and `load_pack(..., produced_event_types=...)` now has
a supplier. The check is real, and it reports 6 blind spots — see §7 and
`docs/reports/dataco/rule-coverage.md`.

Every package exists with an `__init__.py`, a `README.md` stating its single responsibility
and its forbidden dependencies, and a mirrored `tests/unit/` directory. Only
`ingestion/data_adapter`, `ingestion/schema_mapper`, `extraction/entity_extractor`,
`extraction/event_generator`, `graph_engine/timeline_builder`, `graph_engine/state_engine`,
`rule_engine`, `causal_engine/candidate_cause_generator`,
`causal_engine/confidence_scorer` and `causal_engine/causal_graph_builder` contain an
implementation. Layer ranks and forbidden edges are in `docs/architecture.md` §1 and are
enforced by `scripts/check_layers.py`.


**Status vocabulary (closed set):** `not-started` · `in-progress` · `blocked` ·
`built-unverified` · `done`. A module reaches `done` only when the Definition of Done in
`CONVENTIONS.md` §3 is fully satisfied and the evidence is pasted into `PROGRESS.md`.
`built-unverified` exists so that "code written" is never confused with "gate passed".

### §36 module ↔ §44 service mapping (ratified — ADR-0006, closes OQ-001)

prd.md §36 lists 16 modules; prd.md §44 lists 10 backend services with overlapping but
differently-named responsibilities. **ADR-0006 rules that §36 is the authoritative unit of
build, ownership, test, and gate; §44 names are deployment-level service groupings and
carry no ownership.** A prompt or commit that names a §44 service as the unit of work is a
defect.

| §44 service | §36 modules it bundles |
|---|---|
| Dataset Service | Data Adapter, Schema Mapper |
| Ontology Service | Schema Mapper (ontology half), Entity Extractor |
| Event Builder | Event Generator |
| Timeline Builder | Timeline Builder, State Engine |
| Graph Builder | Relationship Resolver, Temporal Graph Builder |
| Causal Engine | Candidate Cause Generator, Confidence Scorer |
| Root Cause Engine | Root Cause Analyzer, Propagation Analyzer |
| Counterfactual Engine | Counterfactual Simulator |
| Recommendation Engine | Intervention Optimizer |
| Explanation Engine | Explanation Generator |
| *(unmapped in §44)* | Visualization API |

---

## 4. Architecture snapshot

**`docs/architecture.md` is authoritative for structure.** This section is the summary a
session reads first; the document is what it reads before touching a boundary.

### Layer ranks and the one-directional rule

Dependencies flow one way: `UI -> API -> orchestration -> reasoning modules -> core
contracts`. A package may import its own rank and every lower rank, never a higher one.

| Rank | Package | Modules |
|---|---|---|
| L0 | `core` | — (canonical types, ports, errors) |
| L1 | `ontology_runtime` | — |
| L2 | `ingestion` | 1 Data Adapter · 2 Schema Mapper |
| L3 | `extraction` | 3 Entity Extractor · 4 Event Generator |
| L4 | `graph_engine` | 5 · 6 · 7 · 8 |
| L5 | `rule_engine` | — |
| L6 | `causal_engine` | 9 · 10 · 11 · 12 |
| L7 | `counterfactual_engine` · `recommendation_engine` | 13 · 14 |
| L8 | `explanation_engine` | 15 |
| L9 | `orchestration` | — |
| L10 | `api` | 16 Visualization API |
| — | `persistence` | — (adapters for L0 ports; imported only by L9) |

### Forbidden dependency edges — enforced, not advisory

`scripts/check_layers.py` fails the build on any of these. Full statements and rationale in
`docs/architecture.md` §1.4.

| # | Forbidden |
|---|---|
| F1 | `core` → any other project package |
| F2 | any `Ln` → any higher `Lm` |
| F3 | L4–L10 → `ontology_runtime` — **nothing depends on the ontology except mapping/extraction (L2–L3) and presentation (L10, labels only)** |
| F4 | anything except `orchestration` → `causalog.persistence.*` |
| F5 | `api` → any reasoning package or the graph store (no reach-through) |
| F6 | `graph_engine` → `causal_engine` (the inference boundary) |
| F7 | rank ≥ 3 → any tabular library (the LAW-EVENT boundary at import level) |
| F8 | `core` → any third party beyond the data-validation library |
| F9 | anything → `pgmpy`, `dowhy`, `torch`, `torch_geometric`, `sklearn`, `tensorflow` (ADR-0003) |

### Storage boundary (ADR-0001)

PostgreSQL is the system of record. Neo4j is a **derived, fully rebuildable projection** —
a write with no backing PostgreSQL fact is a defect, and every graph response carries
`graph_projection_version` so staleness is detectable. Redis holds recomputable values only,
keyed by `run_id`; flushing it may change latency and never an answer. Rebuild procedure:
`docs/architecture.md` §3.3, command `make rebuild-graph RUN_ID=…`.

### The Run (ADR-0013)

`run_id = "run:" + sha256(dataset_version | ontology_hash | rule_pack_version |
engine_version | seed)[:16]`. **Every inferred artifact is scoped to a `run_id`; observed
facts are scoped to `dataset_version`** — which is what makes "inference never overwrites
observation" structural rather than procedural. `execution_id` is the per-process
identifier, random, and excluded from every determinism diff.

### Data flow (reconciles prd.md §19, §36, §48, Appendix A)

```
Raw Dataset / External APIs
   │
   ▼  [1] Data Adapter ......... ingest, validate, clean          P1
   ▼  [2] Schema Mapper ........ columns → ontology concepts      P1
   ▼  [3] Entity Extractor ..... → Entity                         P1
   ▼  [4] Event Generator ...... rows-as-evidence → Event         P1  <-- LAW-EVENT boundary
   ─────────────────── below this line: NO rows, NO DataFrames ───────────────────
   ▼  [5] Timeline Builder ..... group events by process          P2
   ▼  [6] State Engine ......... → State, Transition              P2
   ▼  [7] Relationship Resolver. → Relationship                   P2
   ▼  [8] Temporal Graph Builder → Temporal Property Graph        P2  (no inference here)
   ▼  [9] Candidate Cause Gen .. → CandidateEdge[]                P3  <-- LAW-TIME gate
   ▼ [10] Confidence Scorer .... → ConfidenceVector               P3  <-- LAW-EVIDENCE gate
   ▼ [11] Root Cause Analyzer .. ranked actionable causes         P3
   ▼ [12] Propagation Analyzer . depth/breadth/duration/impact    P3
   ▼ [13] Counterfactual Sim ... SIMULATED worlds, no writeback   P4
   ▼ [14] Intervention Optimizer ranked interventions             P4
   ▼ [15] Explanation Generator  graph evidence → language        P5
   ▼ [16] Visualization API .... structured JSON                  P5
   │
   ▼ Interactive User Interface
```

**Two boundaries are load-bearing and are enforced in code, not prose:**
- **The LAW-EVENT boundary** after module 4: nothing downstream may see a row or a
  DataFrame. Enforced by F7 and by the absence of `RawRecord` in any signature above L3.
- **The inference boundary** between modules 8 and 9: module 8 records only what was
  observed and writes `PRECEDES`; module 9 is the first place an `INFERRED` assertion may
  be created. Enforced by F6.

## 5. Canonical vocabulary

All terminology is defined in **`GLOSSARY.md`**. It is authoritative.

Rule: a term used in code identifiers, API fields, ADRs, or UI copy that is not in
`GLOSSARY.md` is a defect. Add the term to the glossary in the same commit that
introduces it. Do not create a second definition of an existing term anywhere,
including in this file.

---

## 6. Interface registry

Every cross-module public interface. Seeded from the §36 pipeline seams. **Every
`causalog.core` type is `frozen` as of 2026-08-25 (ADR-0025). Everything else is still
`draft`.** The module contract document OQ-009 required now exists as `docs/contracts.md`
v1.0.0, and the four schema versions §7 needs are set; those were the two locks on freezing.

A row owned by a module that does not yet exist stays `draft`. Freezing a type nobody has
built would be the assertion-not-specification error OQ-009 existed to prevent, in a new
place.

Stability vocabulary: `draft` (may change freely) · `frozen` (change requires an ADR and
a coordinated update of every consumer) · `deprecated` (still present, has a named
replacement, has a removal date).

| Interface (planned) | Owning module | Consumers | Stability | ADR |
|---|---|---|---|---|
| `RawRecordBatch` | Data Adapter | Schema Mapper | **frozen** | ADR-0004, ADR-0025. Emitted by `SourceReader`; the Data Adapter consumes it and no type above L2 names it (`tests/law/test_no_row_escapes_ingestion.py`) |
| `SchemaMappingSpec` | Schema Mapper | Data Adapter, Entity Extractor, Event Generator | draft | ADR-0036 — nine namespaces at `mapping_schema_version` 1.1.0, a closed `Transform` registry, `unmapped_value_policy` with one admissible value, and `status: PROPOSED_UNCONFIRMED` refused by the loader. **ADR-0039 added `event_emissions`** — one closed condition tree per event type — and `IdentityBindingSpec.observed_at`. Still `draft`: it now has consumers, and the first thing they did was change it |
| `MappedRecord`, `MappedRecordBatch`, `RecordView` | Schema Mapper | Entity Extractor, Event Generator **only** (LAW-EVENT) | draft | ADR-0039 — `docs/architecture.md` §2 named these as module 2's output and module 2 shipped without them. A row re-expressed in ontology vocabulary: every value addressed `CONCEPT.attribute`, no source column name surviving as a key. `RecordView` is the same record indexed for lookup |
| `ReconciliationReport`, `EntityTypeReconciliation`, `AttributeConflict`, `EntityHistory`, `EntityAttributeVersion` | Entity Extractor | operators; `docs/reports/` | draft | ADR-0039 — entities created/merged/conflicted per type, with every disagreement reported under every policy that tolerates one. Attribute history is a separate artifact because `Entity`'s address excludes its attributes |
| `EventQualityReport`, `EventTypeTally`, `ProcessCoverage`, `ProcessStepCoverage` | Event Generator | operators; `docs/reports/`; Timeline Builder (coverage) | draft | ADR-0040 — counts by type and provenance class, precision and kind distributions, orphans, unevaluable conditions, and process coverage separating a gap in ONE instance from a step no record can ever witness |
| `DataQualityReport`, `Finding`, `HeadlineConstraint` | Data Adapter | operators; `docs/reports/` | draft | Every `Finding` carries a `downstream_consequence` with `min_length=1`, so the requirement is structural |
| `SourceDescription` | `core/ports/source.py` | Data Adapter | draft | ADR-0038 — what a source reader reports about a source without the adapter importing the reader (forbidden edge F4) |
| `Entity`, `Lifecycle` | Entity Extractor | Event Generator, Relationship Resolver, State Engine | **frozen** | ADR-0025; `lifecycle` stored, `current_state` derived by `core.derivation` |
| `Event` | Event Generator | Timeline Builder, State Engine, Temporal Graph Builder, Root Cause Analyzer | **frozen** | ADR-0004, ADR-0021 (interval time), ADR-0008 (`is_actionable`), ADR-0020 (`trigger`), ADR-0009 (`confidence` is a vector, not a float), ADR-0025 |
| `Timeline`, `TimelineEntry`, `TimelineEntryKind`, `TimelineView` | Timeline Builder | State Engine, Candidate Cause Generator | draft | ADR-0042 — lands as a `core` type (like `Event`/`State`/`Transition`, not inside `graph_engine`), so every consumer imports one canonical definition; `IdentifierPrefix.TIMELINE` added additively. `TimelineEntry.sequence_provenance` records ADR-0043's tie-break rule per adjacency |
| `State`, `Transition` | State Engine | Temporal Graph Builder, Counterfactual Simulator | **frozen** | ADR-0025; `State.held_over` is the validity interval and `derived_from_event_id` names its origin |
| `Relationship` | Relationship Resolver | Temporal Graph Builder | **frozen** | ADR-0025; structural only — `CAUSES` may never appear here |
| `TemporalPropertyGraph` | Temporal Graph Builder | Candidate Cause Generator, Propagation Analyzer | draft | — |
| `CandidateEdge` | Candidate Cause Generator | Confidence Scorer | draft | **ADR-0048** — the prd.md §27 candidate, carrying **no confidence field at all**, so "generation never scores" is enforced by the type rather than by convention. Reuses the frozen payload union; its address includes `generator_id` AND the payload, because the graph is a multigraph and one generator legitimately makes two claims over one pair (DEF-0006) |
| `CandidateGraph`, `TruncationRecord` | Candidate Cause Generator | Confidence Scorer | draft | ADR-0050 — a multigraph keyed `(source, target, edge_kind, generator_id)`; parallel edges retained per generator with their own evidence. Checks its own totals at construction and raises rather than publishing a graph whose numbers disagree with themselves |
| `ConfoundingFlag`, `ConfoundingStructure` | Candidate Cause Generator | Confidence Scorer, Explanation Generator | draft | ADR-0051 — `POSSIBLE_MEDIATION` and `POSSIBLE_COMMON_CAUSE`, emitted as a separate artifact that mutates no edge. Makes a structure visible; resolves nothing, and says so on every flag |
| `CandidateGraphReport`, `GeneratorTally`, `PerEffectDistribution` | Candidate Cause Generator | operators; `docs/reports/` | draft | Candidates per generator with `NOT_RUNNABLE` distinguished from zero, rejections by reason, the per-effect distribution, and `UNDETERMINED` kept separate from temporally unverifiable |
| `CausalEdge`, `CausalEdgeKind`, `CausalEdgePayload` | **Confidence Scorer** | Propagation Analyzer, Counterfactual Simulator, Root Cause Analyzer | **frozen** | ADR-0022 — five payload types, LAW-TIME enforced in `between`, `temporally_unverifiable` beside the verdict; ADR-0025. **Owner corrected from module 9 to module 10 by ADR-0048:** `CausalEdge` requires a `ConfidenceVector` and module 9 may not assign one, so module 10 is what actually constructs it. The type is untouched — only the attribution was wrong |
| `ConfidenceVector`, `ConfidenceComponent` | Confidence Scorer | Root Cause Analyzer, Intervention Optimizer, Explanation Generator | **frozen** | ADR-0009 — `scalar` is derived and names its `aggregation`; ADR-0025. **The types are untouched at `confidence_schema_version` 2.0.0**; what changed is the admissible component NAMES (six → eight) and the registered strategies, both of which live in `core/aggregation.py` (ADR-0052) |
| `CausalGraph`, `ScoredEdge`, `ComponentExplanation`, `ScoringOutcome` | Confidence Scorer | Root Cause Analyzer, Propagation Analyzer, Counterfactual Simulator, Explanation Generator | draft | **ADR-0052.** `CausalGraph` holds one `ScoredEdge` per `(source, target, edge_kind)` — module 9's parallel candidates are FUSED, because `CausalEdge.address` omits `generator_id` and `CandidateEdge.address` includes it. `ScoredEdge` wraps the frozen `CausalEdge` with what the frozen type has nowhere to hold: a `ComponentExplanation` per component (plain language, caveats, the arithmetic, and a `missing` flag), the `ScoringOutcome`, the band, and which gate bound the scalar. Prose lives beside the frozen type rather than in it, because prose gets reworded and a frozen contract change is an ADR (ADR-0025). Sequenced canonically, **never by score** — ranking is module 11's |
| `PromotedGraph`, `PromotedEdge`, `DemotionRecord`, `DemotionReason`, `EdgeLineage`, `JointCauseGroup`, `PropagationWeight`, `TypingRecord` | **Causal Graph Builder** | Root Cause Analyzer, Propagation Analyzer, Counterfactual Simulator, Explanation Generator | draft | **ADR-0054.** The engine's stated view, and — of equal standing in the same artifact — the ledger of everything it declined to state. `promoted + demoted == considered` is checked at construction, so a dropped claim raises rather than being published as an absence. `EdgeLineage` carries the WHOLE `ConfidenceVector`, not its scalar: a ledger entry saying "this scored 0.24" and nothing else is the unexplained number prd.md §49 forbids, and a demoted claim has no `CausalEdge` beside it to look the components up on. A `CONTRIBUTING` edge names its `JointCauseGroup` and the group is promoted all-or-nothing |
| `FeedbackLoop`, `LoopClassification`, `LoopMember`, `LoopDetectionResult`, `CircuitTruncation` | **Causal Graph Builder** | Propagation Analyzer, Explanation Generator | draft | **ADR-0054** — prd.md §31. Detected over the event-TYPE projection, never over event instances: at the instance level a `CERTAIN` verdict is a strict precedence relation, strict precedence admits no cycle, so an all-`CERTAIN` circuit is arithmetically impossible and a detector running there could only ever find artifacts. Four classifications, because collapsing them overclaims: `GENUINE`, `TEMPORAL_ARTIFACT`, `WITHIN_INSTANCE`, `UNPROMOTED`. Classification is engine code and no pack may override it |
| `GraphQualityReport`, `PolicyGap`, `OrphanEffect`, `ContradictionFinding` | **Causal Graph Builder** | operators; `docs/reports/` | draft | ADR-0054 — first section is what the graph does **not** contain, then the rejection ledger by reason, then counts. Orphan effects separate "nothing was ever proposed" from "proposals were made and fell short". Carries the fraction of the graph resting on `ASSUMED` inputs |
| `PropagationAnalysisSpec`, `RootCauseAnalysisSpec`, `PatternMiningSpec`, `ImpactAggregationSpec` | `rule_engine/<domain>/` | Propagation Analyzer, Root Cause Analyzer, the pattern miner | draft | **ADR-0063** — `rule_pack_schema_version` 1.5.0, additive and defaulted, ADR-0049's absent-means-CANNOT-RUN rule for the fourth time. A pack chooses WHICH named composition and ranking function apply; it never supplies one. There is deliberately **no weighting field** between earliness and prevented consequence — absent because ADR-0008 rules the number must not exist |
| `GraphConstructionSpec`, `PromotionThresholdSpec`, `MagnitudeAttributionSpec`, `CompetingEffectPolicy`, `WeightNormalization` | `rule_engine/<domain>/` | Causal Graph Builder | draft | **ADR-0055** — `rule_pack_schema_version` 1.3.0, additive and defaulted. A promotion threshold **per edge kind**, because a `DIRECT` claim and an `AMPLIFYING` claim are not the same assertion. Every field optional; absent means the policy CANNOT RUN and is reported, never defaulted. `confidence_scoring.promotion_band` is **deprecated** by this row and the loader warns |
| `MagnitudeMeasurementView`, `MeasurementExpressionView`, `MeasurementExpressionOperator`, `MeasurementKindView` | `core/ontology_view.py` | Causal Graph Builder | draft | **ADR-0056** — additive, beside the duration views rather than widening them. Produced by `extraction.ontology_adapters.magnitude_measurements_of`, which excludes nothing by kind |
| `evaluate_measurement`, `MeasurementNode` | `core/measurement.py` | State Engine, Causal Graph Builder | draft | **ADR-0056** — the one walk of a declared operator tree in this repository. Generic by structural protocol, so it evaluates both view types without a conversion step. `state_engine.measurement.evaluate_duration_seconds` is now a thin restriction of it with unchanged behaviour |
| `DerivedPrecedence`, `DerivedPrecedenceIndex`, `temporal_binding_source` | `core/precedence.py` | Confidence Scorer; produced by `ingestion.data_adapter.derived_precedence_index` | draft | **ADR-0057** — the carrier for module 1's measurement of which of a source's instants were COMPUTED rather than recorded. At L0 so `causal_engine` never imports `ingestion`. `precedence_for` compares `TimeInterval.source` locators by STRING EQUALITY and may never parse one — parsing would make engine code a reader of the source description. The pair is DIRECTED; a reversed lookup misses, because the measurement claims one direction only |
| `RejectedProposal`, `SAMPLED_REJECTIONS` | **Candidate Cause Generator** | operators; `docs/reports/` | draft | **ADR-0058** — one claim the gate or the cap refused, retained with the effect it was refused FOR. Records are bounded (the 150-row slice rejects 143,145 against 17,864 retained); the per-effect COUNTS are complete. `GENERATOR_NOT_RUNNABLE` names no effect and is structurally refused, so coverage is instance-level for four of five reasons and the type says four |
| `RootCauseRanking`, `RankedCause`, `ActionabilityStanding`, `Recurrence`, `TradeOff`, `ViewName`, `RootCauseReport` | **Root Cause Analyzer** | Explanation Generator, Intervention Optimizer, Visualization API | draft | **ADR-0008, ADR-0059, ADR-0062.** FOUR labelled fields, never blended: `earliest_cause`, `highest_consequence_cause`, `most_actionable_cause`, `actionable_root_causes`, with a `TradeOff` per disagreeing pair. `RankedCause` carries five signals side by side and the whole `ConfidenceVector`, never a scalar. There is **no root-cause score field anywhere on the type** — a law test asserts it. `standing` is required and a diagnostic one may not carry `INFERRED` |
| `PropagationReport`, `PropagationTree`, `PropagationNode`, `ConsequenceSet`, `MagnitudeShare`, `PathConfidence`, `TruncationRecord` | **Propagation Analyzer** | Root Cause Analyzer, Intervention Optimizer, Explanation Generator | draft | **ADR-0059, ADR-0060, ADR-0061.** prd.md §30's seven measures, none combined: depth and breadth are separate fields, magnitude is keyed by the measurement that produced it, and confidence composes per route under a named function with its length beside it. `ConsequenceSet` validates its membership sorted and UNIQUE at construction — that is the whole no-double-counting guarantee, held by a type. Reaching a bound is a `TruncationRecord`, never a completed sweep |
| `GraphStanding`, `GraphView`, `GraphLink`, `stated_view`, `diagnostic_view` | **Propagation Analyzer** | Root Cause Analyzer, the pattern miner | draft | **ADR-0059** — the two standings. `diagnostic_view` is the ONLY construction site of `UNPROMOTED_DIAGNOSTIC` in the engine, asserted over the AST. Both `PromotedGraph` and module 10's `CausalGraph` satisfy one protocol, so neither module learns which it is walking except to record it. `PromotedGraph` ships no `edges_by_source`, so the forward index is built here and its canonical sequencing is part of the protocol's contract |
| `PreventedConsequence`, `prevented_by_removing`, `share_of_whole` | **Propagation Analyzer** | Root Cause Analyzer, Counterfactual Simulator | draft | **ADR-0061** — counterfactual-lite: `reachable(seed) \ reachable(seed, excluding=n)`, a re-reachability diff and not a subtraction, which is what makes it correct on diamonds. A joint cause group is removed as a UNIT. `share_of_whole` is prd.md §32's "propagation reduced 82%" figure and returns `None` rather than zero when either operand is unmeasurable |
| `StructuralPatternReport`, `Motif`, `Bottleneck` | **`causal_engine/pattern_miner`** | Explanation Generator, Visualization API | draft | **ADR-0064** — prd.md §10's Executive Leadership user, whom §36 names no owner for. Measured over the event-TYPE projection; every row carries the process instances it spans beside its raw count. In-degree and out-degree are never summed and there is no combined importance figure. An empty section without a stated reason is refused at construction |
| `SimulatedWorld`, `SimulatedEvent`, `WorldDiff`, `EventDelta`, `DeltaKind` | **Counterfactual Simulator** | Intervention Optimizer, Explanation Generator, Visualization API | draft | **ADR-0068, ADR-0069, ADR-0072.** A world holds NO `Event` and NO `TimeInterval` — `SimulatedEvent` and `core.perturbation.SimulatedInstant` are separate shapes, so prd.md §37's non-conflation holds at the type level rather than by a provenance field a consumer must remember to read. `standing` is required with no default and a diagnostic one may not carry `INFERRED`. **`eliminated_event_ids` and `reduced_event_ids` are separate accessors and are never summed:** a consequence that would have been smaller is not one that would have been prevented, and merging them is the single most common counterfactual error. Addressed `sim:digest(base_graph_id \| interventions)` |
| `Intervention`, `InterventionKind`, `InterventionPayload`, `RejectedIntervention`, `RejectionReason` | **Counterfactual Simulator** | Intervention Optimizer, Explanation Generator | draft | **ADR-0066** — five typed changes as a discriminated union, closed because the kind enters the content address. Every change is validated against the ontology BEFORE anything is simulated, and a set holding one inadmissible member never partially executes. A rejection is an artifact of equal standing to the world (ADR-0054's ledger), carrying the declaration it was checked against; `DECLARATION_ABSENT` is kept distinct from every reason that means "checked and refused" |
| `ValidityAssessment`, `SupportEnvelope`, `ValidityVerdict`, `SensitivityFinding`, `Assumption` | **Counterfactual Simulator** | Intervention Optimizer, Explanation Generator, Visualization API | draft | **ADR-0070.** The support envelope measures what the RUN witnessed; the ontology's `admissible_range` is what the DOMAIN declares possible, and the two are deliberately in different places because a value can be possible and unsupported. `EXTRAPOLATION` is returned **instead of** a figure, never beside one. Assumptions carry `falsified_by`, so none of them is a disclaimer. Nothing here is calibrated and `NOT_CALIBRATED_NOTICE` says so first — R-23 |
| `CounterfactualReport`, `PolicyGap` | **Counterfactual Simulator** | operators; `docs/reports/` | draft | first section is what the report does NOT contain, last is what the run did not check. The extrapolation verdict replaces the magnitude in the rendered table |
| `SimulationContext`, `base_world_address` | **Counterfactual Simulator** | orchestration (wiring) | draft | **ADR-0069** — carries module 12's context WHOLE, so the two cannot disagree about which graph or which depth. Holds `PromotedGraph` as well as its `GraphView` because module 13 must branch on the edge PAYLOAD and `GraphLink` deliberately omits it. `base_world_address` is the first half of `CONVENTIONS.md` §9's `sim:` recipe: a `run_id` will not serve, because one run holds both the stated graph and the scored one |
| `SimulatedInstant`, `carry_instant`, `shift_instant`, `precedes`, `transmitted_reading`, `unscale_reading` | `core/perturbation.py` | Counterfactual Simulator | draft | **ADR-0068, ADR-0069** — at L0 for the reason ADR-0061 put `core/attribution.py` there: the metric lint scans `counterfactual_engine/` and refuses this arithmetic, correctly. `transmitted_reading` takes `eliminated` as a keyword rather than inferring it from shares summing to one — shares summing to one is an arithmetic coincidence, nothing reaching a consequence is a fact about the graph, and reading the first as the second is how a partial removal is reported as a prevention |
| `AttributeView`, `MutabilityView`, `mutable_attributes_of` | `core/ontology_view.py` | Counterfactual Simulator | draft | **ADR-0067** — additive beside the magnitude and actionability views; `EventTypeView` is untouched. An absent declaration REFUSES every attribute change on that type and is reported, never read as permission |
| `CounterfactualSimulationSpec` | `rule_engine/<domain>/` | Counterfactual Simulator | draft | **ADR-0071** — `rule_pack_schema_version` 1.6.0, additive and defaulted, ADR-0049's absent-means-CANNOT-RUN rule for the fifth time. The hospital pack declares nothing in it, exercising that path for the third time across two packs |
| `Intervention` | Intervention Optimizer | Explanation Generator, Visualization API | draft | — |
| `Explanation` | Explanation Generator | Visualization API | draft | — |
| `EvidenceRecord`, `EvidenceItem`, `EvidenceKind` | Confidence Scorer | all downstream (LAW-EVIDENCE) | **frozen** | ADR-0025 — a record is a citation, an item is a re-verifiable justification carrying the query or rule that produced it |
| HTTP API (prd.md §53) | Visualization API | Frontend | draft | — |
| `TimeInterval`, `Precision`, `TimestampKind`, `TemporalVerdict`, `DurationBound` | `core/temporal.py` | every module that compares two instants | **frozen** | ADR-0021; comparison semantics in `docs/contracts.md` §3 |
| `ProvenanceClass`, `combine` | `core/provenance.py` | all (LAW-PROVENANCE) | **frozen** | ADR-0005 — `combine` returns the weakest input, never stronger; ADR-0025 |
| `Aggregator`, `AGGREGATORS`, `aggregate` | `core/aggregation.py` | Confidence Scorer | **frozen** | ADR-0009 — registry keyed by name; the name travels with the data |
| `PathComposer`, `PATH_COMPOSERS`, `compose` | `core/composition.py` | Propagation Analyzer, Root Cause Analyzer | draft | **ADR-0060** — how a chain's belief derives from its links, as distinct from how one claim's components roll up. `weakest_link_v1` is the default and `independent_product_v1` is registered beside it; the name travels with the data as `ConfidenceVector.aggregation` does one level down. Monotonicity along a path is a hypothesis test, not a comment |
| `combine_magnitudes`, `share_of`, `difference_of`, `COMBINATION_OPERATORS` | `core/attribution.py` | Propagation Analyzer | draft | **ADR-0061** — at L0 for the reason `core/measurement.py` is: the metric lint refuses this arithmetic inside a reasoning package and is right to. Three operators, not nine: the other six are not n-ary over an unordered set, so admitting one would make a total depend on iteration sequence |
| `Ranker`, `RANKERS`, `rank_value` | `core/ranking.py` | Root Cause Analyzer | draft | **ADR-0008, ADR-0063** — ADR-0008's prevented-times-confidence criterion, under a versioned name the ranked artifact records. Takes `chain_scalar`, not `confidence`: a float bound to a confidence-shaped name is refused by `check_confidence_is_a_vector.py`, correctly |
| `ActionabilityView`, `OrdinalClassView` | `core/ontology_view.py` | Root Cause Analyzer | draft | **ADR-0062** — additive, beside the magnitude views. Produced by `extraction.ontology_adapters.actionability_of` / `cost_classes_of` / `severity_classes_of`. The STAMP on the event stays authoritative; these only refine a set it has already selected, and a stamp-versus-pack disagreement is reported rather than resolved |
| `IdentifierPrefix`, `digest`, canonicalization helpers | `core/identifiers.py` | all (content addressing) | **frozen** | ADR-0013, ADR-0025; `CONVENTIONS.md` §9. `ONTOLOGY = "ont"` added additively by ADR-0028 (contracts.md 1.1.0); `MAPPING = "map"` added additively by ADR-0035 (contracts.md 1.2.0). No existing address recipe moved in either case |
| `to_canonical_json`, `from_canonical_json`, `CANONICAL_SCHEMA_VERSION` | `core/serialization.py` | persistence, Visualization API | **frozen** | ADR-0023 |
| `revise` | `core/immutability.py` | any module versioning an artifact | **frozen** | ADR-0025 — refuses an `OBSERVED` artifact (LAW-PROVENANCE) |
| `current_state`, `states_holding_at` | `core/derivation.py` | State Engine, Visualization API | **frozen** | ADR-0025 — `current_state` is a function of an entity *and an instant*, never a stored field |
| `CausaLogError` taxonomy | `core/errors.py` | all | **frozen** | ADR-0025; `CONVENTIONS.md` §7 |

### Extension seams — what a new domain implements (`docs/architecture.md` §5)

Five of the six are data files; exactly one is code, and it reads bytes rather than
reasoning. Declared in `core/ports/` so a domain author has one place to look — declaring
them there does **not** license a reasoning package to import them (forbidden edge F3).

| Interface (planned) | Kind | Supplied at | Consumers | Stability | ADR |
|---|---|---|---|---|---|
| `SourceReader` | Protocol | `persistence/sources/<domain>.py` | Data Adapter | draft | ADR-0038 — gained `describe()`. Implemented by `persistence.sources.delimited.DelimitedTextSource`; conformance is asserted, not assumed |
| `OntologySpec` (`DomainPack`, `ResolvedPack`) | data | `ontology/packs/<domain>/ontology.yaml` | Schema Mapper, Entity Extractor, Event Generator, Timeline Builder, State Engine, Relationship Resolver, Root Cause Analyzer, Intervention Optimizer | **frozen** at pack schema 1.0.0 | ADR-0026 (the DSL; pydantic normative, JSON Schema generated), ADR-0027 (path + inheritance), ADR-0029 (derived event types); ADR-0002; actionability declared per ADR-0008 |
| `SchemaMappingSpec` | data | `ontology/packs/<domain>/mapping.yaml` | Schema Mapper | draft | ADR-0002, ADR-0027 (path), **ADR-0036 (the schema)**. The DataCo mapping ships at `mapping_version` 1.0.0, `map:7acd9e24866745fb` |
| `RulePack` | data | `rule_engine/<domain>/` | Rule Engine, Candidate Cause Generator | draft | ADR-0044, ADR-0045, ADR-0047 — `rule_pack_schema_version` 1.0.0. Six rule kinds as payload types (the five prd.md §26 categories plus `CONSTRAINT`, which prunes rather than proposes), a closed condition operator tree over `RoleAddress`, and **no expression string, callable, or plugin hook anywhere in the schema**. `KnowledgeProvenance` is a rule-DSL enum, deliberately not `ProvenanceClass` (ADR-0045). Still `draft`: it has exactly one consumer, and that consumer (module 9) does not exist yet |
| `CostModel` | data | `ontology/packs/<domain>/cost.yaml` | Intervention Optimizer | draft | ADR-0027 (path); maps a pack-declared `cost_class` to an ordinal band |
| `PresentationLabels` | data | `ontology/packs/<domain>/labels.yaml` | Explanation Generator, Visualization API | draft | ADR-0027 (path) |
| `load_pack`, `LoadedPack`, `Diagnostic` | code | `causalog.ontology_runtime` | Orchestration (wiring); L2–L3 via injection | draft | ADR-0026 — the loader is `draft` while the DSL it loads is frozen: the schema is the contract, the API that reads it is not yet consumed |
| `ontology_hash` | code | `causalog.ontology_runtime.hashing` | `RunKey` (ADR-0013) | **frozen** | ADR-0028 — `digest(ONTOLOGY, to_canonical_json(resolved_pack))`. **Moved 2026-09-07 by ADR-0067**, which added optional `mutable`, `admissible_values` and `admissible_range` to `AttributeSpec` at pack schema 1.0.0 → 1.1.0 (additive; ADR-0026's freeze is lifted for an additive field and the cost is recorded in that ADR). `ont:55b7f5c6adeeee2c` → `ont:c4a93cb2d4ca4c89`; the hospital pack took the bump and declares no changeable attribute, so its hash moved too. `ontology_hash` is a `RunKey` input, so `run_id` moved with it. |

### Infrastructure ports (ADR-0014) — depended on by reasoning, implemented by `persistence`

| Interface (planned) | Owning package | Consumers | Stability | ADR |
|---|---|---|---|---|
| `FactRepository` | `core/ports` | Orchestration (wiring); reasoning via injection | draft | ADR-0014; write side, the bi-temporal `states_as_believed_at` / `retract_states` pair, and the run-scoped edge reads added 2026-08-29 (ADR-0032). Implemented by `persistence.postgres` and `persistence.memory` |
| `BulkFactWriter`, `BulkLoadSummary` | `core/ports` | Orchestration (wiring); Data Adapter via injection | draft | The prd.md §55 ingestion path. A SEPARATE port from `FactRepository` so a reasoning module cannot reach the fast path by accident — only ingestion is given one |
| `SchemaMigrator` | `core/ports` | Orchestration | draft | ADR-0033 — a port rather than a script entry point, so migration state is inspectable from a test and orchestration can assert the schema is current before a run |
| `GraphProjection` | `core/ports` | Temporal Graph Builder, Propagation Analyzer | draft | ADR-0001, ADR-0014; `drop_run` and a run-scoped `projection_version` added 2026-08-29 (ADR-0034). Implemented by `persistence.neo4j` |
| `DerivedCache` | `core/ports` | Orchestration | draft | ADR-0014 |
| `AuditSink` | `core/ports` | all modules writing auditable events | draft | ADR-0014; `actor`/`action`/`target`/`before`/`after` added 2026-08-29 per prd.md §54. `request_id` is `correlation_id` — one concept, one name (`GLOSSARY.md` §2.7) |
| `Clock` | `core/ports` | any module needing an instant (time is injected, never read) | draft | ADR-0014 |

### Run and envelope types

| Interface (planned) | Owning package | Consumers | Stability | ADR |
|---|---|---|---|---|
| `RunKey`, `Run` | `core/run.py` | Orchestration, `FactRepository` | **frozen** | ADR-0013, ADR-0025; `Run.created_at` comes from the `Clock` port and is excluded from `run_id` |
| `OutputEnvelope` | `core/run.py` | every artifact, every API response | **frozen** | ADR-0013, ADR-0025 |
| `RawRecord`, `RawRecordBatch` | `core/ports/source.py` | Data Adapter, Schema Mapper **only** (LAW-EVENT) | **frozen** | ADR-0004, ADR-0025 |

---

## 7. Data contracts in force

| Contract | Version in force | Set by | Notes |
|---|---|---|---|
| `event_schema_version` | `1.0.0` | Event Generator | semver; breaking change = major. Set 2026-08-25 by ADR-0025. `confidence` is a `ConfidenceVector`, not a float (ADR-0009); `occurred_at` carries `source` (ADR-0021). |
| `entity_schema_version` | `1.0.0` | Entity Extractor | semver. Set 2026-08-25 by ADR-0025. `lifecycle` is stored; `current_state` is derived and is not a field. |
| `edge_schema_version` | `1.0.0` | Candidate Cause Generator | semver. Set 2026-08-25 by ADR-0025. The closed `edge_kind` set and the five payload shapes are part of this contract (ADR-0022). |
| `confidence_schema_version` | `2.0.0` | Confidence Scorer | semver; component names are part of the contract. Set 2026-08-25 by ADR-0009 at 1.0.0. **Moved to 2.0.0 on 2026-09-03 by ADR-0052**, which added two component names `weighted_mean_v1`'s six could not express: `evidence_diversity` (independent evidence beats repeated evidence) and `contradiction_freedom` (counter-evidence lowers a score, named for freedom so every component rises with support and the aggregation stays monotone). Breaking, so it arrives as a NEW strategy `gated_weighted_mean_v1` beside the old ones rather than as a revision of them — `weighted_mean_v1`, `minimum_v1` and `DEFAULT_COMPONENT_WEIGHTS` are byte-identical and a vector naming one still recomputes to the same scalar. Two of the eight are **gates, not addends**: `temporal_support` and `contradiction_freedom` cap the scalar rather than contributing to it. `AGGREGATOR_COMPONENT_NAMES` declares what each registered aggregator accepts, because the registry stopped being uniform. |
| `ontology_version` | `1.0.0` | `ontology/packs/` | Set 2026-08-28 by ADR-0026. Two numbers, deliberately: **`pack_schema_version`** (`1.0.0`) versions the DSL and is the same for every pack; **`ontology_version`** is each pack's own semver. `ontology_hash` = `digest(ONTOLOGY, to_canonical_json(resolved_pack))` (ADR-0028) and is per-pack — today `ont:55b7f5c6adeeee2c` for `dataco`, `ont:11f8d5bddf4ed34c` for `hospital`. |
| `dataset_version` | `dataco@994b3c8d24049cc4+mapa85a911e567f73c2` | Data Adapter | Set 2026-08-30 by ADR-0035. Recipe: `<dataset_id>@<content_sha256[:16]>+map<mapping_digest[:16]>`. Legible rather than a single opaque digest, because the mapping participates in `run_id` THROUGH this value — `RunKey` is frozen and was not changed — so either half must stay recoverable. Full decomposition in `datasets/dataco.pin.json`. **Changed 2026-08-30 by ADR-0039**, whose emission rules moved `mapping_hash` from `map:7acd9e24866745fb` to `map:a85a911e567f73c2` — risk R-19 realised exactly as ADR-0035 predicted, on the first mapping edit after it. See risk R-19. |
| `mapping_version` | `1.1.0` | `ontology/packs/<domain>/mapping.yaml` | Set 2026-08-30 by ADR-0036, moved to 1.1.0 the same day by ADR-0039. Two numbers, as for the ontology: **`mapping_schema_version`** (`1.1.0`, additive — `event_emissions` defaults to empty, so a 1.0.0 mapping still loads) versions the DSL and is the same for every mapping; **`mapping_version`** is each mapping's own semver. `mapping_hash` = `digest(MAPPING, to_canonical_json(mapping))` — today `map:a85a911e567f73c2` for `dataco`. |
| `report_schema_version` | `1.0.0` | Data Adapter | The Data Quality Report's own shape. Bumping it invalidates comparison with reports written under a prior shape. Does NOT participate in `run_id`: the report describes a run, it is not an input to one. |
| `graph_projection_version` | `1.0.0` | Temporal Graph Builder | Set 2026-08-29 by ADR-0034. `gpv:` + `digest(run_id \| projection_content_hash)`. Derived from BOTH: from the run alone two builds would share a version and staleness would be undetectable; from the hash alone two runs that projected identically would share one. |
| `rule_pack_version` | `1.7.0` | `rule_engine/<domain>/rules.yaml` | **Set 2026-09-01 by ADR-0044.** semver; participates in `run_id` (ADR-0013), so editing any rule creates a new Run. Two numbers, as for the ontology and the mapping: **`rule_pack_schema_version`** (`1.0.0`) versions the DSL and is the same for every pack; **`rule_pack_version`** is each pack's own semver. `rule_pack_hash` = `digest(RULE_PACK, to_canonical_json(pack))` (ADR-0046) — **moved to 1.1.0 on 2026-09-02 by ADR-0049**, which added the `candidate_generation` namespace at `rule_pack_schema_version` 1.1.0 (additive; a 1.0.0 pack still loads and simply runs no generator that needs a declaration). `rule_pack_hash` moved `rul:f4aeace1280015c4` -> `rul:83fa4858d3cc0a4a` and **`run_id` moved with it**, which is ADR-0013 working as designed: declaring a proximity window is an input to the Run, not a free edit. **This was the last `unset` `RunKey` input**; every one of the five now has a real value. Coverage: 13 of 20 declared DataCo event types explained (65%) — `docs/reports/dataco/rule-coverage.md`. **Moved to 1.2.0 on 2026-09-03 by ADR-0053**, which added the `confidence_scoring` namespace at `rule_pack_schema_version` 1.2.0 (additive; a 1.1.0 pack still loads and simply scores no component that needs a declaration). `rule_pack_hash` moved `rul:83fa4858d3cc0a4a` → `rul:01eb1123f2d33de4` and **`run_id` moved with it** — declaring how to score is an input to the Run, not a free edit, which is R-19 realised exactly as ADR-0035 predicted and for the second time. The hospital pack moved 1.0.0 → 1.1.0 with deliberately DIFFERENT numbers, which is the LAW-DOMAIN check the split exists to make possible. **Moved to 1.3.0 on 2026-09-04 by ADR-0055**, which added the `graph_construction` namespace at `rule_pack_schema_version` 1.3.0 (additive; a 1.2.0 pack still loads and simply constructs an empty causal graph and says which policy did not run) and **deprecated `confidence_scoring.promotion_band`** — still parsed, no longer read, with a loader `WARNING` naming its replacement. `rule_pack_hash` moved `rul:01eb1123f2d33de4` → `rul:4115780e4b4b45ec` and **`run_id` moved with it**, to `run:244e3cf2d3f4300d` — R-19 realised as ADR-0035 predicted, for the third time. Declaring which claims the engine will stand behind is an input to the Run, not a free edit. The hospital pack moved 1.1.0 → 1.2.0 and disagrees with DataCo on every number, including the *direction* of one: it promotes `CONDITIONAL` at a LOWER band than `DIRECT`, on the argument that a qualified claim shows a reader its own scope. **Moved to 1.4.0 on 2026-09-05 by ADR-0057**, which added `confidence_scoring.derived_precedence_temporal_support` at `rule_pack_schema_version` 1.4.0 — the cap on `temporal_support` for a pair whose precedence the source COMPUTED rather than recorded. Additive, but NOT silently defaulted: absent, an edge resting on a confirmed derivation is NOT SCORABLE on that component rather than scored as though the precedence had been observed. `run_id` moved with it — R-19 for the fourth time, and the reason every committed report in `docs/reports/dataco/` was regenerated in that commit. `dataset_version` is unaffected, so no re-import was needed. The hospital pack moved 1.2.0 -> 1.3.0 and declares 0.02 against DataCo's 0.10. **Moved to 1.5.0 on 2026-09-06 by ADR-0063**, which added THREE namespaces at `rule_pack_schema_version` 1.5.0 — `propagation_analysis`, `root_cause_analysis` and `pattern_mining` — for modules 12 and 11 and the pattern miner. Additive and defaulted, ADR-0049's absent-means-CANNOT-RUN rule for the fourth time: a 1.4.0 pack still loads, traverses nothing, ranks nothing, mines nothing, and says which bound each would have needed. `rule_pack_hash` moved `rul:83fa4858d3cc0a4a` → `rul:29044a40bcab8ca5` and **`run_id` moved with it** — R-19 for the fifth time, and the reason every committed report under `docs/reports/dataco/` was regenerated in this commit. `dataset_version` is unaffected, so no re-import was needed. The hospital pack took the schema bump and declares NOTHING in the three new blocks, which is valid and is the second pack exercising the absent-means-CANNOT-RUN path rather than only the first. **Moved to 1.6.0 on 2026-09-07 by ADR-0071**, which added the `counterfactual_simulation` namespace at `rule_pack_schema_version` 1.6.0 for module 13 — depth, node cap, support tolerance, sensitivity perturbations and path composition. Additive and defaulted, ADR-0049's absent-means-CANNOT-RUN rule for the fifth time: a 1.5.0 pack still loads, simulates nothing, and says which declaration each policy would have needed. `rule_pack_hash` moved `rul:29044a40bcab8ca5` → `rul:b02ea6399b720f81`. **`ontology_hash` moved in the same commit** — ADR-0067 added `mutable` to `AttributeSpec` at pack schema 1.1.0 — so `run_id` moved for TWO reasons at once, which is R-19 for the sixth time and the reason every report under `docs/reports/dataco/` was regenerated. (Only the data-quality pair, `report.sha256` and `rule-coverage.*` are tracked by git today; the analysis reports are written to the working tree and have never been committed — see PROGRESS.md §00j.) `dataset_version` is unaffected by both, so no re-import was needed. The hospital pack took the schema bump and declares NOTHING in the new block, the third pack-level exercise of the absent path. **Moved to 1.7.0 on 2026-09-07 by ADR-0079**, which added the `recommendation` namespace at `rule_pack_schema_version` 1.7.0 for module 14 — the scalarizer name, one weight per objective, the cut-set exact ceiling and node cap, the set-size cap, the publication limit and the belief floor. Additive and defaulted, ADR-0049's absent-means-CANNOT-RUN rule for the SIXTH time. **`ontology_hash` moved in the same commit** — ADR-0073 added the `risk_classes` vocabulary and a `risk_class` per actionable event type at pack schema 1.2.0 — so `run_id` moved for TWO reasons at once for the second consecutive module, which is R-19 for the seventh time. That this is now unremarkable is the point of pinning it: the second occurrence of a hazard should be routine rather than a rediscovery. The hospital pack took the bump and declares NOTHING in the new block AND no `risk_class` on any of its four actionable types, so it exercises both halves of the absent path. |
| `engine_version` | `0.1.0` | `causalog.ENGINE_VERSION` | semver; bump on any change that can alter output for identical inputs |
| `postgres_schema_version` | `1.0.0` | `deployment/sql/migrations/` | Set 2026-08-29 by ADR-0032/ADR-0033. Fifteen paired migrations; the authority on what is applied is the `schema_migration` ledger, not this row. Does NOT participate in `run_id`: the schema decides how a fact is stored, never what it is. |

Rules:
1. `unset` blocks freezing. No interface may move to `frozen` while a contract it depends
   on is `unset`.
2. `ontology_hash` participates in the determinism guarantee (`CONVENTIONS.md` §3). Every
   output envelope carries the versions that produced it, plus `run_id`, `seed`, and
   `execution_id` (ADR-0013).
3. Version bumps are recorded in section 11 (Changelog) and, if breaking, in an ADR.

---

## 8. Open questions

Every row has a proposed default so work is never blocked on a missing answer — but a
default that is *used* must be promoted to an ADR before the dependent module is frozen.

| ID | Question | Proposed default | Cost if wrong | Unblocked by |
|---|---|---|---|---|
| ~~OQ-001~~ **RESOLVED 2026-08-23 by ADR-0006** | prd.md §36 (16 modules) and §44 (10 services) overlap with different names and no mapping. Which is authoritative? | §36 is the authoritative build/ownership unit; §44 are deployment groupings. Mapping table in §3 above. | **High.** Two sessions build the same component twice under two names; interface registry fragments; integration fails late. | ADR-0006 (accepted) |
| ~~OQ-002~~ **RESOLVED 2026-08-23 by ADR-0007** | LAW-TIME requires strict `cause.ts < effect.ts`, but DataCo timestamps are day-granularity, so ties are common and legitimate edges are silently discarded. | Interval timestamps `[t_earliest, t_latest]` + `precision` enum. `cause.t_latest < effect.t_earliest` ⇒ CERTAIN. Overlap ⇒ `UNDETERMINED`; edge is retained but blocked from promotion to `INFERRED`. | **High.** Either mass loss of true edges (strict `<` on tied days) or mass admission of false edges (loose `<=`). Both invalidate root-cause output. | ADR-0007, **superseded 2026-08-25 by ADR-0021**, which keeps every part of this answer and adds `INFERRED` timestamp provenance plus a required `source`. Retaining `UNDETERMINED` creates a new exposure: it may dominate on a day-granularity dataset — see R-14. |
| ~~OQ-003~~ **RESOLVED 2026-08-23 by ADR-0008** | Root Cause is defined twice: §12 ("could prevent downstream consequences") vs §29 ("would prevent the *largest* downstream impact"). Earliest and largest-impact disagree. | Adopt §29. Return two separate fields: `earliest_cause` (structural) and `actionable_root_causes` (ranked by impact-averted × confidence, tie-break earliest). | **High.** The headline output of the product means two different things to two modules; explanations contradict the ranking. | ADR-0008 (accepted). Actionability becomes ontology-declared and is stamped onto `Event` — see R-15. |
| ~~OQ-004~~ **RESOLVED 2026-08-23 by ADR-0001** | prd.md §42 splits Postgres (facts) / Neo4j (relationships) but names no source of truth and no sync mechanism. | Postgres is the system of record. Neo4j is a derived, rebuildable projection keyed by `ontology_version` + `dataset_version`. Direct writes to Neo4j are a defect. | **High.** Split-brain state; no transactional boundary; irreproducible graphs; determinism guarantee unenforceable. | ADR-0001 (accepted). *This row read as open until 2026-08-23 while §3 prose said it was resolved — a missed same-commit update, not a reopened question.* |
| ~~OQ-005~~ **RESOLVED 2026-08-25 by ADR-0009** | Confidence is a 0–1 float in §28 but LAW-EVIDENCE and §49 say a bare float is a defect. §20 additionally puts `Confidence` on `Event` itself, conflating extraction confidence with occurrence confidence and colliding with `OBSERVED` provenance. | `ConfidenceVector` with named components is authoritative; the scalar is derived and names the `aggregation` function that produced it, via a registry keyed by name. | **Medium-High.** LAW-EVIDENCE violated by construction; UI displays a number nobody can decompose. | ADR-0009 (accepted). *The proposed default kept a scalar on `Event` under the name `extraction_confidence`; the ADR rejects that half — LAW-EVIDENCE exempts no type, so `Event.confidence` is a full vector. The weights are an editorial judgement with no ground truth behind them: see the ADR's negative consequences.* |
| ~~OQ-006~~ **RESOLVED 2026-08-23 by ADR-0010, matcher spec SUPERSEDED by ADR-0019** | LAW-DOMAIN lint is underspecified: (a) `core/` is not in the §43 repo structure; (b) case-insensitive substring matching false-positives on `ordering`, `reorder`, `recorder`, `border`; (c) §21's own event ontology is exactly the banned vocabulary. | (a) `core/` is added; §43 amended by ADR. (b) word-boundary regex + explicit allowlist. (c) §21 is a *DataCo ontology instance* under `ontology/`; ontology and rule **data** files are exempt, `rule_engine` **code** is not. | **Medium.** A lint that cries wolf gets disabled, and LAW-DOMAIN then holds by convention only — which is exactly the failure it exists to prevent. **Realised, in the other direction:** ADR-0010's word-boundary matcher cried wolf about nothing and caught nothing (DEF-0001). | ADR-0010 for `core/` and the exemptions; **ADR-0019 for the matcher** — stem-prefix, no suffix exceptions |
| ~~OQ-007~~ **RESOLVED 2026-09-07 by ADR-0065** | prd.md §33 promises counterfactual simulation over a graph whose edges are rule/statistics-derived, not identified causal effects. §16 already concedes causality is not proven. | V1 ships graph-surgery propagation over frozen edges, labeled `SIMULATED`, surfaced as a **plausibility simulation** with its no-unobserved-confounder assumption printed in the output envelope. Not a causal effect estimate. | **Medium-High.** Overclaiming. A user acts on a simulated number that has no identification argument behind it. | **ADR-0065** (accepted). *This row, `docs/architecture.md` §2 and `PROGRESS.md` §13 all named a reserved decision number that was skipped at the 2026-08-23 scaffold and never written; three documents pointed at a decision that did not exist, and none of `check_governance_consistency.py`'s six rules could see it because every one fires on an ADR that DOES exist. A seventh rule closes that in this commit, and ADR-0065 records the gap rather than erasing it.* The default is adopted and **extended**: the support envelope, the extrapolation verdict, the sensitivity sweep and the enumerated assumptions are this project's addition and not a reading of the PRD — OQ-029. |
| ~~OQ-008~~ **RESOLVED 2026-08-23 by ADR-0003** | prd.md §38 requires determinism "when rules are explicit" while §41 lists pgmpy unqualified (DoWhy is marked future); `CONVENTIONS.md` §3 hardens this to byte-identical reruns. | V1 is fully deterministic (ADR-0003). Any nondeterministic component requires its own ADR and an explicit seed contract before introduction. | Medium. Determinism gate becomes unenforceable and silently drops out of the DoD. | ADR-0003 (accepted). *Second instance of the stale-row class that produced the OQ-004 slip: ADR-0003 answered this at the scaffold and the row was never struck. Now checked mechanically by `scripts/check_governance_consistency.py`.* Note the gate itself is still NOT-YET-RUNNABLE — see OQ-014. |
| ~~OQ-009~~ **RESOLVED 2026-08-25 by ADR-0025** | The module contract document ("Prompt 02") referenced by the Definition of Done does not exist. | The document is `docs/contracts.md`, versioned `1.0.0`; the four §7 schema versions are set; every `causalog.core` row moves to `frozen` and everything else stays `draft`. | Medium. Contracts get frozen by assertion rather than by specification. | ADR-0025 (accepted). *The freeze is early by design — nothing consumes these types yet, so it is frozen against anticipated rather than observed use. See the ADR's negative consequences.* |
| ~~OQ-010~~ **RESOLVED 2026-08-23 by ADR-0017** | Session ritual says `docs/prd.md`; the file is at `./prd.md`. | The file moved to `docs/prd.md`; the ritual is now correct as written. | Low, but caused a failed read at the start of every new session. | ADR-0017 (accepted) |
| OQ-011 | Phase grouping (P1–P5) in §3 is proposed by this document, not stated in the PRD. | Adopt as shown: P1 Ingestion (1–4), P2 Graph (5–8), P3 Inference (9–12), P4 Simulation (13–14), P5 Surface (15–16). | Low. Sequencing only; no contract depends on it. | Product owner ruling |
| ~~OQ-012~~ **RESOLVED 2026-08-23 by ADR-0020** | `Trigger` is a required `Event` field in §20 but is never defined, and collides with `Cause`. | `Trigger` = the proximate mechanism recorded *on* the event (intrinsic, `OBSERVED`). `Cause` = an inferred edge *between* events. See `GLOSSARY.md`. | Medium. Two fields mean the same thing; agents populate them inconsistently. | ADR-0020 (accepted). Inference may never read `Event.trigger`. |
| OQ-016 | The LAW-DOMAIN lint reads only `.py`, `.md`, `.sql`, `.cypher`, and still cannot catch domain dependence expressed as a branch on a data *value* rather than as vocabulary (ADR-0019). | Keep both residuals disclosed in `docs/architecture.md` §1.5 rather than implied. The value-branch hole is covered — imperfectly — by the planned ontology-swap test, not by any lint. | Medium. A green LAW-DOMAIN job is not proof of domain independence, and DEF-0001 showed how readily a green job is mistaken for one. | `tests/ontology/test_ontology_swap.py`, which still needs a pipeline that produces an output to compare — the mapping seam landing in module 2 supplies the second data file a swap replaces and settles nothing about this question. **Half-covered 2026-08-28** by `tests/ontology/test_pack_is_not_domain_shaped.py`: two unrelated domains load through one code path and share no behavioural vocabulary, which proves the *schema* is domain-neutral. That a swap changes engine *output* still needs a pipeline. |
| OQ-014 | The determinism gate cannot run: `scripts/check_determinism.py` exits 2 (`NOT-YET-RUNNABLE`) because no orchestration pipeline entry point exists, and its CI job is `continue-on-error` for that reason alone. **Partially unblocked 2026-08-28:** `ontology_hash` exists (ADR-0028). **Further unblocked 2026-08-30:** `dataset_version` is now set (ADR-0035), so every `RunKey` input except `rule_pack_version` has a real value. **Fully unblocked on the inputs side 2026-09-01 (ADR-0044):** the DataCo rule pack sets `rule_pack_version`, so all five `RunKey` inputs now have real values and the remaining blocker is the orchestration entry point alone, not a missing contract. Module 1 additionally ships its OWN determinism test — `tests/determinism/test_data_quality_report_is_stable.py` asserts byte-identical report, clean layer and quarantine across two imports, and invariance to batch size — so determinism is proved for this module while the whole-pipeline gate still cannot run. | Keep the script reporting the gap loudly rather than exiting 0. Remove `continue-on-error` at the P1 exit, when the pipeline first runs end to end. | **Medium.** A gate that cannot run looks identical to a gate that passes, and `CONVENTIONS.md` §3 lists determinism as a Definition-of-Done item for every module. | The orchestration pipeline (P1 exit) |
| OQ-015 | `docs/architecture.md` §1.2 and `scripts/check_layers.py` hold two copies of the layer-rank table, as `CONTEXT.md` §2 and `CONVENTIONS.md` §1 do for the Five Laws. Only the Laws have an automated copy check. | `tests/law/test_layer_boundaries.py` asserts every ranked package name appears in the document, which catches a removal but not a changed rank. Strengthen to a parsed comparison if the tables ever disagree in practice. | Low-Medium. A silently divergent rank table means the document teaches a rule the build does not enforce. | A stricter check, or a single generated source |
| OQ-017 | `recommendation` and `counterfactual_scenario` are stored as run-scoped envelope columns plus a `payload jsonb`, because `Intervention`, `SimulatedWorld`, and `RootCauseRanking` are all `draft` and modules 13–14 do not exist. | Normalize into real columns when those modules freeze their types. Until then the canonical JSON carries its own `schema_version` and is re-validatable on read. | **Low-Medium.** A jsonb payload cannot be joined, constrained, or indexed by field, so any query over intervention cost or mutation shape is a full scan until the normalization lands. If that query arrives before module 14, the normalization is pulled forward rather than worked around. | Modules 13 and 14 freezing their contracts |
| OQ-018 | prd.md §55 says "dataset loading < 30 seconds" and does not say what is being loaded. ADR-0029 declares one OBSERVED event type and twenty DERIVED ones for DataCo, so the two readings — 180 519 source rows, or ~3.8 million materialized events — differ by a factor of twenty-one. | Measure and report **both**, and assert the budget against the smaller claim (observed rows). `tests/integration/test_bulk_load_budget.py` prints both figures on every run. | **Medium.** The two readings are a passing budget and a badly failing one. Choosing silently would either overstate compliance or condemn a design that meets the requirement as written. | A product-owner ruling on which reading §55 intends |
| OQ-019 | The Data Adapter reads the reference file **twice** (ADR: two exact passes rather than one approximate one), and the measured wall clock for the full import is ~105 s against the `prd.md` §55 "dataset loading < 30 seconds" budget. That budget is already contested by OQ-018, which asks what "dataset loading" even counts. | Report the measurement and do not tune it away. The two passes buy exact quantiles and a correct orphan-key check, both of which a single pass cannot give without sampling (forbidden, `CONVENTIONS.md` §11) or without calling a forward reference an orphan. Revisit only when OQ-018 settles what the budget measures. | **Medium.** Two budgets are now measured and both miss (R-17 for persistence, this for ingestion), and nobody has ruled on what §55 counts, so neither miss can be called a failure or a pass. | A product-owner ruling on OQ-018 |
| OQ-020 | Module 3 versions entity attributes over time and **the store cannot hold the versions.** `entity_attribute` is keyed `(entity_id, attribute_name)` and holds one value per attribute (migration 0007), so an attribute that took two values across the dataset is storable only as whichever value the `ConflictPolicy` resolved to. | Keep the history as an in-memory artifact of the run and report it, which is what module 3 does today. Normalize `entity_attribute` into a versioned table when an orchestration pipeline first needs to persist one. | **Medium.** The history exists, is deterministic, and is discarded at the end of every run. Any question of the form "what did we believe about this participant, and when" is unanswerable from the store until this lands — and bi-temporal storage (ADR-0032) already answers exactly that shape of question for `State`, so the asymmetry is a gap rather than a design. | An orchestration pipeline that persists extraction output (P1 exit) |
| OQ-021 | The pack's declared bases for `PAYMENT_FAILED`, `ORDER_HELD` and `PAYMENT_REVIEW_OPENED` are **not separable in this dataset**: all three are satisfied by an `ON_HOLD` status and no column records which state an order arrived from. All three fire, so occurrences on those records are over-counted. `ORDER_RELEASED`'s basis needs a history the source does not carry at all, so it can never be witnessed. | Transcribe each basis faithfully and report the overlap, which is what ADR-0039 does. Choosing one in the mapping would be a domain judgement written into a data file — the shape of error R-16 describes — and the pack's own default confidences (0.6, 0.7, 0.8) already express the uncertainty. | **Medium.** Any count of held orders is inflated by roughly three, and any propagation measure that walks all three will double-count. The inflation is disclosed in the Event Quality Report and is a property of the pack, not of the generator. | A pack author's ruling, or a source that records state history |
| OQ-022 | **Three attributes the DataCo pack declares at one granularity are recorded at another, measured over the reference file and not predicted.** `ORDER.order_profit` and `ORDER.order_benefit` come from `Order Profit Per Order` and `Benefit per order`, which VARY BETWEEN THE LINES OF ONE ORDER in 4,773 of the first 12,203 orders — they are line figures wearing order names. `MARKET_REGION` is keyed on `(Market, Order Region)` and the pack gives it `destination_city`/`destination_state`/`destination_country`, which are address-level, so 23 region entities carry 46,575 disagreements between them. | Report, do not repair. Module 3 records every disagreement with both values and both citations; module 4 splits an occurrence whose recorded attributes differ, because merging would discard a value silently. Moving `order_profit` to `ORDER_ITEM` and the destination attributes to their own entity type is a **pack** change: it is a claim about the domain, an `ontology_hash` change, and therefore an ADR by whoever owns the pack — not an edit made by the module that noticed. | **Medium-High.** The order-level pair is the more serious: because `order_profit` is a required attribute of `ORDER_PLACED`, it reaches `changed_attributes`, and one placement therefore becomes several events — 19,997 `ORDER_PLACED` events for 12,203 orders in the measured slice. Any downstream count of placements is inflated by roughly 64%, and any monetary roll-up over `ORDER.order_profit` reads one line's figure as the whole order's. | A pack owner's ruling, as a new ADR that re-declares the three attributes at the granularity the source records them |
| OQ-023 | **Module 9's report is measured over a 150-row slice, not over the dataset, and the gap is three orders of magnitude.** Module 9 is not a streaming module: the historical-frequency and statistical-association generators measure across process instances and the confounder walk needs the graph in hand, so the whole run must be resident. The reference expansion is ~3.8 M events and does not fit in memory as models (`tests/integration/test_full_expansion_budget.py`). Compounding it, DEF-0005's fix makes evaluation over a type pair with unplaced consequents quadratic — 20,328 firings from 1,224 events — so the cost grows faster than the row count. | Report the slice, label it a slice in the artifact itself, and do not present it as a dataset measurement — which is what `scripts/build_candidate_graph.py` does, printing the bound on stdout and stamping a BOUNDED RUN banner into the report. Removing the bound is `--rows 0` for anyone with the memory. | **Medium-High.** Every number in the Candidate Graph Report — the `UNDETERMINED` share, the unverifiable share, the per-generator counts, the flag density — is a property of 150 rows. The unverifiable share in particular may move sharply with scale, and R-14's severity is currently known only at this size. Reading the slice as the dataset would be exactly the overclaiming this project exists to avoid. | An orchestration pipeline that can page the candidate graph, or a generator set that streams. Both are post-P3. |
| OQ-024 | **The confidence scores are internally consistent and are NOT calibrated, and nothing in this repository can make them calibrated.** Calibration means claims scored 0.8 are right about eighty per cent of the time; measuring it needs labelled causal ground truth — pairs where someone independently established what actually caused what. DataCo carries no causal annotation, no fixture set of known causes exists, and prd.md §16 already concedes causality is not proven. So no reliability curve can be drawn, no error rate can be quoted, and `V2_ADDEND_WEIGHTS` was written down rather than fitted because there was nothing to fit it against. | State it, before any number, in the artifact itself — which is what `NOT_CALIBRATED_NOTICE` does as the confidence report's first section, as fixed text that cannot be softened per run. Ship the diagnostics that ARE computable without labels: the distribution, which gate bound each score, which components are missing, which components distinguish nothing, and whether the top of the ranking is a plateau at a ceiling. | **High.** A decomposed, well-explained, reproducible number is much more persuasive than an undecomposed one, and persuasiveness is not accuracy. The decomposition makes the score auditable; it does not make it right, and a reader who sees eight components and a plain-language band is MORE likely to trust it than one who sees a bare float. That is the specific way this module could do harm. | A labelled evaluation set. Either a hand-built one over a synthetic domain — which would measure the implementation and say nothing about DataCo — or a real one, which needs a domain expert and is outside V1. prd.md §57's evaluation metrics presuppose it. |
| OQ-013 | Intervention requires `Estimated Cost` (§32, §50) but DataCo carries no cost data. | Cost is ontology-supplied configuration, never inferred. Default to an ordinal scale (`LOW`/`MEDIUM`/`HIGH`) with provenance `ASSUMED`. | Medium. A fabricated cost silently drives the recommendation ranking. | ADR; must precede module 14 |
| OQ-025 | **prd.md §36 names no module that owns §25 (the causal graph), §26 (the edge taxonomy) or §31 (feedback loops).** Module 9 proposes candidates, module 10 scores them, and modules 11 and 12 both consume a graph they assume already exists. The assembly step between 10 and 11 — deciding which scored claims become the system's stated view, typing them, weighting them, detecting loops — has no owner in the authoritative build unit (ADR-0006). | Build it as a package that is **not** one of the sixteen, exactly as the ontology layer and the rule engine were built (ADR-0054), and amend §36 to name it rather than renumbering modules 11–16. Renumbering would rewrite the §36↔§44 mapping ratified by ADR-0006 and every prompt, table and ADR that cites a module number, to buy nothing. | **Medium.** §36 is the authoritative unit of build, ownership, test and gate. A third package that is "not a module" is a precedent, and a fourth would mean §36 has stopped describing the system — at which point the module table and the code disagree, which is the OQ-004 / DEF-0004 class in a new place. | A product owner's ruling on amending prd.md §36. Not blocking: the package is built, tested and reported, and only its *listing* is unresolved. |

---
| OQ-026 | **The `UNPROMOTED_DIAGNOSTIC` standing publishes a second artifact that looks like an analysis and is not one.** ADR-0059 defends it with four structural mechanisms — a required field, one construction site, a validator refusing `INFERRED`, and a fixed notice held as a property — and none of them survives a screenshot. Somebody will quote a diagnostic figure without its notice. | Keep the two in separate files, keep the notice above every table, and require modules 13 and 14 to REFUSE a diagnostic input when they are built. Revisit if the diagnostic reports are ever cited outside this repository. | **Medium.** A disowned number read as a finding is exactly the overclaiming prd.md §17 and R-11 exist to prevent, arriving through a door this project opened deliberately. | The stated graph becoming non-empty — i.e. modules 7 and 8, or a source with observed instants |
| OQ-027 | **A plateau is reported, and nothing says what a consumer should DO with one.** 310 scored links sit at exactly 0.400000, so under `weakest_link_v1` many chains compose identically and the recommended set is frequently unsequenceable. Modules 11 and 12 say so; the API and the interface have no stated behaviour for it. | Present tied candidates as an explicitly unsequenced SET rather than as a list with an arbitrary first row. Do not break the tie on earliness — that would reintroduce ADR-0008's blend by the back door. | **Medium.** An interface that renders a tie as a ranked list makes the engine appear to have chosen, which is the one thing the plateau notice exists to deny. | Module 16 |
| OQ-028 | **The pattern miner enumerates motifs of length two only**, against a `motif_maximum_length` the pack declares and nothing reads. The report says so rather than implying longer shapes were searched for and not found, but the declaration is currently a number with no consumer — the shape ADR-0055's `_check_shape` refuses elsewhere. | Either implement longer enumeration behind the declared bound, or remove the field until something reads it. Do not leave a declared bound unread past the next release of the miner. | **Low.** A pack author reads `motif_maximum_length: 4` and believes four-step motifs are being looked for. The report contradicts them, but the pack does not. | Whoever next touches the miner |
| OQ-029 | **Module 13's rigour EXTENDS the PRD and was not asked for.** The document uses the words *provenance*, *validity*, *extrapolation* and *sensitivity* exactly zero times. Principle 5's assumption enumeration binds **recommendations**, not counterfactuals; §32's six-field intervention record omits assumptions too; §51 Workspace 5 is the only workspace showing derived numbers that asks for no confidence display. So the support envelope, the `EXTRAPOLATION` verdict, the sensitivity sweep and the enumerated assumption list are this project's addition. | Ship them, and record here that they are an addition rather than a reading, so a product owner ratifies or trims them deliberately (ADR-0065). The alternative — shipping a bare simulated number because the PRD asks for no more — is the overclaiming prd.md §17 exists to prevent. | **Medium.** Scope the PRD does not authorise, carried in a module the PRD does authorise. If trimmed, the removal is four fields on one artifact and the tests that assert them; nothing else depends on it. | A product owner's ruling |
| OQ-030 | **prd.md §57 names "counterfactual plausibility" as an evaluation metric and defines it nowhere, and nothing in this repository can compute it.** §56's "counterfactual consistency" is defined here as the three properties `CONVENTIONS.md` §14 lists and is tested; plausibility is a claim about whether a simulated answer resembles what would really have happened, which needs labelled ground truth. | State it in the report's closing section, which is what module 13 does. Do not invent a proxy: a number named "plausibility" that measured internal consistency would be read as the thing §57 asks for. | **Medium-High.** OQ-024's shape one layer up, and worse: a simulated figure reads like a measurement of a thing that did not happen, so a plausibility score attached to it would be doubly persuasive and equally unfounded. | The same labelled evaluation set OQ-024 needs |
| OQ-031 | **prd.md §51 Workspace 5 asks for no confidence display and no simulated-versus-observed distinction**, while §37 requires that distinction "in the implementation or the user interface". Workspaces 3 and 6 both specify a confidence display; Workspace 5 does not. | Treat §37 as governing and §51 as underspecified. Module 13 holds the distinction structurally — a simulated world contains no `Event` and no `TimeInterval` (ADR-0068) — so the API physically cannot serialize one as the other. What the UI does with that is module 16's. | **Medium.** A workspace built to §51 as written would render a simulated figure exactly like an observed one, which is the conflation §37 forbids, in the place §37 names first. | Module 16, and a product owner's ruling on §51 |
| OQ-032 | **prd.md §52's own worked example commits the conflation §37 forbids.** "The shipment delay originated from an inventory shortage detected at Warehouse W12 … Historical evidence indicates similar chains in 84 previous orders … Earlier inventory reconciliation would likely reduce delivery delay by approximately 11 hours" puts an observed fact, a statistical association and a counterfactual simulation in one undifferentiated paragraph, with "likely" and "approximately" carrying the whole epistemic load. | Do not reproduce the example's SHAPE when module 15 is built. Every sentence must carry its own provenance class, and a simulated figure must carry its validity verdict rather than an adverb. | **Medium.** The PRD's most quotable paragraph is a template for the failure the PRD elsewhere forbids, and module 15 will be written by someone reading it. | Module 15 |


## 9. Known risks and current mitigations

Risks are prd.md §59 plus risks introduced by the execution model. "Current mitigation"
means *what is in force today* — `NONE YET` is an honest and expected value at P0.

| ID | Risk | Current mitigation | Owning module | Status |
|---|---|---|---|---|
| R-01 | Incomplete timestamps | Interval + precision representation (`CONVENTIONS.md` §10) with the three-valued `TemporalVerdict`. Never impute; missing ⇒ `UNKNOWN` precision, `ASSUMED` provenance, and barred from any `INFERRED` edge. **Enforced at the layer where a source string first becomes an instant:** the mapping DSL refuses to declare `EXACT` precision, `PRECISION_SPANS` holds only entries that widen, and `tests/law/test_cleaning_never_imputes_time.py` enumerates the transform registry rather than sampling it. | Event Generator; Data Adapter | **in force (ADR-0021, superseding ADR-0007)**; `TimeInterval` enforces its own invariants and module 1 now builds them |
| R-14 | **`UNDETERMINED` dominance.** ADR-0007 retains temporally ambiguous edges rather than guessing, so most candidate edges may be unpromotable and the causal graph correspondingly thin. **The stated premise was wrong and the risk survives it (DEF-0004):** the reference dataset is not day-granular. `order date` is minute-granular; `shipping date` is bound to DAY not because it is coarse but because its minutes are manufactured (R-20). | **Now measured at module 9 itself, and it is worse than the 2.81% the Data Adapter predicted — for a reason that row could not see.** The adapter measured ROWS where one declared precedence pair is inseparable: 5,080 of 180,519 (2.81%). Module 9 measures CANDIDATES, over all twenty-one event types, and the first bounded run reports **14.5% `UNDETERMINED`** and — separately, and much larger — **84.1% temporally unverifiable**: the data never placed one of the two events at all. Only **254 of 17,864 candidates (1.4%)** are promotable to `INFERRED`. The dominant term is not ambiguity between placed instants, it is ABSENT instants, which is a consequence of ADR-0029's twenty DERIVED event types rather than of granularity. The two counts are reported separately and never summed (`docs/contracts.md` §3). Disclosed, never tuned away by loosening the test. | Candidate Cause Generator | **accepted and OPEN; measured at module 9 on 2026-09-02.** The severity is now known and is high |
| R-15 | **Mis-declared actionability. NOW LOAD-BEARING IN TWO PLACES, as of 2026-09-06.** ADR-0008 ranks root causes on an ontology-declared `actionable` flag; a wrong flag silently changes the headline ranking and nothing in the system can detect it. **ADR-0062 added a second surface:** a mis-declared `cost_class` now changes which lever `most_actionable_cause` offers first, and that is equally undetectable. Module 11 prints the caveat above every ranking as a property no revision can soften, and reports every stamp-versus-pack disagreement without resolving it — both are disclosure, neither is mitigation. | Same treatment as OQ-013's cost: provenance `ASSUMED`, inspectable, surfaced in explanations. No ground truth exists to validate it against. | Root Cause Analyzer | accepted; revisit if ranking disputes recur |
| R-16 | **A pack that validates cleanly can still be semantically wrong — and now a MAPPING can too.** ADR-0002 predicted it: a bad ontology produces silently wrong causality rather than a crash. The loader checks that references resolve and state machines are well-formed; nothing checks that a declared transition matches how the business works, that a `derivation.basis` is sound, or that an actionability flag is true. In the DataCo pack this covers twenty derived event types and their default confidences. | Disclosed, not mitigated — no procedure could check it, because there is no ground truth. Partially bounded: every derivation names its basis in the pack, every attribute names its origin, the manifest says it is unverified, and the loader's warnings are non-fatal precisely so they are read rather than tuned away. **Widened 2026-08-30 by ADR-0039:** nineteen emission rules are nineteen more places a declaration can validate and be wrong, and nothing mechanically compares a rule to the prose basis it transcribes. Bounded the same way and no better — the two are kept in separate files so a human can read them against each other, and mapping coverage reports every derived emission at `NOT_RUNNABLE` rather than clean, so the unchecked thing is visible rather than absent. | `ontology_runtime` and `schema_mapper` (surface); every consumer (effect) | accepted 2026-08-28 (ADR-0026, ADR-0029), widened 2026-08-30 (ADR-0039); revisit on labelled ground truth |
| R-17 | **The prd.md §55 load budget is not met on the measured configuration.** The persistence path takes ~33–41s for the reference dataset's 180 519 events against a 30s budget. Measured, not estimated. | Disclosed, not tuned away. The benchmark asserts the budget and currently FAILS, which is the correct signal: `LOAD_BUDGET_SECONDS` is a product requirement, and raising it until the test goes green would convert a known miss into an unknown one. What has been tried is recorded with numbers in `PROGRESS.md` §00d. What has NOT been tried is the deployment configuration — the measurement is against a local PostgreSQL 14 with default server settings, and the target is the pinned PostgreSQL 16 in the compose stack, which this machine cannot start. | `persistence` (surface); Data Adapter (caller) | **accepted and OPEN as of 2026-08-29.** Revisit on the first measurement against the deployment configuration. |
| R-18 | **A performance path can enforce less than the correctness path, invisibly.** Observed, not hypothetical: the first bulk loader wrote `confidence_component` and silently skipped `confidence_component_evidence`, so LAW-EVIDENCE's audit hook held for small loads and stopped holding at exactly the scale where it matters. | Fixed, and then made structural: `tests/integration/test_bulk_load_budget.py::test_the_bulk_path_stores_exactly_what_the_row_path_stores` loads identical artifacts through both paths into two databases and compares all twelve tables. A future divergence fails there rather than in production. | `persistence` | **in force as of 2026-08-29** |
| R-02 | Missing events | **Partly in force, one layer earlier than expected.** Module 4 measures process coverage per definition and per step, separating a step absent from ONE instance from a step **no record can ever witness** — the second bounds every conclusion drawn around it and would otherwise be buried inside the first. ADR-0040 makes the default `RECORD_GAP`: nothing is fabricated, and the gap is reported. Timeline gap markers and the explanation requirement remain module 5's. | Timeline Builder; Event Generator (coverage) | **partly in force as of 2026-08-30 (ADR-0040)** |
| R-03 | Conflicting business rules | Rules are data, not code (prd.md §46). Conflict detection at rule-load time; a conflict is a load error, not a runtime coin-flip. `RuleConflictError` exists in the `core/errors.py` taxonomy; the detection does not. | Rule Engine | error type only |
| R-12 | **Projection rebuild on the critical path.** Neo4j being derived means graph availability is bounded by rebuild time, against the prd.md §55 target of graph generation under 60s. | Accepted, not mitigated. Rebuild stages into a new namespace and swaps atomically, so a slow rebuild degrades freshness rather than availability. | Temporal Graph Builder | accepted; revisit on the first measured rebuild over 60s |
| R-13 | **Recall bounded by rule coverage, silently.** A causal relationship not expressible as a rule is missed, and the system cannot report what it missed (ADR-0003). | **Narrowed, not closed, 2026-09-02.** Module 9 runs six generators BESIDES the rule-based one, so a relationship no rule expresses can still be proposed on temporal proximity, a shared participant, recurrence, or measured association — and the Candidate Graph Report shows what each contributed. On the first measured slice the rule-based generator supplied 2,297 of 17,864 retained candidates (12.9%), so rule coverage bounds one generator rather than the graph. What is NOT closed: no generator reaches a relationship the ontology declares no event type for, and nothing can still report what was missed. No metric can measure it — this dataset has no causal ground truth. | Candidate Cause Generator | accepted, narrowed 2026-09-02; revisit on labelled ground truth |
| R-04 | Noisy data | **In force.** 24 registered validation rules, each with a severity and a required `downstream_consequence`. Ontology violations are `ERROR` and quarantine the row with its reasons; statistical anomalies are `WARNING` and are carried forward untouched. `rows_read == rows_clean + rows_quarantined` is asserted and the run raises rather than publishing a report whose arithmetic disagrees with itself. Measured on the reference dataset: 0 quarantined of 180,519. | Data Adapter | **in force as of 2026-08-30** |
| R-19 | **A changed mapping re-scopes observed facts.** ADR-0035 folds `mapping_hash` into `dataset_version` rather than into the frozen `RunKey`. Observed facts are dataset-scoped (ADR-0013), so re-mapping now looks to the store exactly like a changed source file. | Disclosed, not mitigated — it is the accepted cost of the product owner's choice between three options, all of which are recorded in ADR-0035. Bounded by making the composite LEGIBLE: either half is recoverable by eye or by `str.split`, and `datasets/<id>.pin.json` carries both in full. The observed-fact store will hold one copy per (file, mapping) pair rather than one per file. **REALISED 2026-08-30, on the first mapping edit after the ADR:** ADR-0039's emission rules moved `mapping_hash` to `map:a85a911e567f73c2`, so `dataset_version` moved to `dataco@994b3c8d24049cc4+mapa85a911e567f73c2`, the file was re-pinned and re-imported, and a second Data Quality Report directory now exists for byte-identical source bytes. The cost is exactly what the ADR said it would be, which is the one thing that went to plan here. | Data Adapter; every consumer of `dataset_version` | **accepted and OPEN as of 2026-08-30; realised the same day** |
| R-20 | **Manufactured precision.** A source column can carry more precision than it observed. In the reference dataset `shipping date (DateOrders)` displays a minute and equals `order date` plus a recorded day count, to the minute, in 94.61% of rows. A coarse column announces its limits; a column that displays `22:56` because a different column said `22:56` does not. | Mitigated where declared, undetectable where not. `mapping.yaml` may declare a `temporal_derivation_check`, which the adapter MEASURES over every row and reports with its agreement rate and residual histogram; the DataCo mapping binds the affected column at DAY precision on the strength of that measurement, and the report carries it as a headline constraint. **Nothing finds an UNDECLARED derivation** — a mapping author has to suspect it first. | Data Adapter (surface); Candidate Cause Generator (effect) | **accepted 2026-08-30 (ADR-0038, DEF-0004)** |
| R-05 | Hidden confounders | **Partly surfaced as of 2026-09-02 (ADR-0051), still unmitigated.** Module 9 detects two structures in the candidate graph — `POSSIBLE_MEDIATION` and `POSSIBLE_COMMON_CAUSE` — and flags them as a separate artifact that removes and down-weights nothing. This LOCATES the possibility instead of only asserting it in prose, which is what prd.md §59's "explicitly surfaced" asks for. **It sees only OBSERVED common causes**, so a run with zero flags has learned nothing about the hidden ones this row is actually about, and every flag says so. The first measured run also shows the other limit: 3.84 flags per candidate, at which density a flag is a property of a dense graph rather than a finding about a claim. The blanket no-unobserved-confounder statement on every `INFERRED`/`SIMULATED` output remains required. | Candidate Cause Generator (surface); Confidence Scorer | partly in force 2026-09-02; see OQ-007 |
| R-06 | Correlation mistaken for causation | **In force at the point the association is first computed, as of 2026-09-02.** LAW-PROVENANCE separates `STATISTICAL` from `INFERRED` and promotion is never silent; `GLOSSARY.md` disambiguates the terms. Module 9's statistical-association generator now carries the separation structurally: every item it mints is `STATISTICAL`, and every one carries `ASSOCIATION_DISCLAIMER` verbatim — fixed text, so it cannot be softened per candidate — stating that lift establishes no causation, **no direction** (lift is symmetric; a candidate's direction comes only from the LAW-TIME gate), no freedom from confounding, and no significance. Its `verification` carries all four contingency cells so a reader recomputes rather than trusts. | Candidate Cause Generator; Confidence Scorer | **in force end to end as of 2026-09-03.** The scoring half landed with module 10: `statistical_support` is its own named component carrying `STATISTICAL` provenance that is never promoted to `INFERRED` however large the number (ADR-0003), it names the measure it computed rather than implying one, it carries `ASSOCIATION_DISCLAIMER` verbatim, and it states that no p-value was computed and no null tested. `ConfidenceVector.provenance_class` takes the WEAKEST component class, so an edge resting on association is `STATISTICAL` whatever its scalar. On the measured slice **zero** edges were promoted to `INFERRED`. |
| R-07 | Ontology mismatch | **In force.** `unmapped_value_policy` admits exactly one value, `ERROR`; an unmapped source value quarantines the row and is never passed through or defaulted. Coverage is assessed against the resolved pack and every miss is an `OntologyMappingError` naming what it breaks. An unlisted source column is a hard error. `ontology_hash` and `mapping_hash` both travel in `dataset_version`. | Schema Mapper | **in force as of 2026-08-30 (ADR-0036)** |
| R-08 | **Cross-session context loss / silent contradiction** | These six governance files; the session ritual; the same-commit doc rule; `HANDOFF.md` staleness checks. | — | **in force as of 2026-08-23** |
| R-09 | Determinism erosion (unsorted iteration, float drift, random IDs) | Content-addressed IDs, canonical sort keys, quantized float serialization (`CONVENTIONS.md` §8). `PYTHONHASHSEED=0` in the Makefile, every CI job, and the backend image. `scripts/check_determinism.py` exists but **cannot run yet** — see OQ-014. | all | partially in force; gate NOT YET RUNNABLE |
| R-10 | Domain leakage into the reasoning core | LAW-DOMAIN lint (`scripts/check_domain_independence.py`, **stem-prefix** matching + exact-match allowlist + two-table self-test with a re-poisoning guard; `ontology_runtime` added to its scope by ADR-0026 — the one package built to keep the domain out was the one package not being checked for it) **and** the layer lint's forbidden edge F3 (no reasoning package may import the ontology; a self-import false positive in F3 was fixed in the same commit, having been unobservable while `ontology_runtime` was empty). Narrowed by `scripts/check_metrics_are_declared.py` (ADR-0030, ADR-0031), which refuses two classes of value-level leakage — a domain metric recomputed in engine code instead of read from the pack's declared `MeasurementExpression` tree, and a threshold on one hard-coded there — over the AST, with intra-scope taint tracking so a metric reaching the arithmetic under an unrelated name is still caught. Exits 2 NOT-YET-RUNNABLE while the reasoning packages are scaffold. Residual: none of the three catches a branch on a data *value* — see `docs/architecture.md` §1.5. | all core modules | **in force as of the ADR-0019 fix.** It was NOT in force between the scaffold landing and DEF-0001: this row claimed "in force as of 2026-08-23" while the shipped matcher caught only the bare English word in a comment. The claim is left visible here rather than overwritten. |
| R-11 | Overclaiming in the UI | Provenance classes visually distinct; "plausibility simulation" wording for counterfactuals. | Visualization API | proposed, see OQ-007 |
| R-21 | **The rule engine cannot evaluate the reference dataset.** Two defects, found by running the DataCo pack against DataCo facts after seam 4's gate passed green. **DEF-0007:** `FactIndex.admissible_slice` raises `OverflowError` on any `UNKNOWN`-precision event, because `cause_earliest - span` underflows when `span` is the ~9999-year width of an unplaced interval — while the method's own docstring specifies that this case must "degenerate to zero and scan from the start". Prose and code disagreed and nothing compared them. 13 of 18 emitted DataCo event types are 100% `UNKNOWN`. **DEF-0008:** clamping to the documented behaviour trades the crash for a cross product — 12,494 events emit 1,855,405 firings, 99.8% of them `temporally_unverifiable`, because an event that could have occurred at any instant is admissible against every candidate in its linkage. This is R-14 (`UNDETERMINED` dominance) arriving at its full size: not 2.81% of rows, but the majority of the graph. | **Disclosed, not fixed.** Recorded in `PROGRESS.md` §04a with a two-event reproduction. Not fixed in place because the cheap fix for DEF-0007 is precisely what produces DEF-0008, so the choice between "scan the bucket and flag every pair unverifiable" and "refuse an `UNKNOWN` antecedent outright" is an evaluator guarantee and needs an ADR. Bounded meanwhile by the fact that **no consumer exists** — module 9 is not built and the only caller of the loader is `scripts/check_rule_pack.py`, which validates without evaluating. The engine's own honesty holds: every affected firing sets `temporally_unverifiable` and the statistics are returned, not logged. Not caught by the suite because `tests/fixtures/facts.py::interval` hardcodes `OBSERVED` provenance and `TimeInterval` refuses `UNKNOWN`+`OBSERVED`, so **no rule-engine test can construct the input that breaks it** — the DEF-0001 shape, relocated into a fixture. | Rule Engine (surface); Candidate Cause Generator (effect) | **accepted and OPEN as of 2026-09-02.** Closing it is an ADR + an `engine_version` bump; the missing `UNKNOWN`-precision fixture lands with it. |

---

| R-22 | **An INFERRED timestamp can never yield a CERTAIN verdict, and on this dataset the most important causal link has one.** Measured by hand on 2026-09-04, not predicted. `causalog.core.temporal.verdict` returns `CERTAIN` only when the intervals are strictly separated **and** neither endpoint's timestamp provenance is `INFERRED` (ADR-0021). For order `41304`, `SHIPMENT_DISPATCHED` sits at `2018-02-03` and `SHIPMENT_DELIVERED` at `2018-02-06`: `strictly_before` is **True**, the bounds are three whole days apart, and the verdict is still `UNDETERMINED` — because DataCo records no arrival timestamp, so `SHIPMENT_DELIVERED.occurred_at` is arithmetic (`dispatched_at + actual_shipping_days`) and carries `INFERRED`. Across the 150-row slice **not one of the 1,224 events carries an `OBSERVED` timestamp**: 789 `ASSUMED`, 435 `INFERRED`. Every pair whose effect is a derived occurrence is therefore permanently barred from promotion. | **Disclosed, not fixed, and not a defect.** ADR-0021 is working exactly as designed — an inference standing on a computed instant is an inference standing on arithmetic, and treating it as established precedence is the overclaiming this project exists to avoid. What was never measured before is the *size* of the consequence, because nothing had ever tried to promote: this is the reason the stated causal graph is empty, and it is a sharper statement than R-14's "day granularity". More rows cannot change it; only a source that records arrival, or an ADR that admits a weaker verdict class for arithmetic instants, can. The Graph Quality Report's rejection ledger surfaces it as 65.5% `TEMPORALLY_UNVERIFIABLE` plus 13.8% `TEMPORAL_NOT_CERTAIN`, against only **8 claims** that ever reached a band comparison. | Event Generator (origin); Causal Graph Builder (effect) | **accepted and OPEN as of 2026-09-04** |

| R-23 | **A simulated figure is MORE persuasive than an inferred one, because it is concrete.** prd.md §52's own example says a change "would likely reduce delivery delay by approximately 11 hours" — a number, in a unit, about a world that did not happen. Module 13's support envelope, sensitivity sweep and enumerated assumptions make such a figure auditable; **none of them makes it right**, and a decomposed, envelope-checked figure invites more trust than a bare one. This is OQ-024's argument one layer up and it is worse here, because the artifact reads like a measurement. | Disclosed structurally, not mitigated. `NOT_CALIBRATED_NOTICE` is the report's first section and is a property no run can soften. The `EXTRAPOLATION` verdict REPLACES the figure in the rendered table rather than sitting beside it — a number a reader can copy will be copied, and a warning above a table does not survive a screenshot. A simulated world holds no `Event` and no `TimeInterval`, so the API cannot serialize one as history. None of this is calibration and no procedure here could be: the dataset carries no causal ground truth. | Counterfactual Simulator (surface); Visualization API (effect) | **accepted and OPEN as of 2026-09-07** |
| R-24 | **The support envelope is measured over the same 150-row slice as everything else.** "Inside the range this run witnessed" is a statement about 150 rows of 180,519, and the witnessed range at dataset scale is certainly wider — so a change this run calls `EXTRAPOLATION` may be ordinary, and the verdict is conservative in a way that is invisible without the denominator. | Every envelope carries `witnessed_count`, so a range measured over two observations cannot be read as a range measured over two thousand; the report's closing section states that every figure is a property of the slice. OQ-023's shape on a new surface, bounded the same way and no better. | Counterfactual Simulator | **accepted and OPEN as of 2026-09-07** |
| R-25 | **A recommendation is the most actionable artifact this engine produces, and BOTH of the quantities that sequence it are assumed.** R-15 recorded that a mis-declared `actionable` flag silently changes the headline ranking and that nothing can detect it; ADR-0062 added `cost_class` as a second such surface. ADR-0073 adds a third: `risk_class`. Module 14 ranks on benefit, cost, belief and risk, and two of those four are pack declarations with `provenance_class` pinned to `ASSUMED` because no observation establishes them. A wrong cost or a wrong risk reorders what an operator is shown FIRST, with no symptom anywhere. This is strictly worse than R-15's original scope: a root-cause ranking is read as an explanation, and a recommendation is read as an instruction. | Disclosed structurally, not mitigated — no procedure here could check it. `CostBasis` and `RiskBasis` are closed two-member enums with no `DERIVED` member, so the engine cannot substitute a computed figure for a missing declaration; every recommendation prints its basis beside its figure and prints `ASSUMED` every time one is present, because there is nothing else it could print; and `ASSUMED_COST_NOTICE` is the report's first section as a property no run can soften. None of that makes a declaration true. | Intervention Optimizer (surface); every operator acting on the output (effect) | **accepted and OPEN as of 2026-09-07** |
| R-26 | **The only non-empty recommendation list this repository can produce comes from the disowned diagnostic run, and eight of its top ten propose acting on the outcome itself.** On the committed slice the stated graph is empty, so the STATED run publishes zero; the `UNPROMOTED_DIAGNOSTIC` run also publishes zero, because every candidate composes to a belief of 0.03 against a declared floor of 0.50. The ten that came closest are dominated by `SHIPMENT_DELAYED` — proposing to prevent a delay by removing the delay — which is circular, and is an artifact of the near-complete scored graph where one event type touches 4,517 of 9,492 claims. The actionability gate cannot catch it: the pack correctly declares that type actionable, so the DECLARATION is right and the INFERENCE is wrong. | Disclosed, not fixed, and not a defect in module 14: it is a causal-graph problem surfacing as a recommendation problem, and the fix is upstream (a source that records arrival, or a promotion policy that admits a weaker verdict class for arithmetic instants — R-22). Bounded by the belief floor, which withholds all of it; by the withheld ledger, which carries what was measured so a reader can see what the threshold excluded; and by PROGRESS.md's per-entry critique, which names the limitation behind each of the ten. | Causal Graph Builder (origin); Intervention Optimizer (surface) | **accepted and OPEN as of 2026-09-07** |
| R-25 | **The condition re-check is a containment test over a rendered expression, and it is conservative in one direction only.** `ConditionalCause.condition_expression` is the rendering of a rule-DSL tree; module 13 cannot re-evaluate it without parsing a rendering, which `core/precedence.py` refuses for the same reason. So a qualified link is treated as invalidated when its expression NAMES something the change touched. | Disclosed on every affected outcome. The test stops links it cannot prove should keep transmitting, so consequences are **under-claimed** rather than over-claimed — the direction this project errs in everywhere else. What it cannot see is a condition that should have stopped holding and names nothing that changed, and `CONDITION_TEST_NOTICE` says exactly that, as fixed text, with a standing assumption added to the enumerated list whenever an outcome rests on one. | Counterfactual Simulator | **accepted and OPEN as of 2026-09-07.** Closing it needs the condition TREE on the promoted edge rather than its rendering, which is a frozen-type change and an ADR |

## 10. Deferred / out-of-scope

**Do not re-litigate these.** Reopening any row requires an ADR that supersedes the
rationale, not a fresh discussion.

| Item | Source | Rationale |
|---|---|---|
| Real-time streaming inference | prd.md §6 | V1 reconstructs history. Streaming changes the temporal model and the determinism guarantee at once. |
| Autonomous decision execution | prd.md §6 | The system recommends; a human decides. Execution authority is a separate trust problem. |
| Reinforcement learning | prd.md §6, §45 | V4 at the earliest. Non-deterministic and unexplainable by default — violates the DoD and LAW-EVIDENCE. |
| Multi-company optimization | prd.md §6 | Requires cross-tenant data sharing; out of scope for a single-dataset V1. |
| Digital twin simulation | prd.md §6 | Requires a forward process model the PRD does not specify. |
| Predictive maintenance | prd.md §6 | Prediction, not causal reconstruction. Fails the §17 north star. |
| Bayesian networks (pgmpy) | prd.md §45 | V2. V1 intelligence comes from architecture, not model complexity. |
| Graph neural networks (PyTorch Geometric) | prd.md §45 | V3. |
| DoWhy-based identification | prd.md §41 | V2+. Requires a structural causal model V1 does not build. See OQ-007. |
| LLM explanation refinement | prd.md §58 | V1 explanations must be traceable sentence-by-sentence to graph evidence. An LLM in that path breaks the trace. |
| IoT / live ERP connectors, KG federation, cross-company analysis, multi-agent optimization | prd.md §58 | Future extensions. Named so they are not mistaken for V1 gaps. |

---

## 11. Changelog

Append-only. One line per meaningful change. Newest at the bottom. Never edit a past line.

```
2026-08-23  Governance substrate created: CONTEXT, DECISIONS, PROGRESS, CONVENTIONS,
            GLOSSARY, HANDOFF. Five Inviolable Laws placed verbatim. ADR-0001..0005
            seeded. 16 §36 modules registered, all not-started. 18 interfaces
            registered, all draft. OQ-001..OQ-013 opened. Phase set to P0 Governance.
            Repository contains no code.
2026-08-23  Governance audit. Five Laws verified byte-identical across CONTEXT/
            CONVENTIONS. OQ-001..OQ-007 and OQ-012 verified traceable to prd.md.
            OQ-008 citation corrected: prd.md has no §0.4; the determinism
            tension is §38 vs §41, hardened by CONVENTIONS.md §3. No other change.
2026-08-23  Architecture blueprint + repository scaffold. docs/architecture.md written
            (layer map + forbidden edges F1-F9, 16-module inventory, two-database
            boundary + rebuild procedure, Run model, extension seams + hospital
            walkthrough, three sequence diagrams). Scaffold created as one installable
            package backend/src/causalog with draft core/ contracts; 33 packages, each
            with README + tests mirror. ADR-0006, 0010, 0012..0018 accepted; OQ-001,
            OQ-006, OQ-010 closed; OQ-014, OQ-015 opened. prd.md moved to docs/prd.md.
            LAW-DOMAIN, layer-boundary, dependency-policy, and law-copy checks now fail
            the build. Determinism gate exists but is NOT-YET-RUNNABLE (OQ-014).
            CONVENTIONS.md §8/§9 amended for execution_id (ADR-0013). Still zero of the
            16 modules built; no business logic exists.
2026-08-23  DEF-0001 (Class C) fixed. LAW-DOMAIN's word-boundary matcher caught only the
            bare English word -- warehouse_id, orders, WAREHOUSE_TABLE, customerName and
            every other identifier form passed clean -- and its self-test listed
            `shipments` and `customers_table_in_a_name` as words that must never fire,
            certifying the hole. LAW-DOMAIN was therefore NOT enforced between the
            scaffold landing and this entry, while CONTEXT.md R-10 asserted it was.
            ADR-0019 accepted, superseding ADR-0010's matcher spec: stem-prefix matching
            with a letter-only lookbehind, no suffix exceptions, allowlist keyed on the
            exact reported text. Self-test rebuilt as MUST_FIRE / MUST_NOT_FIRE plus a
            guard refusing any claimed false positive that contains a banned stem.
            Generalised: every law script now ships --self-test and runs it in CI before
            its scan; negative pytest cases added for the law-copy and dependency-policy
            checks, which previously had positive-only and no coverage respectively.
            Three `order`-stem lines reworded to "sequence"/"sequenced". OQ-016 opened.
            CONVENTIONS.md §6 restated. Tests 55 -> 104.
2026-08-23  P0-gating ADRs ratified. ADR-0007 (OQ-002): LAW-TIME evaluated over intervals
            with the three-valued TemporalVerdict; UNDETERMINED is retained and blocked
            from INFERRED rather than guessed either way; imputation stays forbidden.
            ADR-0008 (OQ-003): root cause reported as two never-blended fields,
            earliest_cause and actionable_root_causes, ranked per prd.md §29; actionability
            is ontology-declared and stamped onto Event at generation time so the ranking
            module never reads the ontology (forbidden edge F3). ADR-0020 (OQ-012): Trigger
            is a property of one event, Cause is a relation between two, and no inference
            path may read Event.trigger. OQ-002, OQ-003, OQ-012 closed. New risks R-14
            (UNDETERMINED dominance) and R-15 (mis-declared actionability) accepted and
            disclosed. Event gained is_actionable; OntologySpec gained
            event_type_is_actionable. Tests 104 -> 108.
2026-08-23  DEFECT, self-reported: the §8 row for OQ-004 still read as open while §3 prose
            said it was resolved by ADR-0001. Class A doc lag caused by a missed
            same-commit update in the 2026-08-23 scaffold entry above, which changed the
            prose and not the row. Row struck; the history is recorded on the row itself
            rather than tidied away. OQ-001..OQ-004 are now all closed, so P0's OQ exit
            criterion is met -- but P0 remains OPEN: the module contract document does not
            exist, OQ-009 stands, and no interface may be frozen.
2026-08-23  Second instance of the same stale-row class found while sweeping: OQ-008 was
            fully answered by ADR-0003 at the scaffold and never struck. Twice is a
            pattern, so it now gets a check rather than more care --
            scripts/check_governance_consistency.py, with --self-test per ADR-0019,
            wired into make laws and CI. It rejects: a question both struck and open, a
            closure naming a nonexistent ADR, an unacknowledged supersession, an open
            question already answered by an ACCEPTED ADR (the OQ-004/OQ-008 class), and
            an open question called resolved in prose. OQ-008 struck. Tests 108 -> 114.
2026-08-23  Repository placed under git; first commit follows CONVENTIONS.md §13 with ADR
            and OQ trailers, making the same-commit doc rule auditable rather than
            aspirational.
2026-08-25  Canonical core implemented and FROZEN. causalog.core now holds working code
            rather than draft contracts: content-addressed identifiers with escaped
            payloads, interval timestamps with comparison semantics, the provenance
            algebra, a pluggable confidence aggregation registry, the five-payload causal
            edge taxonomy with LAW-TIME enforced at construction, canonical serialization,
            and the observed-fact immutability guard. ADR-0009 (closes OQ-005), ADR-0021
            (supersedes ADR-0007), ADR-0022, ADR-0023, ADR-0024 (supersedes ADR-0015, adds
            hypothesis), ADR-0025 (closes OQ-009) accepted. docs/contracts.md v1.0.0
            written; event/entity/edge/confidence schema versions set to 1.0.0; every
            core row in section 6 moved to frozen. Property-based tests added for identity,
            temporal comparison, the provenance algebra, aggregation, and serialization
            round-trip. Still zero of the 16 section 36 modules built; core/ is the shared
            contract layer, not a module, so there is still no pipeline and no ingestion.
2026-08-28  Ontology layer built. causalog.ontology_runtime (L1) now loads, validates and
            versions a declarative domain pack: a nine-namespace DSL whose pydantic models
            are normative and whose JSON Schema is GENERATED from them and drift-checked in
            make laws and CI; structural validation (orphan references, unreachable states,
            malformed state machines, CAUSES as a relationship, external event types
            referenced anywhere) reported as located ERRORs, all at once with file and line;
            semantic validation as non-fatal WARNINGs; and a third severity, NOT_RUNNABLE,
            for a check the validator could not perform -- today rule coverage, because no
            rule pack exists. That severity exists because DEF-0001 and OQ-014 are both
            instances of an unrunnable check reading as a passing one. Base-plus-overlay
            inheritance merges by identifier with whole-entry replacement and explicit
            withdrawal. ontology_hash = digest(ONTOLOGY, to_canonical_json(resolved_pack)),
            which required adding ONTOLOGY to the frozen IdentifierPrefix enum -- purely
            additive, no address recipe changed, docs/contracts.md -> 1.1.0.
            ADR-0026 (the DSL), ADR-0027 (ontology/packs/<domain>/ + inheritance),
            ADR-0028 (the hash), ADR-0029 (derived event types) accepted. Packs moved from
            ontology/<domain>/ to ontology/packs/<domain>/. Three packs ship: _base
            (structure only), dataco, hospital. ontology_version set to 1.0.0, which removes
            one of OQ-014's two blockers. New risk R-16: a pack that validates cleanly can
            still be semantically wrong, and nothing here can detect it.
            TWO FINDINGS ABOUT DATACO, recorded rather than smoothed over. First, the
            dataset logs ONE occurrence and implies the rest: only ORDER_PLACED is OBSERVED,
            twenty event types are DERIVED, each naming its basis and carrying a default
            confidence, and none may claim OBSERVED provenance (ADR-0029) -- the ratio is
            pinned by a test so it cannot be quietly promoted. Second, three prd.md §21
            event types are ABSENT rather than invented: Order Updated (no revision
            history), Customer Complaint (no such column), Route Changed (no route data);
            and no CARRIER entity is declared, because DataCo names a service level and
            never a carrier. Column traceability is enforced against a checked-in manifest
            that states it is UNVERIFIED_AGAINST_LOCAL_FILE -- the dataset is not in this
            repository, and module 1 flips that field when it pins the file.
            ontology_runtime added to the LAW-DOMAIN lint scope; a self-import false
            positive in the layer lint's F3 fixed and given a MUST_ACCEPT case. docs/
            ontology.md written, with domain onboarding as a numbered checklist a non-author
            can follow. Tests 114 -> 384. Still zero of the 16 section 36 modules built.
2026-08-28  Ontology acceptance checklist run against the layer; two items were true and
            enforced by nothing, and both are the DEF-0001 shape. FIRST, "a new pack touches
            ontology/ alone" was false: docs/ontology.md step 9 told a pack author to add the
            id to three literal tuples in the test suite, so a pack added without that
            editing would load and be tested by nothing. Discovery is now derived --
            tests/ontology_packs.discover_packs() globs ontology/packs/*/ontology.yaml and
            raises on an empty result, because zero parameterised tests report as a pass.
            Demonstrated with a throwaway pack that was collected with no test file edited,
            then deleted. SECOND, metrics are declared as a MeasurementExpression tree with
            no way to write a formula into a pack, and nothing stopped a reasoning module
            recomputing one inline -- LAW-DOMAIN defeated by a VALUE rather than by a word,
            the residual docs/architecture.md section 1.5 states. scripts/
            check_metrics_are_declared.py now refuses metric arithmetic in the five reasoning
            packages, over the AST rather than the text, with --self-test and planted-case
            coverage. Its scan exits 2 NOT-YET-RUNNABLE while those packages are scaffold,
            and emptiness is measured by CONTENT: thirteen docstring-only __init__.py files
            must not report as "13 files, clean". make laws and CI tolerate exactly 2, not
            continue-on-error, which would swallow a real violation too. ADR-0030 accepted;
            CONVENTIONS.md section 6a written. The other three checklist items -- DataCo
            column traceability, located diagnostics for invalid packs, and hash
            sensitivity/stability -- needed no work and are evidenced in PROGRESS.md 00c.
            Tests 384 -> 391. Still zero of the 16 section 36 modules built.
2026-08-28  ADR-0030's two stated limitations closed the same day rather than left standing
            (ADR-0031, supersedes ADR-0030; the pack-discovery decision is restated there
            unchanged). FIRST, the matcher read identifiers, and a declared quantity enters
            engine code through a STRING -- event["shipping_delay"] -- so one rebinding
            stripped every metric name off the arithmetic and the check passed. The lint now
            follows the VALUE: a name bound from a metric-named attribute or string key is
            tainted, taint survives rebinding, and arithmetic on it fires however it is
            named. Taint is tracked PER SCOPE, so a `value` holding a metric in one function
            does not taint an unrelated `value` in the next. SECOND, a hard-coded threshold
            -- if delay > 48 -- computes no metric and was excluded on the grounds that a
            lint firing on every guard clause gets routed around. That reasoning holds for
            delay > threshold and not for a numeric literal, which is domain policy written
            into engine code; the two are now separated and only the literal form fires.
            Both rules were observed to reject a planted file before being trusted. What
            remains is narrower and recorded: taint is a source-order approximation, it does
            not follow a metric through a function call, and v = a - b with both operands
            unnamed is still clean -- the answer to that is option C, ban arithmetic in the
            reasoning packages outright, revisited at the P2 exit. Also recorded because it
            is the check working on itself: the DEF-0001 guard rejected a MUST_NOT_FIRE
            entry written while implementing this ADR; the entry was multi-line and the
            guard is line-blind by design, so the guard stayed strict and the case moved to
            pytest. Tests 391 -> 397. Still zero of the 16 section 36 modules built.
2026-08-29  Persistence layer built. PostgreSQL is now a real system of record rather than
            two tables: fifteen PAIRED migrations (forward under sql/migrations/, reverse
            under sql/down/, same basename) covering the three version registries, entities,
            events, bi-temporal states/transitions/relationships, evidence records and
            items, decomposed confidence, run-scoped causal edges, the two under-specified
            run-scoped artifacts, the extended audit log, and the projection registry. Every
            table and column carries a COMMENT ON. Append-only is enforced by RAISING
            triggers on nine tables and observed to fire by tests/law/
            test_facts_are_append_only.py -- 23 cases, per table and per operation.
            ADR-0032 (bi-temporality: valid time IS the frozen State.held_over, system time
            is database-managed and appears in no content address, no core type and no
            envelope; the one sanctioned mutation closes a system period once), ADR-0033
            (paired raw-SQL migrations applied by a recorded runner with a checksum rule --
            ADR-0015's own negative consequences named this runner as the accepted cost of
            excluding a framework; Alembic was declined for that reason and the reasoning is
            in the ADR), ADR-0034 (every prd.md section 47 label is materialized, and the
            three derived ones name the facts they are a function of) accepted.
            DEF-0003 fixed: migration 0002 enforced audit_log append-only with
            `CREATE RULE ... DO INSTEAD NOTHING`, which reports SUCCESS for a write it
            discarded -- a rejected write indistinguishable from an accepted one, in the one
            table whose whole purpose is being trustworthy. Same shape as DEF-0001. Migration
            0014 replaces it with the raising trigger every other fact table uses, and the
            reversal restores the defect verbatim rather than "fixing" what it reverses.
            SECOND INSTANCE OF THE F3 SELF-IMPORT HOLE, in F4: the layer lint rejected
            `persistence` importing `persistence`. ADR-0026 fixed exactly this in F3 and it
            stayed invisible there until ontology_runtime held code; F4 had it too and stayed
            invisible for the same reason -- persistence was four empty scaffold packages, so
            the rule had nothing to fire on. Both now carry a MUST_ACCEPT self-test case.
            A DEFECT FOUND BY ITS OWN TEST, recorded because the test was written before the
            fix: the bulk loader wrote confidence_component and silently skipped
            confidence_component_evidence, so LAW-EVIDENCE's audit hook held for small loads
            and stopped holding at the scale where it matters. Fixed, and made structural --
            a test now loads identical artifacts through the bulk path and the row path into
            two databases and compares all twelve tables. New risk R-18.
            THE prd.md SECTION 55 LOAD BUDGET IS NOT MET AND THE TEST SAYS SO. Measured
            ~33-41s against 30s for 180,519 events on a local PostgreSQL 14 with default
            server settings. COPY over INSERT, one transaction, UNLOGGED staging,
            synchronous_commit off, work_mem and maintenance_work_mem raised, and the removal
            of a speculative GiST index (measured at ~3s, about a tenth of the budget, and
            serving no query any built module issues) are all in place; the deployment
            configuration is untested because no container runtime is reachable here. The
            assertion is left FAILING rather than relaxed: raising the budget until the test
            goes green would convert a known miss into an unknown one. New risk R-17.
            OQ-017 (the two under-specified tables) and OQ-018 (which reading of "dataset
            loading" section 55 means -- the two differ by 21x under ADR-0029) opened.
            GLOSSARY gained Valid Time, System Time, Bi-temporal, Retraction, Schema
            Migration, Migration Ledger, Projection Namespace, Projection Content Hash,
            Staging Table, and section 2.7 recording that prd.md section 54's "request id"
            IS correlation_id -- one concept, one name.
            The PostgreSQL init-directory mount is removed: it applies migrations without
            writing the ledger, leaving a schema that exists and a history that says nothing
            was applied. `make up` no longer migrates; `make migrate` does.
            docs/data-model.md written (ER diagram, graph model diagram, the index table with
            every justifying query, the indexes deliberately absent, and the storage boundary
            restated in one paragraph). graph_projection_version and postgres_schema_version
            moved from unset to 1.0.0. Tests 397 -> 485 (480 fast + 5 slow). Still zero of the 16 section 36
            modules built.
2026-08-30  THE FIRST TWO MODULES. 1 Data Adapter and 2 Schema Mapper built, both
            built-unverified. A generic delimited SourceReader that DETECTS its encoding
            rather than declaring it, streams in bounded memory, and pins the file by hash;
            a two-pass stdlib profiler (no tabular library, so no ADR-0015 change) giving
            exact ranges and binned quantiles; 24 registered validation rules across six
            dimensions, each carrying a required downstream_consequence; a closed cleaning
            transform registry with a receipt per (rule, column); quarantine with reasons and
            an asserted row reconciliation; and a declarative SchemaMappingSpec whose
            auto-suggester writes a proposal the loader REFUSES to load.
            ADR-0035 (dataset_version = <id>@<file_hash>+map<mapping_hash>, folding the
            mapping into run identity WITHOUT touching frozen RunKey -- the product owner
            chose this over a sixth RunKey field; its cost is new risk R-19), ADR-0036 (the
            mapping DSL and the PROPOSED_UNCONFIRMED refusal), ADR-0037 (LAW-DOMAIN's scan
            extended to ingestion and extraction, and its package list itself checked),
            ADR-0038 (encoding probed from BOTH ENDS of the file; precision never asserted
            from a format) accepted. dataset_version moves from unset to a real value, which
            takes another bite out of OQ-014. contracts.md -> 1.2.0 for an additive
            IdentifierPrefix.MAPPING. New OQ-019 on the ~105s import against the contested
            section 55 budget. New risks R-19 and R-20.
            DEF-0004, AND IT INVALIDATES A PREMISE FOUR ADRs REST ON. "DataCo timestamps are
            day-granularity" is false against the actual file, in both directions. `order
            date` is MINUTE-granular -- 180,401 of 180,519 rows carry a real time. `shipping
            date` displays a minute and never observed one: it equals `order date` plus `Days
            for shipping (real)` whole days, exactly to the minute, in 170,782 of 180,519
            rows (94.61%), and the remaining 9,737 miss by exactly +12h (5,080) or -12h
            (4,657) and by nothing else -- which is precisely the count of `Same Day`
            shipments. So the project's CONCLUSION (intra-day precedence is largely
            unrecoverable) survives and its REASON does not: not coarse precision but
            MANUFACTURED precision, which is worse, because a coarse column announces its
            limits and a fabricated minute does not. The mapping binds that column at DAY on
            the strength of the measurement, and the measurement is in a committed report.
            New risk R-20. R-14 keeps its status and gains a real number: 5,080 rows (2.81%)
            are temporally inseparable under core.temporal.verdict -- the engine's own
            LAW-TIME function, called directly rather than reimplemented, so the count is
            exactly what module 9 will face.
            TWO DEFECTS IN THIS WORK, FOUND BY ITS OWN CHECKS AND RECORDED BECAUSE THE CHECKS
            FOUND THEM. First, the derivation audit compared the two columns' BOUND intervals,
            so the DAY binding had already discarded the minutes it was measuring; it reported
            0.07% agreement where the truth was 94.61%, and the headline asserted "the great
            majority of rows" regardless of what came back. A measurement whose result was
            created by the binding it existed to justify. Both fixed: the audit reads SOURCE
            instants, and the headline is gated on the measured rate. Second, read_pin used
            model_validate on canonical JSON that write_pin had wrapped in a schema envelope
            -- a round-trip this module could not survive, caught by the manifest test.
            Also: the LAW-DOMAIN scan, on being pointed at ingestion for the first time,
            immediately reported 21 violations in the freshly written modules 1 and 2. All 21
            were REWORDED, none allowlisted. And check_layers rejected module 1 importing a
            concrete reader (F4); the fix put SourceDescription on the core port, which is
            the seam working rather than being worked around.
            A THIRD CORRECTION, and this one is to an append-only line so it is made here
            rather than there: the 2026-08-28 entry above says "twenty event types are
            DERIVED". The pack declares TWENTY event types in total -- one OBSERVED
            (ORDER_PLACED) and NINETEEN derived. The ratio the entry was making a point
            about is unchanged and the test that pins it still passes; the count was off by
            one and is corrected on the record.
            The DataCo column manifest flips to VERIFIED, which is the promise module 1 was
            named to keep. The test that guarded the flip is INVERTED AND STRENGTHENED rather
            than deleted: verified_by must name a dataset_version that a real, readable pin
            carries, with a header matching the manifest. Data Quality Report committed to
            docs/reports/dataco/<dataset_version>/. Tests: 600 collected, of which 75 are
            added by this work. NOTE that 600 - 75 = 525 pre-existing against the 485 this
            log last recorded, so about forty tests were added earlier without the count
            being updated; that gap predates this work and is recorded in PROGRESS.md 01a
            rather than absorbed into this line.
            Fourteen of the 16 section 36 modules remain; there is still no Event and no
            graph.
2026-08-30  MODULES 3 AND 4, AND THE LAW-EVENT BOUNDARY IS CROSSED. Entity Extractor and
            Event Generator built, both built-unverified. There is now an Event.
            THE DECISION THIS MODULE TURNED ON. Every derived event type in the pack states
            its derivation.basis in PROSE -- "Implied by an Order Status of PROCESSING,
            COMPLETE or CLOSED" -- which a human can audit and nothing can execute. The pack
            was otherwise fully machine-readable, so the only thing between module 4 and
            being ontology-driven was that nothing said, executably, WHICH RECORDS WITNESS
            WHICH OCCURRENCE. ADR-0039 puts that in mapping.yaml as a closed condition
            operator tree over ontology addresses -- not in the frozen pack, because a
            condition over source values is a claim about one dataset's encoding and would
            make the pack unreusable; and not as an expression string, for ADR-0026's
            reasons unchanged. Nineteen rules were authored, one per witnessable type, each
            transcribing its basis with the prose kept beside it so the two can be read
            against each other. An emission rule names NO provenance class and NO
            participants: the event takes the class its type declares and the pack refuses
            OBSERVED on a derived type, so a heuristic has no path to an observed event by
            construction rather than by review, asserted over the AST.
            ADR-0040 makes RECORD_GAP the default where a process step has no supporting
            field: the gap is reported and no event is fabricated, because a fabricated
            event is a real node the causal engine can attach edges to and one with no
            supporting field is UNKNOWN-precision, so it adds graph mass carrying nothing
            checkable. EMIT_GAP_MARKER is implemented, selectable, and stamped into the
            report because it changes what the causal engine can conclude.
            ADR-0041 CORRECTS docs/architecture.md section 2, which stated module 4's
            invariant as `provenance_class = OBSERVED`. That is false against ADR-0029 and
            building to it would have put nineteen fabricated observations into the system
            of record with real columns standing behind them. The document predated the
            pack; the correction is an ADR rather than a quiet edit, per CONVENTIONS.md 13.
            Two structural additions ADR-0039 forced, recorded because they are module
            boundaries and not implementation detail. MappedRecord/MappedRecordBatch, which
            docs/architecture.md section 2 named as module 2's output and module 2 shipped
            without, added to schema_mapper where the architecture assigns them. And the
            transform registry and interval builder MOVED from data_adapter/cleaning.py to
            schema_mapper/transforms.py, verbatim and re-exported: they interpret Transform
            and TemporalBindingSpec, which is mapping semantics, and module 2's own record
            mapper reaching them through module 1 would have been a circular import --
            a defect under CONVENTIONS.md 6, not a refactoring opportunity.
            R-19 REALISED, on the first mapping edit after the ADR that predicted it.
            mapping_hash moves to map:a85a911e567f73c2, so dataset_version moves to
            dataco@994b3c8d24049cc4+mapa85a911e567f73c2, the file was re-pinned and
            re-imported, and a second report directory now exists for byte-identical source
            bytes. The cost is exactly what ADR-0035 said it would be.
            A DEFECT THIS WORK FOUND IN ITS OWN REPORT, and it is the third instance of one
            class. Process coverage reported ITEM_PICKED and ITEM_PACKED as 100% missing,
            SYSTEMATICALLY, while 19,222 events of each had just been emitted: both declare
            participants that include no participant of the process anchor's type, so the
            measurement could not connect their events to any instance and reported its own
            blindness as a finding. "100% of instances lack this step" is confident and
            quantified and was wrong about a step firing on nearly every instance -- the
            DEF-0001 shape (a check that could not run reading as one that passed) and the
            DEF-0004 shape (a measurement whose result was created by the binding it existed
            to justify). ProcessStepCoverage now carries `attributable`; an unmeasurable step
            reports NOT MEASURED with n/a rather than a rate it never counted, and two tests
            pin it, one asserting the step really does produce events so the case cannot go
            vacuous.
            THE GROUND TRUTH CAUGHT TWO THINGS BEFORE ANYTHING ELSE RAN, which is what it is
            for. Twenty hand-built records and a hand-derived expansion of 146 events written
            BEFORE the generator produced anything: it rejected its own first draft (each
            line of one order carried a different order-date minute, which would have
            silently defeated the deduplication the fixture exists to check) and it forced
            occurrence deduplication, without which a line-item source inflates every
            order-level count by its average line count, invisibly.
            MEASURED, NOT ESTIMATED. The expansion factor is ~7.9x, against OQ-018's guess of
            21x -- so the two readings of "dataset loading" section 55 might mean are 180,519
            records and ~1.43 million events, and the ruling OQ-018 asks for is still needed,
            now against numbers. Deduplication is worth ~30% of the event count (records per
            event is 1.00 for every line-scoped type and 1.5-1.95 for every order-scoped
            one). Events are STREAMED rather than collected, which is a correctness
            constraint and not an optimisation: collecting the reference expansion drove an
            8 GB host into swap.
            LAW-DOMAIN fired on the first draft, as it did on modules 1 and 2. Fourteen
            occurrences across five files, ALL REWORDED, none allowlisted.
            New OQ-020 (attribute history is computed and cannot be persisted -- entity_
            attribute holds one value per attribute) and OQ-021 (three of the pack's declared
            bases are not separable in this source, so all three fire and over-count; a
            fourth cannot be witnessed at all). R-02 partly in force one layer earlier than
            expected; R-16 widened to nineteen emission rules. contracts.md -> 1.3.0 with no
            frozen type changed. mapping_schema_version -> 1.1.0, mapping_version -> 1.1.0.
            `make events` and scripts/build_event_log.py added, so both reports are
            reproducible rather than merely committed. Tests 600 -> 724 collected (124 new).
            Twelve of the 16 section 36 modules remain; there is still no graph and no
            inference.
2026-09-02  Audit of the rule engine against the reference dataset, after seam 4's gate
            passed green. Five checks run: rules-all-disabled produces zero candidates with
            no hidden default (and an empty `rules` list is refused at load, so the two ways
            of reaching zero stay distinguishable); a randomly drawn firing was verified by
            hand back to raw CSV row 850 (Order 21868, Order Item 54682), window arithmetic
            reproduced to the second; a rule naming an undeclared event type is refused at
            load with RUL-E-UNDECLARED-EVENT-TYPE; the six coverage blind spots were
            confirmed present in the report but NOT listed in this file, only counted; the
            LAW-DOMAIN scan is clean and a wider 24-term grep found one docstring leak
            (loader.py:364, "a line already withdrawn cannot be dispatched") that the
            seven-stem matcher cannot see.
            TWO DEFECTS FOUND, recorded and NOT fixed. DEF-0007: `evaluate()` raises
            OverflowError on any UNKNOWN-precision event, contradicting the docstring twelve
            lines above the crash site; 13 of 18 emitted DataCo event types are 100% UNKNOWN,
            so the pack cannot be evaluated over its own dataset. Reproducible in two
            synthetic events. No test could catch it: tests/fixtures/facts.py::interval
            hardcodes OBSERVED provenance and TimeInterval refuses UNKNOWN+OBSERVED, so the
            fixture structurally forbids the breaking input -- the DEF-0001 shape relocated
            into a fixture. DEF-0008: clamping to the documented behaviour trades the crash
            for a cross product -- 12,494 events emit 1,855,405 firings, 99.8% flagged
            temporally_unverifiable. The engine stays honest about it; the output is
            unusable. test_complexity_bound.py measures only Precision.DAY, so its 2.00
            ratios are narrower than they read; corrected in place in PROGRESS.md.
            New risk R-21. No source file changed: this commit records what was found.
2026-09-02  Module 9 built: the Candidate Cause Generator, and with it the inference
            boundary (forbidden edge F6). Seven independent generators -- temporal proximity,
            rule-based, shared entity, shared identifier, structural path, historical
            frequency, statistical association -- each returning PROPOSALS, none able to
            construct a candidate, because construction is where the LAW-TIME gate lives and
            the gate is one function in one module. VIOLATION is refused and counted;
            UNDETERMINED is retained, flagged and blocked from INFERRED; temporally
            unverifiable is a THIRD outcome counted separately, never summed with the second.
            ADR-0048: CandidateEdge is a new draft core type with NO confidence field, so
            "module 9 never scores" is enforced by the type rather than remembered -- a
            generator cannot score because the artifact has nowhere to put a score. CausalEdge
            is untouched and still frozen; only its registry OWNER was wrong and moves to
            module 10, which is what actually constructs one. IdentifierPrefix gains
            EVIDENCE_ITEM additively; contracts.md -> 1.5.0; no address recipe moves.
            ADR-0049: every generator parameter -- window, hop bound, support floor, lift
            floor, per-effect cap, and each generator's authored evidence weight -- is
            declared in the RULE PACK at rule_pack_schema_version 1.1.0, additive and
            defaulted. Not the ontology pack: a window is a claim about how a domain BEHAVES,
            which is causal knowledge, and the ontology says what a domain IS. An absent
            parameter makes its generator NOT_RUNNABLE, never zero -- the third-severity
            lesson from ontology_runtime, which OQ-014 and DEF-0001 are both instances of.
            The DataCo pack declares all of them with a rationale on every window and moves to
            1.1.0, so rule_pack_hash and run_id moved with it. None of the widths is
            calibrated; R-16 covers them.
            ADR-0050: the per-effect cap selects ROUND-ROBIN across generators. Every
            intuitive alternative -- closest in time, strongest evidence, most agreement --
            is a plausibility ranking, and a module documented as forbidden from ranking that
            ranks its survivors has only stopped SAYING so. Round-robin is fair allocation;
            every drop emits a TruncationRecord naming the effect and the count lost per
            generator, and both the record and the graph check their own arithmetic and raise
            rather than publish numbers that disagree with themselves.
            ADR-0051: confounder awareness as structural flagging. POSSIBLE_MEDIATION and
            POSSIBLE_COMMON_CAUSE, emitted as a separate artifact that mutates no edge. One
            closed triangle emits BOTH, because the data cannot separate the two readings and
            suppressing one would be the resolution nothing at V1 can perform. Every flag
            carries a fixed notice saying visibility is not resolution AND that the absence of
            a flag is not evidence of no confounding.
            THREE DEFECTS, all found by running the thing rather than by reading it.
            DEF-0005: rule_engine.index.admissible_slice documented that an UNKNOWN-precision
            event degenerates the lower cut to zero, and raised OverflowError instead. The
            paragraph was right and nothing executed it -- no test put an unplaced event on the
            CONSEQUENT side, which is the only side that reproduces it. Third instance of the
            DEF-0001 shape. Fixed by saturating arithmetic; the regression test was observed
            to fail with the original OverflowError first.
            DEF-0006: the candidate address collided when one generator made two claims over
            one pair -- which the DataCo pack authors deliberately. Caught not by a test but by
            TruncationRecord's own arithmetic check on real data (retained 20 + dropped 137 !=
            proposed 159). The payload now participates in the address, and identical claims
            are MERGED into one candidate carrying both justifications.
            DEF-0007: the shared-identifier generator read all of Event.metadata, which carries
            the Event Generator's traceability pairs and no domain identifier. It proposed
            87,446 candidates over a 150-row slice -- one per pair sharing an observation_mode,
            exactly matching the shared-entity count. Caught by the per-generator report the
            task required; the saturation flag did NOT fire (87.2%, under the 90% share), so
            the side-by-side comparison is what found it. The pack now declares which metadata
            keys carry identifiers, and DataCo declares NONE, so the generator reports
            NOT_RUNNABLE with its requirement rather than 87,446 meaningless hypotheses.
            FIRST MEASURED CANDIDATE GRAPH, bounded to 150 rows and labelled as bounded in the
            artifact (OQ-023): 1,224 events, 733 process instances, 17,864 candidates.
            14.5% UNDETERMINED and -- separately and much larger -- 84.1% temporally
            unverifiable, with only 254 candidates (1.4%) promotable to INFERRED. R-14 is
            therefore measured at module 9 and is worse than the adapter's 2.81% predicted,
            for a reason that row could not see: the dominant term is ABSENT instants from
            ADR-0029's twenty DERIVED event types, not ambiguity between placed ones.
            R-13 narrowed: rule coverage now bounds one generator of seven rather than the
            graph. R-05 and R-06 gain a real surface. Tests 802 -> 880.
2026-09-03  MODULE 10 (Confidence Scorer) built, built-unverified. prd.md 49's "confidence
            should never be represented by a single unexplained number", made structural:
            eight named components, a ComponentExplanation per component carrying its
            arithmetic and its caveats, and a strategy name from which the whole scalar
            recomputes. confidence_schema_version 1.0.0 -> 2.0.0 (ADR-0052) adding
            evidence_diversity and contradiction_freedom; weighted_mean_v1 and minimum_v1
            are byte-identical and still registered, and the new gated_weighted_mean_v1
            arrives BESIDE them so every stored scalar still recomputes.
            TWO OF THE EIGHT ARE GATES, NOT ADDENDS. temporal_support and
            contradiction_freedom cap the scalar rather than contributing to it: a claim
            whose precedence nobody established is not a weak causal claim, it is not a
            causal claim, and no quantity of correlation lifts it past its ceiling.
            Monotonicity is preserved and property-tested (weighted mean non-decreasing in
            each addend; each ceiling non-decreasing in its gate; min of non-decreasing
            functions non-decreasing).
            NO COMPONENT IS EVER SKIPPED. A component whose data is absent is emitted at
            zero, marked missing, and counted -- absence costs score rather than
            abstaining, which is the opposite of weighted_mean_v1's renormalize-over-present
            and is why the gated strategy REQUIRES all eight names.
            rule_pack_schema_version 1.1.0 -> 1.2.0 (ADR-0053): a confidence_scoring block
            holding the DOMAIN knobs (lift reference, small-sample prior, bands and their
            plain-language wording, promotion band). The STRATEGY stays in engine code under
            a versioned name, because ConfidenceVector.aggregation must determine the
            arithmetic -- a pack-supplied weight would make one name mean two things.
            rule_pack_hash rul:83fa4858d3cc0a4a -> rul:01eb1123f2d33de4, run_id moved with
            it (R-19, second occurrence, as ADR-0035 predicted).
            FIRST MEASURED CONFIDENCE DISTRIBUTION, same 150-row slice as module 9's:
            17,864 candidates fused to 9,492 scored edges. NO EDGE SCORES ABOVE 0.40 and
            NONE is promoted to INFERRED; every scored edge lands in the WEAK band. The
            temporal gate binds on 48.8%, graph_connectivity is MISSING on 100% (module 7
            does not exist), rule_support on 75.8%. 1,957 edges (20.6%) are
            INSUFFICIENT_EVIDENCE -- a distinct outcome from a low score, carrying a full
            vector, given no band, never promoted.
            The top of the distribution is a PLATEAU: 310 edges tie at exactly 0.400000
            because the temporal ceiling put them there, so "top 10" is a canonical slice
            of a tie and the report says so before printing them.
            THREE DEFECTS FOUND BY THE ARTIFACTS AND TESTS THEMSELVES, FIXED AND RECORDED
            rather than tidied away. (1) DataCo declared minimum_scored_components: 3,
            which CANNOT FIRE -- three components are properties of the claim's own
            evidence bundle and are always measurable. The report said so; corrected to 5
            against the observed distribution, and the report now states when a floor is
            unreachable. (2) ceiling_at returned an unquantized value, so on 3.8% of
            vectors the stored scalar sat 5.5e-17 ABOVE its own ceiling -- a hard cap a
            rounding could step over. Caught by a property test; fixed by quantizing the
            ceiling. (3) statistical_support discounted for sample size on the INSTANCE
            TOTAL rather than on the cell the ratio rests on, making the term 0.973 for
            every pair -- a small-sample penalty that penalized nothing, sitting under a
            caveat that correctly announced SMALL SAMPLE. A number disagreeing with its own
            caveat is this module's characteristic defect and it shipped for one run. Both
            lift-reading components now discount on `both` and differ by how they WEIGHT
            the sample and effect factors, geometrically, so a zero on either is a zero
            overall.
            NOT CALIBRATED, and the report says so before any number. No labelled causal
            ground truth exists in this repository, so no reliability curve can be drawn
            and no error rate quoted; the weights are a stated editorial judgement. New
            OQ-024. Tests 880 -> 1,050.
2026-09-04  CAUSAL GRAPH BUILDER built (ADR-0054, ADR-0055, ADR-0056). The assembly step
            prd.md §25/§26/§31 describe and §36 names no owner for. NOT one of the 16
            modules -- landed as the ontology layer and the rule engine were, with OQ-025
            recording the PRD gap and proposing that §36 be amended rather than renumbered.
            Package causal_engine/causal_graph_builder at L6, built-unverified.
            PROMOTION MOVED OUT OF MODULE 10. ProvenanceClass.INFERRED is now assigned in
            exactly one file in the whole engine -- causal_graph_builder/policy.py -- and a
            law test asserts it structurally over the AST rather than behaviourally, so a
            second promotion path fails on the day it is written. Module 10's
            _promotion_class always returns the weakest class its evidence supports;
            confidence_scoring.promotion_band is DEPRECATED, still parsed, no longer read,
            with a loader WARNING; ConfidenceReport.promoted_count is structurally zero and
            the report says where the decision went rather than reading as a finding.
            LAW-TIME RE-VERIFIED AT PROMOTION BY TWO INDEPENDENT MECHANISMS: explicitly
            against the two Event intervals -- the check a stored CausalEdge CANNOT perform
            on itself, because it holds identifiers and not intervals (DEF-0002) -- and
            again through core.immutability.revise, which re-runs the frozen type's
            INFERRED => CERTAIN invariant on the revision. Neither is redundant: the first
            catches a stored verdict the data does not support, the second catches a path
            that never consulted the first.
            FEEDBACK LOOPS ARE DETECTED OVER THE EVENT-TYPE PROJECTION, never over event
            instances. At the instance level a CERTAIN verdict is a strict precedence
            relation and strict precedence admits no cycle, so an all-CERTAIN circuit over
            instances is ARITHMETICALLY IMPOSSIBLE and a detector running there could only
            ever find artifacts. prd.md §31's loop closes across process instances. Pinned
            by test_no_instance_level_cycle_is_all_certain so it cannot be quietly reversed.
            Four classifications, because two would overclaim: GENUINE, TEMPORAL_ARTIFACT,
            WITHIN_INSTANCE, UNPROMOTED. Classification is engine code; no pack overrides it.
            Joint causes promoted ALL-OR-NOTHING: promoting two of three contributors would
            tell counterfactual and intervention analysis that removing either prevents the
            outcome, the opposite of what a joint cause asserts.
            rule_pack_schema_version 1.2.0 -> 1.3.0 (graph_construction, additive);
            dataco rule_pack_version 1.2.0 -> 1.3.0; hospital 1.1.0 -> 1.2.0 with
            deliberately different numbers INCLUDING A DIFFERENT DIRECTION (hospital
            promotes CONDITIONAL below DIRECT); rule_pack_hash rul:01eb1123f2d33de4 ->
            rul:4115780e4b4b45ec; run_id moved with it to run:244e3cf2d3f4300d -- R-19 for
            the third time, as ADR-0035 predicted. contracts.md 1.6.0 -> 1.7.0.
            core gains measurement.py (ADR-0056): the ONE walk of a declared operator tree,
            lifted out of state_engine rather than duplicated into causal_engine, because a
            second walker there would be arithmetic over domain attributes inside a package
            check_metrics_are_declared.py polices -- and the lint would be right.
            THE MEASURED RESULT: the stated causal graph is EMPTY. 0 of 9,492 claims
            promoted on the 150-row slice. The ledger says why, and it is not the threshold:
            65.5% TEMPORALLY_UNVERIFIABLE, 20.6% INSUFFICIENT_EVIDENCE, 13.8%
            TEMPORAL_NOT_CERTAIN, and only 8 claims EVER REACHED A BAND COMPARISON. 200
            circuits found, ZERO genuine, all 200 temporal artifacts.
            NEW RISK R-22, found by hand-verifying one chain against the raw rows rather
            than predicted: an INFERRED timestamp can never yield a CERTAIN verdict
            (ADR-0021), and on this dataset the most important link has one. Order 41304:
            SHIPMENT_DISPATCHED 2018-02-03 -> SHIPMENT_DELIVERED 2018-02-06, strictly_before
            is TRUE, three whole days apart, verdict still UNDETERMINED -- because DataCo
            records no arrival instant, so the delivery timestamp is arithmetic. Not one of
            the 1,224 events in the slice carries an OBSERVED timestamp (789 ASSUMED, 435
            INFERRED). This is a sharper statement than R-14's "day granularity" and more
            rows cannot change it. Tests 1,050 -> 1,156.
2026-09-06  Modules 11 (Root Cause Analyzer) and 12 (Propagation Analyzer) built, plus
            `causal_engine/pattern_miner` -- an L6 package deliberately NOT one of the 16,
            serving prd.md §10's Executive Leadership user whom §36 names no owner for
            (OQ-025's shape a second time). ADR-0059..ADR-0064. `GraphStanding` makes a
            traversal declare which graph it walked; ADR-0008's two required fields become
            four labelled views with a trade-off per disagreeing pair and no root-cause
            score anywhere on the type; consequence is attributed to the node SET, never to
            the routes; path confidence composes under a named function in
            `core/composition.py` with the product beside it and path length unblended.
            `rule_pack_schema_version` 1.4.0 -> 1.5.0 (three namespaces, all defaulted,
            absent means CANNOT RUN); contracts.md 1.8.0 -> 1.9.0 (three L0 registries and
            three `IdentifierPrefix` members, all additive, no frozen type touched).
            `run_id` moved to run:f5e7ab410fa9eeb4 -- R-19 for the fifth time -- and every
            committed DataCo report was regenerated. prd.md §55's root-cause budget is
            MEASURED for the first time (0.5s against 3s, at slice scale); `make laws` lost
            the metric-lint exit-2 tolerance as its own comment instructed. 104 new tests,
            both allowlists still empty. On the slice: 5 of 5 cases return no cause under
            STATED, and the disowned diagnostic run's 5 rankings are all unconvincing for
            stated reasons. OQ-026..OQ-028 opened; R-15 restated as load-bearing in two
            places. This work's own 104 tests pass; the whole-suite figure first
            recorded here was produced through a pipe that hid both the FAILED lines
            and pytest's exit code, and is corrected in PROGRESS.md §00i.
2026-09-07  Module 13, the Counterfactual Simulator, built at L7 (`counterfactual_engine`,
            9 files) with `core/perturbation.py` beside it at L0. ADR-0065..ADR-0072.
            A PREREQUISITE THAT WAS NOT THERE: architecture.md section 2, CONTEXT.md
            OQ-007 and PROGRESS.md section 13 all named a reserved ADR number as what
            unblocked this module, and that ADR had never been written -- reserved at the
            2026-08-23 scaffold and skipped while numbering reached 0064. ADR-0065 is the
            decision, records the gap rather than erasing it, and closes OQ-007;
            check_governance_consistency.py gains a seventh rule (every ADR named in any
            governance file exists) which found the two references still dangling after the
            first pass. Five typed interventions validated against the ontology before
            anything simulates; an impossible premise is REFUSED, never simulated and
            flagged. A contributing cause removed REDUCES and never eliminates -- asserted
            at 90.0 -> 67.5 over four causes at 0.25 each. A simulated world holds no Event
            and no TimeInterval, so prd.md section 37's non-conflation is structural rather
            than a field a consumer must read. Attribute mutability is ontology-declared
            (pack schema 1.0.0 -> 1.1.0, ADR-0067); module 13's bounds are pack-declared
            (rule_pack_schema_version 1.5.0 -> 1.6.0, ADR-0071). ontology_hash and
            rule_pack_hash BOTH moved, so run_id moved for two reasons at once -- R-19 for
            the sixth time. contracts.md -> 1.10.0, additive only. prd.md section 55's
            5s counterfactual budget is MEASURED for the first time. OQ-007 struck;
            OQ-029..OQ-032 opened; R-23..R-25 accepted. The schema and RunKey changes broke 44
            tests elsewhere in the suite, all fixed; the non-slow suite is then 1,379 green
            at pytest exit 0, the first such figure in this record. OQ-026 is honoured with an explicit
            opt-in rather than amended away (ADR-0072) and is left OPEN and widened.
```
