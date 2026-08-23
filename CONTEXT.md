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

NOTHING IS FROZEN YET. See section 6. No interface may be marked `frozen`
until the module contract document ("Prompt 02") exists. See OQ-009.

The PRD is at docs/prd.md. The architecture blueprint is at docs/architecture.md;
read it before touching any module boundary, dependency, or storage decision.
```

**Current status in one line:** Phase P0 (Governance), architecture blueprint and scaffold
complete. Zero of the 16 modules built. The repository contains the six governance files,
`docs/prd.md`, `docs/architecture.md`, the package scaffold with draft `core/` contracts,
and the enforcement tooling — but no module implementation and no business logic.

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

Module list is prd.md §36, verbatim and in order. Phase grouping is **proposed, not
ratified** — see OQ-011.

| # | Phase | Module | Package path (`backend/src/causalog/…`) | Owner prompt | Status | Contract frozen? | Tests | Last touched |
|---|---|---|---|---|---|---|---|---|
| 1 | P1 Ingestion | Data Adapter | `ingestion/data_adapter` | TBD | not-started | no | none | — |
| 2 | P1 Ingestion | Schema Mapper | `ingestion/schema_mapper` | TBD | not-started | no | none | — |
| 3 | P1 Ingestion | Entity Extractor | `extraction/entity_extractor` | TBD | not-started | no | none | — |
| 4 | P1 Ingestion | Event Generator | `extraction/event_generator` | TBD | not-started | no | none | — |
| 5 | P2 Graph | Timeline Builder | `graph_engine/timeline_builder` | TBD | not-started | no | none | — |
| 6 | P2 Graph | State Engine | `graph_engine/state_engine` | TBD | not-started | no | none | — |
| 7 | P2 Graph | Relationship Resolver | `graph_engine/relationship_resolver` | TBD | not-started | no | none | — |
| 8 | P2 Graph | Temporal Graph Builder | `graph_engine/temporal_graph_builder` | TBD | not-started | no | none | — |
| 9 | P3 Inference | Candidate Cause Generator | `causal_engine/candidate_cause_generator` | TBD | not-started | no | none | — |
| 10 | P3 Inference | Confidence Scorer | `causal_engine/confidence_scorer` | TBD | not-started | no | none | — |
| 11 | P3 Inference | Root Cause Analyzer | `causal_engine/root_cause_analyzer` | TBD | not-started | no | none | — |
| 12 | P3 Inference | Propagation Analyzer | `causal_engine/propagation_analyzer` | TBD | not-started | no | none | — |
| 13 | P4 Simulation | Counterfactual Simulator | `counterfactual_engine` | TBD | not-started | no | none | — |
| 14 | P4 Simulation | Intervention Optimizer | `recommendation_engine` | TBD | not-started | no | none | — |
| 15 | P5 Surface | Explanation Generator | `explanation_engine` | TBD | not-started | no | none | — |
| 16 | P5 Surface | Visualization API | `api/visualization` | TBD | not-started | no | none | — |

Every package exists with an `__init__.py`, a `README.md` stating its single responsibility
and its forbidden dependencies, and a mirrored `tests/unit/` directory. No package contains
an implementation. Layer ranks and forbidden edges are in `docs/architecture.md` §1 and are
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

Every cross-module public interface. Seeded from the §36 pipeline seams. **All rows are
`draft`. Nothing is frozen. Nothing may be frozen until the module contract document
("Prompt 02") exists — see OQ-009.**

Stability vocabulary: `draft` (may change freely) · `frozen` (change requires an ADR and
a coordinated update of every consumer) · `deprecated` (still present, has a named
replacement, has a removal date).

| Interface (planned) | Owning module | Consumers | Stability | ADR |
|---|---|---|---|---|
| `RawRecordBatch` | Data Adapter | Schema Mapper | draft | — |
| `SchemaMapping` | Schema Mapper | Entity Extractor, Event Generator | draft | — |
| `Entity` | Entity Extractor | Event Generator, Relationship Resolver, State Engine | draft | — |
| `Event` | Event Generator | Timeline Builder, State Engine, Temporal Graph Builder, Root Cause Analyzer | draft | ADR-0004, ADR-0007 (interval time), ADR-0008 (`is_actionable`), ADR-0020 (`trigger`) |
| `Timeline` | Timeline Builder | State Engine, Candidate Cause Generator | draft | — |
| `State`, `Transition` | State Engine | Temporal Graph Builder, Counterfactual Simulator | draft | — |
| `Relationship` | Relationship Resolver | Temporal Graph Builder | draft | — |
| `TemporalPropertyGraph` | Temporal Graph Builder | Candidate Cause Generator, Propagation Analyzer | draft | — |
| `CandidateEdge` | Candidate Cause Generator | Confidence Scorer | draft | — |
| `ConfidenceVector` | Confidence Scorer | Root Cause Analyzer, Intervention Optimizer, Explanation Generator | draft | — |
| `CausalGraph` | Confidence Scorer | Root Cause Analyzer, Propagation Analyzer, Counterfactual Simulator | draft | — |
| `RootCauseRanking` | Root Cause Analyzer | Explanation Generator, Intervention Optimizer | draft | ADR-0008 — carries `earliest_cause` and `actionable_root_causes` as two fields, never blended |
| `PropagationReport` | Propagation Analyzer | Intervention Optimizer, Explanation Generator | draft | — |
| `SimulatedWorld` | Counterfactual Simulator | Intervention Optimizer, Explanation Generator | draft | — |
| `Intervention` | Intervention Optimizer | Explanation Generator, Visualization API | draft | — |
| `Explanation` | Explanation Generator | Visualization API | draft | — |
| `EvidenceRecord` | Confidence Scorer | all downstream (LAW-EVIDENCE) | draft | — |
| HTTP API (prd.md §53) | Visualization API | Frontend | draft | — |

### Extension seams — what a new domain implements (`docs/architecture.md` §5)

Five of the six are data files; exactly one is code, and it reads bytes rather than
reasoning. Declared in `core/ports/` so a domain author has one place to look — declaring
them there does **not** license a reasoning package to import them (forbidden edge F3).

| Interface (planned) | Kind | Supplied at | Consumers | Stability | ADR |
|---|---|---|---|---|---|
| `SourceReader` | Protocol | an adapter package | Data Adapter | draft | — |
| `OntologySpec` | data | `ontology/<domain>/ontology.yaml` | Schema Mapper, Entity Extractor, Event Generator, State Engine | draft | ADR-0002; `event_type_is_actionable` added by ADR-0008 |
| `SchemaMappingSpec` | data | `ontology/<domain>/mapping.yaml` | Schema Mapper | draft | ADR-0002 |
| `RulePack` | data | `rule_engine/<domain>/` | Rule Engine, Candidate Cause Generator | draft | — |
| `CostModel` | data | `ontology/<domain>/cost.yaml` | Intervention Optimizer | draft | — |
| `PresentationLabels` | data | `ontology/<domain>/labels.yaml` | Explanation Generator, Visualization API | draft | — |

### Infrastructure ports (ADR-0014) — depended on by reasoning, implemented by `persistence`

| Interface (planned) | Owning package | Consumers | Stability | ADR |
|---|---|---|---|---|
| `FactRepository` | `core/ports` | Orchestration (wiring); reasoning via injection | draft | ADR-0014 |
| `GraphProjection` | `core/ports` | Temporal Graph Builder, Propagation Analyzer | draft | ADR-0001, ADR-0014 |
| `DerivedCache` | `core/ports` | Orchestration | draft | ADR-0014 |
| `AuditSink` | `core/ports` | all modules writing auditable events | draft | ADR-0014 |
| `Clock` | `core/ports` | any module needing an instant (time is injected, never read) | draft | ADR-0014 |

### Run and envelope types

| Interface (planned) | Owning package | Consumers | Stability | ADR |
|---|---|---|---|---|
| `RunKey` | `core/run.py` | Orchestration, `FactRepository` | draft | ADR-0013 |
| `OutputEnvelope` | `core/run.py` | every artifact, every API response | draft | ADR-0013 |
| `RawRecord`, `RawRecordBatch` | `core/ports/source.py` | Data Adapter, Schema Mapper **only** (LAW-EVENT) | draft | ADR-0004 |

---

## 7. Data contracts in force

| Contract | Version in force | Set by | Notes |
|---|---|---|---|
| `event_schema_version` | `unset` | Event Generator | semver; breaking change = major. `is_actionable` added 2026-08-23 (ADR-0008) — no bump, the contract is still `draft` and unversioned. |
| `entity_schema_version` | `unset` | Entity Extractor | semver |
| `edge_schema_version` | `unset` | Candidate Cause Generator | semver |
| `confidence_schema_version` | `unset` | Confidence Scorer | semver; component names are part of the contract |
| `ontology_version` | `unset` | `ontology/` | semver + `ontology_hash` |
| `dataset_version` | `unset` | Data Adapter | DataCo SMART Supply Chain; pin the exact source file hash |
| `graph_projection_version` | `unset` | Temporal Graph Builder | derived; = f(run_id) |
| `rule_pack_version` | `unset` | `rule_engine/` | semver; participates in `run_id` (ADR-0013) |
| `engine_version` | `0.1.0` | `causalog.ENGINE_VERSION` | semver; bump on any change that can alter output for identical inputs |

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
| ~~OQ-002~~ **RESOLVED 2026-08-23 by ADR-0007** | LAW-TIME requires strict `cause.ts < effect.ts`, but DataCo timestamps are day-granularity, so ties are common and legitimate edges are silently discarded. | Interval timestamps `[t_earliest, t_latest]` + `precision` enum. `cause.t_latest < effect.t_earliest` ⇒ CERTAIN. Overlap ⇒ `UNDETERMINED`; edge is retained but blocked from promotion to `INFERRED`. | **High.** Either mass loss of true edges (strict `<` on tied days) or mass admission of false edges (loose `<=`). Both invalidate root-cause output. | ADR-0007 (accepted). Retaining `UNDETERMINED` creates a new exposure: it may dominate on a day-granularity dataset — see R-14. |
| ~~OQ-003~~ **RESOLVED 2026-08-23 by ADR-0008** | Root Cause is defined twice: §12 ("could prevent downstream consequences") vs §29 ("would prevent the *largest* downstream impact"). Earliest and largest-impact disagree. | Adopt §29. Return two separate fields: `earliest_cause` (structural) and `actionable_root_causes` (ranked by impact-averted × confidence, tie-break earliest). | **High.** The headline output of the product means two different things to two modules; explanations contradict the ranking. | ADR-0008 (accepted). Actionability becomes ontology-declared and is stamped onto `Event` — see R-15. |
| ~~OQ-004~~ **RESOLVED 2026-08-23 by ADR-0001** | prd.md §42 splits Postgres (facts) / Neo4j (relationships) but names no source of truth and no sync mechanism. | Postgres is the system of record. Neo4j is a derived, rebuildable projection keyed by `ontology_version` + `dataset_version`. Direct writes to Neo4j are a defect. | **High.** Split-brain state; no transactional boundary; irreproducible graphs; determinism guarantee unenforceable. | ADR-0001 (accepted). *This row read as open until 2026-08-23 while §3 prose said it was resolved — a missed same-commit update, not a reopened question.* |
| OQ-005 | Confidence is a 0–1 float in §28 but LAW-EVIDENCE and §49 say a bare float is a defect. §20 additionally puts `Confidence` on `Event` itself, conflating extraction confidence with occurrence confidence and colliding with `OBSERVED` provenance. | `ConfidenceVector` with named components is authoritative; scalar is a derived non-authoritative rollup. Rename the event-level field `extraction_confidence`; `provenance_class` is primary on `Event`. | **Medium-High.** LAW-EVIDENCE violated by construction; UI displays a number nobody can decompose. | ADR-0009; must precede module 10 |
| ~~OQ-006~~ **RESOLVED 2026-08-23 by ADR-0010, matcher spec SUPERSEDED by ADR-0019** | LAW-DOMAIN lint is underspecified: (a) `core/` is not in the §43 repo structure; (b) case-insensitive substring matching false-positives on `ordering`, `reorder`, `recorder`, `border`; (c) §21's own event ontology is exactly the banned vocabulary. | (a) `core/` is added; §43 amended by ADR. (b) word-boundary regex + explicit allowlist. (c) §21 is a *DataCo ontology instance* under `ontology/`; ontology and rule **data** files are exempt, `rule_engine` **code** is not. | **Medium.** A lint that cries wolf gets disabled, and LAW-DOMAIN then holds by convention only — which is exactly the failure it exists to prevent. **Realised, in the other direction:** ADR-0010's word-boundary matcher cried wolf about nothing and caught nothing (DEF-0001). | ADR-0010 for `core/` and the exemptions; **ADR-0019 for the matcher** — stem-prefix, no suffix exceptions |
| OQ-007 | prd.md §33 promises counterfactual simulation over a graph whose edges are rule/statistics-derived, not identified causal effects. §16 already concedes causality is not proven. | V1 ships graph-surgery propagation over frozen edges, labeled `SIMULATED`, surfaced as a **plausibility simulation** with its no-unobserved-confounder assumption printed in the output envelope. Not a causal effect estimate. | **Medium-High.** Overclaiming. A user acts on a simulated number that has no identification argument behind it. | ADR-0011; must precede module 13 |
| ~~OQ-008~~ **RESOLVED 2026-08-23 by ADR-0003** | prd.md §38 requires determinism "when rules are explicit" while §41 lists pgmpy unqualified (DoWhy is marked future); `CONVENTIONS.md` §3 hardens this to byte-identical reruns. | V1 is fully deterministic (ADR-0003). Any nondeterministic component requires its own ADR and an explicit seed contract before introduction. | Medium. Determinism gate becomes unenforceable and silently drops out of the DoD. | ADR-0003 (accepted). *Second instance of the stale-row class that produced the OQ-004 slip: ADR-0003 answered this at the scaffold and the row was never struck. Now checked mechanically by `scripts/check_governance_consistency.py`.* Note the gate itself is still NOT-YET-RUNNABLE — see OQ-014. |
| OQ-009 | The module contract document ("Prompt 02") referenced by the Definition of Done does not exist. | No interface may be marked `frozen` until it exists. Registry rows stay `draft`. | Medium. Contracts get frozen by assertion rather than by specification. | Delivery of the prompt library |
| ~~OQ-010~~ **RESOLVED 2026-08-23 by ADR-0017** | Session ritual says `docs/prd.md`; the file is at `./prd.md`. | The file moved to `docs/prd.md`; the ritual is now correct as written. | Low, but caused a failed read at the start of every new session. | ADR-0017 (accepted) |
| OQ-011 | Phase grouping (P1–P5) in §3 is proposed by this document, not stated in the PRD. | Adopt as shown: P1 Ingestion (1–4), P2 Graph (5–8), P3 Inference (9–12), P4 Simulation (13–14), P5 Surface (15–16). | Low. Sequencing only; no contract depends on it. | Product owner ruling |
| ~~OQ-012~~ **RESOLVED 2026-08-23 by ADR-0020** | `Trigger` is a required `Event` field in §20 but is never defined, and collides with `Cause`. | `Trigger` = the proximate mechanism recorded *on* the event (intrinsic, `OBSERVED`). `Cause` = an inferred edge *between* events. See `GLOSSARY.md`. | Medium. Two fields mean the same thing; agents populate them inconsistently. | ADR-0020 (accepted). Inference may never read `Event.trigger`. |
| OQ-016 | The LAW-DOMAIN lint reads only `.py`, `.md`, `.sql`, `.cypher`, and still cannot catch domain dependence expressed as a branch on a data *value* rather than as vocabulary (ADR-0019). | Keep both residuals disclosed in `docs/architecture.md` §1.5 rather than implied. The value-branch hole is covered — imperfectly — by the planned ontology-swap test, not by any lint. | Medium. A green LAW-DOMAIN job is not proof of domain independence, and DEF-0001 showed how readily a green job is mistaken for one. | `tests/ontology/test_ontology_swap.py` (module 2) |
| OQ-014 | The determinism gate cannot run: `scripts/check_determinism.py` exits 2 (`NOT-YET-RUNNABLE`) because no orchestration pipeline entry point exists, and its CI job is `continue-on-error` for that reason alone. | Keep the script reporting the gap loudly rather than exiting 0. Remove `continue-on-error` at the P1 exit, when the pipeline first runs end to end. | **Medium.** A gate that cannot run looks identical to a gate that passes, and `CONVENTIONS.md` §3 lists determinism as a Definition-of-Done item for every module. | The orchestration pipeline (P1 exit) |
| OQ-015 | `docs/architecture.md` §1.2 and `scripts/check_layers.py` hold two copies of the layer-rank table, as `CONTEXT.md` §2 and `CONVENTIONS.md` §1 do for the Five Laws. Only the Laws have an automated copy check. | `tests/law/test_layer_boundaries.py` asserts every ranked package name appears in the document, which catches a removal but not a changed rank. Strengthen to a parsed comparison if the tables ever disagree in practice. | Low-Medium. A silently divergent rank table means the document teaches a rule the build does not enforce. | A stricter check, or a single generated source |
| OQ-013 | Intervention requires `Estimated Cost` (§32, §50) but DataCo carries no cost data. | Cost is ontology-supplied configuration, never inferred. Default to an ordinal scale (`LOW`/`MEDIUM`/`HIGH`) with provenance `ASSUMED`. | Medium. A fabricated cost silently drives the recommendation ranking. | ADR; must precede module 14 |

---

## 9. Known risks and current mitigations

Risks are prd.md §59 plus risks introduced by the execution model. "Current mitigation"
means *what is in force today* — `NONE YET` is an honest and expected value at P0.

| ID | Risk | Current mitigation | Owning module | Status |
|---|---|---|---|---|
| R-01 | Incomplete timestamps | Interval + precision representation (`CONVENTIONS.md` §10) with the three-valued `TemporalVerdict`. Never impute; missing ⇒ `UNKNOWN` precision, `ASSUMED` provenance, and barred from any `INFERRED` edge. | Event Generator | **in force (ADR-0007)**; implementation lands with module 4 |
| R-14 | **`UNDETERMINED` dominance.** ADR-0007 retains temporally ambiguous edges rather than guessing, so on a day-granularity dataset most candidate edges may be unpromotable and the causal graph correspondingly thin. | Disclosed, not mitigated — the ordering information is not in the data. Every run summary reports the CERTAIN/UNDETERMINED/VIOLATION ratio; a dominant `UNDETERMINED` share is reported as a finding about the dataset, never tuned away by loosening the test. | Candidate Cause Generator | accepted; measurable once module 9 runs |
| R-15 | **Mis-declared actionability.** ADR-0008 ranks root causes on an ontology-declared `actionable` flag. A wrong flag silently changes the headline ranking and nothing in the system can detect it. | Same treatment as OQ-013's cost: provenance `ASSUMED`, inspectable, surfaced in explanations. No ground truth exists to validate it against. | Root Cause Analyzer | accepted; revisit if ranking disputes recur |
| R-02 | Missing events | Timeline gap detection; explicit `gap` markers rather than interpolation. Explanations must state that a chain has gaps. | Timeline Builder | NONE YET |
| R-03 | Conflicting business rules | Rules are data, not code (prd.md §46). Conflict detection at rule-load time; a conflict is a load error, not a runtime coin-flip. `RuleConflictError` exists in the `core/errors.py` taxonomy; the detection does not. | Rule Engine | error type only |
| R-12 | **Projection rebuild on the critical path.** Neo4j being derived means graph availability is bounded by rebuild time, against the prd.md §55 target of graph generation under 60s. | Accepted, not mitigated. Rebuild stages into a new namespace and swaps atomically, so a slow rebuild degrades freshness rather than availability. | Temporal Graph Builder | accepted; revisit on the first measured rebuild over 60s |
| R-13 | **Recall bounded by rule coverage, silently.** A causal relationship not expressible as a rule is missed, and the system cannot report what it missed (ADR-0003). | Disclosed, not mitigated: explanations must state the limit. No metric can measure it — this dataset has no causal ground truth. | Candidate Cause Generator | accepted; revisit on labelled ground truth |
| R-04 | Noisy data | Validation stage rejects rather than repairs; rejects are counted and surfaced. | Data Adapter | NONE YET |
| R-05 | Hidden confounders | Cannot be mitigated, only disclosed. Every `INFERRED` and `SIMULATED` output carries an explicit no-unobserved-confounder assumption statement. | Confidence Scorer | proposed, see OQ-007 |
| R-06 | Correlation mistaken for causation | LAW-PROVENANCE separates `STATISTICAL` from `INFERRED`; promotion between classes is never silent. `GLOSSARY.md` disambiguates Correlation vs Causal Confidence. | Confidence Scorer | partially in force (law stated) |
| R-07 | Ontology mismatch | `ontology_hash` in every output envelope; mapping misses are hard errors, never defaults. | Schema Mapper | NONE YET |
| R-08 | **Cross-session context loss / silent contradiction** | These six governance files; the session ritual; the same-commit doc rule; `HANDOFF.md` staleness checks. | — | **in force as of 2026-08-23** |
| R-09 | Determinism erosion (unsorted iteration, float drift, random IDs) | Content-addressed IDs, canonical sort keys, quantized float serialization (`CONVENTIONS.md` §8). `PYTHONHASHSEED=0` in the Makefile, every CI job, and the backend image. `scripts/check_determinism.py` exists but **cannot run yet** — see OQ-014. | all | partially in force; gate NOT YET RUNNABLE |
| R-10 | Domain leakage into the reasoning core | LAW-DOMAIN lint (`scripts/check_domain_independence.py`, **stem-prefix** matching + exact-match allowlist + two-table self-test with a re-poisoning guard) **and** the layer lint's forbidden edge F3 (no reasoning package may import the ontology). Residual: neither catches a branch on a data *value* — see `docs/architecture.md` §1.5. | all core modules | **in force as of the ADR-0019 fix.** It was NOT in force between the scaffold landing and DEF-0001: this row claimed "in force as of 2026-08-23" while the shipped matcher caught only the bare English word in a comment. The claim is left visible here rather than overwritten. |
| R-11 | Overclaiming in the UI | Provenance classes visually distinct; "plausibility simulation" wording for counterfactuals. | Visualization API | proposed, see OQ-007 |

---

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
```
