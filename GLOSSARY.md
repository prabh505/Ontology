# GLOSSARY.md — Canonical vocabulary

Authoritative. A term used in code identifiers, API fields, ADRs, or UI copy that is not
defined here is a defect. Add the term in the same commit that introduces it. Never create
a second definition of a term elsewhere.

Every entry has three fields:
- **Definition** — what it is.
- **NOT** — what it is not. This field exists because the failure mode of a multi-session
  build is not missing definitions, it is *plausible wrong ones*.
- **Where** — the owning module from `CONTEXT.md` §3. `[planned]` means no code exists
  yet; no path here is a claim that a file exists.

Section 2 disambiguates the terms this project overloads. **Read section 2 before writing
any code that names a cause, a status, or a recommendation.**

---

## 1. Canonical terms

### Entity
**Definition.** An object that participates in events and persists across them, with a
unique ID, entity type, attributes, lifecycle, and current state (prd.md §12, §20).
**NOT.** Not a database row. Not a table. Not a state — an entity *has* states over time.
Not necessarily physical (a Region is an entity).
**Where.** Entity Extractor `[planned]`; type in `core/` `[planned]`.

### Event
**Definition.** A timestamped occurrence that changes the state of the system, and the
atomic computational unit of the engine (prd.md §12, §18; ADR-0004). Carries event ID,
time interval, event type, trigger, source entity, target entity, changed attributes,
metadata, provenance class, and evidence record IDs.
**NOT.** Not a row (see §2.3). Not a prediction. Not mutable — a correction emits a new
event. Not necessarily a failure; `ORDER_CREATED` is as much an event as `SHIPMENT_DELAYED`.
**Where.** Event Generator `[planned]`; type in `core/` `[planned]`.

### State
**Definition.** The condition of an entity at a specific time — the entity's condition
immediately after an event (prd.md §12, §20).
**NOT.** Not a status string from the source data (see §2.4). Not global — a state belongs
to exactly one entity. Not a time range by itself; a state plus its interval is a fact
about one entity over one span.
**Where.** State Engine `[planned]`.

### Transition
**Definition.** A movement between two states of the same entity, caused by an event
(prd.md §12, §20). Carries `from_state`, `to_state`, and the causing event.
**NOT.** Not a causal edge between events. A transition is intra-entity and `OBSERVED`; a
causal edge is inter-event and usually `INFERRED`.
**Where.** State Engine `[planned]`.

### Relationship
**Definition.** A structural, comparatively stable connection between entities — the
`BELONGS_TO`, `PART_OF`, `LOCATED_AT` class of links (prd.md §22).
**NOT.** Not causal. Not temporal. Relationships persist; events change the states of the
entities they connect.
**Where.** Relationship Resolver `[planned]`.

### Timeline
**Definition.** The temporally ordered sequence of events belonging to one operational
process instance (prd.md §24).
**NOT.** Not a causal chain — adjacency on a timeline implies ordering only, never
causation. Not a UI widget.
**Where.** Timeline Builder `[planned]`.

### Temporal Property Graph
**Definition.** The canonical graph structure holding entities, events, states,
transitions, and relationships with their temporal attributes, before any causal inference
(prd.md §40, §44 "No causal inference occurs here").
**NOT.** Not the causal graph. It contains `PRECEDES`, never `CAUSES`. Building it creates
no `INFERRED` assertions.
**Where.** Temporal Graph Builder `[planned]`.

### Causal Graph
**Definition.** The directed graph of inferred causal influence between events; nodes are
events, edges carry confidence, evidence, propagation weight, rule support, and statistical
support (prd.md §25).
**NOT.** Not a proven causal structure (prd.md §16). Not a Bayesian network. Not
necessarily acyclic — feedback loops are expected and are a feature (prd.md §31).
**Where.** Confidence Scorer `[planned]`; stored as the Neo4j projection (ADR-0001).

### Candidate Edge
**Definition.** A hypothesized causal link between two events, generated before scoring,
from temporal proximity, business rules, shared entities, shared identifiers, historical
frequency, ontology, or statistical association (prd.md §27).
**NOT.** Not a causal claim. Not yet confidence-scored. Its existence asserts only "worth
evaluating".
**Where.** Candidate Cause Generator `[planned]`.

### Confidence Vector
**Definition.** The decomposed, named-component confidence attached to an inferred edge or
recommendation: overall, rule support, historical support, temporal support, statistical
support, graph connectivity, evidence count (prd.md §49; LAW-EVIDENCE).
**NOT.** Not a probability. Not a bare float — a bare float is a defect. Not calibrated
against ground truth; no causal ground truth exists in V1 (ADR-0003).
**Where.** Confidence Scorer `[planned]`.

### Evidence Record
**Definition.** An immutable record of an observation that supports an assertion, linking
back to its source locator in the dataset. Every confidence component names the evidence
records that produced it.
**NOT.** Not the source row itself. Not mutable. Not optional — LAW-EVIDENCE requires it.
**Where.** Confidence Scorer `[planned]`; persisted in Postgres (ADR-0001).

### Provenance Class
**Definition.** The required, closed-set classification of how an assertion is known:
`OBSERVED | ASSUMED | STATISTICAL | INFERRED | SIMULATED` (LAW-PROVENANCE; prd.md §37;
ADR-0005).
**NOT.** Not confidence — provenance is *how we know*, confidence is *how sure we are*.
They are orthogonal: a low-confidence `OBSERVED` fact and a high-confidence `INFERRED`
edge are different in kind. Not merge-able. Not implicitly promotable.
**Where.** `core/` `[planned]`; enforced everywhere.

| Class | Means |
|---|---|
| `OBSERVED` | Present in the source data. |
| `ASSUMED` | Supplied by business assumption, ontology, or configuration; not observed. |
| `STATISTICAL` | Derived from association in the data; carries no causal claim. |
| `INFERRED` | A causal claim produced by the engine from rules, time, and evidence. |
| `SIMULATED` | Produced inside a counterfactual world; never history. |

### Ontology
**Definition.** The versioned, hashed data layer that defines domain vocabulary — entity
types, event types, states, legal transitions, relationship types, cost scales — and maps
dataset columns onto them (prd.md §35, §44; ADR-0002).
**NOT.** Not code. Not part of the reasoning engine. Not optional — an unmapped column is
a hard error, never a default.
**Where.** `ontology/` `[planned]`; consumed by Schema Mapper.

### Propagation
**Definition.** The transmission of effects through multiple events downstream of an
origin, measured by depth, breadth, duration, affected entities, economic impact,
operational impact, and confidence (prd.md §12, §30).
**NOT.** Not prediction — propagation describes what already spread through observed
history. Not the same as the count of downstream nodes; breadth and depth are separate
measures.
**Where.** Propagation Analyzer `[planned]`.

### Propagation Depth / Breadth
**Definition.** Depth is the longest causal path length from an origin event to a terminal
downstream effect. Breadth is the number of distinct events or entities affected at any
depth.
**NOT.** Interchangeable. A deep narrow chain and a shallow wide fan are different failure
shapes and must not be summarized by a single number.
**Where.** Propagation Analyzer `[planned]`.

### Feedback Loop
**Definition.** A cycle in the causal graph where downstream effects reinforce an upstream
cause (prd.md §31).
**NOT.** Not a bug in the graph. Not a data error. Detecting these is a product
requirement, which is why the causal graph is not constrained to be acyclic.
**Where.** Propagation Analyzer `[planned]`.

### Simulated World
**Definition.** A derived copy of the causal graph with one or more mutations applied, used
to evaluate a hypothetical. All assertions in it carry provenance `SIMULATED`
(prd.md §33).
**NOT.** Not a write to history — prd.md §33 requires that historical records are never
modified. Not a forecast of the future.
**Where.** Counterfactual Simulator `[planned]`.

### Validation Gate
**Definition.** The checklist a module must pass, with recorded evidence, before its status
may become `done` (`CONVENTIONS.md` §3).
**NOT.** Not code review. Not "tests passed" as a claim — the gate requires pasted command
output in `PROGRESS.md`.
**Where.** `PROGRESS.md`; run by an Opus-tier session (`CONVENTIONS.md` §2).

### Time Interval / Precision
**Definition.** The representation of an event's time as `[t_earliest, t_latest]` plus a
precision tag (`EXACT | SECOND | MINUTE | HOUR | DAY | UNKNOWN`) (`CONVENTIONS.md` §10).
**NOT.** Not a single datetime. Not a duration. Not imputable — a missing timestamp is
`UNKNOWN`, never filled in.
**Where.** `core/` `[planned]`; produced by Event Generator.

### Causal Edge types (prd.md §26)

| Type | Definition | NOT |
|---|---|---|
| **Direct Cause** | A produces B without an intermediary in the modeled graph. | Not "proven"; not "the only cause". |
| **Conditional Cause** | A produces B only when condition C holds. | Not a probability — the condition is explicit and checkable. |
| **Contributing Cause** | Several causes jointly produce an outcome; none is sufficient alone. | Not a ranked list — contributors are conjunctive, not competing. |
| **Amplifying Cause** | Increases the magnitude of a downstream effect without being its origin. | Not a cause of the effect's *existence*, only of its size. |
| **Inhibiting Cause** | Reduces propagation of a downstream effect. | Not the absence of a cause; an inhibitor is a positive, recorded event. |

### Run
**Definition.** The unit of reproducibility: the tuple `(dataset_version, ontology_hash,
rule_pack_version, engine_version, seed)` and every artifact derived from it (ADR-0013).
Identical tuple implies identical `run_id` implies byte-identical artifacts.
**NOT.** Not one execution of the pipeline — that is an *execution*, and the same Run may
be executed many times. Not a job, not a session, not a request.
**Where.** `core/run.py`; registered by Orchestration `[planned]`.

### run_id
**Definition.** The content-addressed identifier of a Run:
`"run:" + sha256(dataset_version | ontology_hash | rule_pack_version | engine_version |
seed)[:16]` (`CONVENTIONS.md` §9 scheme, ADR-0013). Every **inferred** artifact is scoped
to one. Observed facts are scoped to `dataset_version` instead, which is what prevents an
inference from ever overwriting an observation.
**NOT.** Not random. Not per-execution — see `execution_id`. Not excluded from determinism
comparisons; it is the thing determinism is asserted against.
**Where.** `core/run.py`; the `run` table; every `OutputEnvelope`.

### execution_id
**Definition.** The identifier of one process execution of a Run. Random, present in logs,
API correlation, and audit rows (ADR-0013, amending `CONVENTIONS.md` §8/§9).
**NOT.** Not a Run identity. Not stable across reruns — by design. Never a key for an
artifact. Explicitly excluded from every determinism diff by `scripts/check_determinism.py`.
**Where.** Structured logs; `OutputEnvelope`; the audit trail `[planned]`.

### Rule Pack
**Definition.** A versioned, conflict-checked set of causal rules expressed as **data**
under `rule_engine/<domain>/` (prd.md §46). `rule_pack_version` participates in the
`run_id`, so editing a rule creates a new Run.
**NOT.** Not source code. Not optional — a pack that contradicts itself raises
`RuleConflictError` at load time, never a runtime coin-flip.
**Where.** `rule_engine/` (data); loaded by `causalog.rule_engine` `[planned]`.

### Engine Version
**Definition.** The version of the reasoning code itself, participating in the `run_id`.
Bumped on any change that can alter output for identical inputs.
**NOT.** Not the package release version for its own sake, and not a marketing version. A
bug fix that changes a single edge is an engine-version bump.
**Where.** `causalog.ENGINE_VERSION`.

### Graph Projection
**Definition.** The Neo4j-resident, fully rebuildable derivation of PostgreSQL facts,
identified by `graph_projection_version` (ADR-0001).
**NOT.** Not a source of truth. Not repairable — a corrupt projection is rebuilt, never
patched. Not silently substitutable: a reader asking for a version the store is not serving
gets `ProjectionStaleError`, never older data.
**Where.** Built by Temporal Graph Builder `[planned]`; rebuilt by `scripts/rebuild_graph.py`.

### Port / Adapter
**Definition.** A *port* is a `Protocol` in `core/ports/` naming a capability a reasoning
package needs from infrastructure. An *adapter* is a concrete implementation under
`causalog.persistence`, wired only by `causalog.orchestration` (ADR-0014).
**NOT.** A port is not an interface between two reasoning modules — those are the
`CONTEXT.md` §6 registered types. An adapter is never imported by a reasoning package.
**Where.** `core/ports/`; `persistence/` `[planned]`.

### Layer Rank
**Definition.** The integer L0–L10 assigned to each package, defining which imports are
legal: a package may import its own rank and every lower rank, never a higher one
(`docs/architecture.md` §1.2).
**NOT.** Not a deployment tier. Not advisory — `scripts/check_layers.py` fails the build on
a violation.
**Where.** `docs/architecture.md` §1.2 and `scripts/check_layers.py`, which are two copies
of one rule; a divergence between them is a defect.

### Temporal Verdict
**Definition.** The three-valued result of testing LAW-TIME over two `TimeInterval`s
(ADR-0007): `CERTAIN` (`cause.t_latest < effect.t_earliest`), `VIOLATION`
(`cause.t_earliest >= effect.t_latest`), `UNDETERMINED` (the intervals overlap).
**NOT.** Not a confidence. Not a probability that the ordering holds. `UNDETERMINED` is not
"weak evidence of causality" — it is *no evidence about ordering*, and an `UNDETERMINED`
edge is retained but permanently barred from promotion to `INFERRED`.
**Where.** `core/temporal.py`; applied by Candidate Cause Generator `[planned]`.

### Actionability
**Definition.** Whether an event is one a human could have acted on — ontology-declared
configuration, per event type, stamped onto each `Event` as `is_actionable` at generation
time with provenance `ASSUMED` (ADR-0008). It is the criterion prd.md §29 ranks root causes
by: a storm is not actionable, a dispatch is.
**NOT.** Never inferred, never defaulted — an undeclared event type is an
`OntologyMappingError`. Not a property the reasoning core may look up: it lives on the
`Event` precisely so the Root Cause Analyzer never reads the ontology (forbidden edge F3).
Not verifiable — a mis-declared flag silently changes the ranking (`CONTEXT.md` R-15).
**Where.** `ontology/<domain>/ontology.yaml` (data); `core/types/event.py`; consumed by
Root Cause Analyzer `[planned]`.

### Graph relationship types (prd.md §47)
`CAUSES` · `PRECEDES` · `BELONGS_TO` · `LOCATED_AT` · `TRANSITIONS_TO` · `PART_OF` ·
`AFFECTS` · `BLOCKS` · `AMPLIFIES` · `REDUCES` · `RECOMMENDS`.

**Critical distinction:** `PRECEDES` is temporal and `OBSERVED`. `CAUSES` is causal and
`INFERRED`. Writing `CAUSES` where only ordering is known is the single most damaging
defect this system can contain. `PRECEDES` lives in the Temporal Property Graph;
`CAUSES` may only be written by the Confidence Scorer.

---

## 2. Disambiguation of overloaded terms

### 2.1 Cause vs Root Cause vs Trigger

| | **Cause** | **Root Cause** | **Trigger** |
|---|---|---|---|
| **Definition** | An event contributing to another event (prd.md §12). An inter-event relation. | The earliest **actionable** event whose modification would prevent the largest downstream impact (prd.md §29). | The proximate mechanism recorded *on* a single event — the immediate occasion of that event, as observed. A required `Event` field (prd.md §20). |
| **Scope** | A single edge between two events. | A ranked selection over a whole causal subgraph. | An attribute intrinsic to one event. |
| **Provenance** | Usually `INFERRED`. | `INFERRED`. | `OBSERVED` (it comes from the record). |
| **NOT** | Not a root cause. Not correlation. | **Not the earliest event** — prd.md §29 is explicit: a storm may be earliest while late dispatch is actionable. Not the most frequent event. Not unique — the output is a ranked list. | **Not a Cause.** A trigger is a property of an event; a cause is a relationship between events. If you are populating a field on an `Event`, you mean trigger; if you are drawing an edge, you mean cause. |
| **Where** | Candidate Cause Generator, Confidence Scorer `[planned]` | Root Cause Analyzer `[planned]` | Event Generator `[planned]` |

> **Ratified 2026-08-23.** prd.md defined Root Cause twice (§12 "could prevent downstream
> consequences" vs §29 "largest downstream impact"); **ADR-0008** adopts §29 and requires
> `earliest_cause` and `actionable_root_causes` as two distinct fields, never one blended
> answer — which is what §29's own storm/late-dispatch example asks for. `Trigger` was
> undefined in the PRD; **ADR-0020** ratifies the definition above and adds the binding
> rule that **no inference path may read `Event.trigger`** — reading it would turn an
> `OBSERVED` field into a causal claim that skipped the LAW-TIME and LAW-EVIDENCE gates.

### 2.2 Correlation vs Causal Confidence

| | **Correlation** | **Causal Confidence** |
|---|---|---|
| **Definition** | A statistical association between event types or attributes, computed from co-occurrence frequency. | The decomposed strength of belief that a specific causal edge holds, of which statistical support is **one named component** among several. |
| **Provenance** | `STATISTICAL` | `INFERRED` |
| **Direction** | Symmetric. | Directed, and constrained by LAW-TIME. |
| **Is it evidence?** | Yes — prd.md §9 Principle 3: "Correlation is evidence. Not proof." | It *aggregates* evidence, including correlation. |
| **NOT** | Not a cause. Not sufficient for an edge. Never displayed as causation in the UI. | **Not a probability.** Not calibrated (no causal ground truth exists). Not a single float — LAW-EVIDENCE. Not promotable from correlation without rule, temporal, and evidence support. |
| **Where** | Confidence Scorer, statistical component `[planned]` | Confidence Scorer `[planned]` |

> A correlation may never be promoted to an `INFERRED` edge silently. Promotion is an
> explicit, logged, evidence-bearing operation (ADR-0005).

### 2.3 Event vs Record vs Row

| | **Event** | **Record (Evidence Record)** | **Row** |
|---|---|---|---|
| **Definition** | Something that happened, at a time, to entities. The unit of reasoning. | An immutable pointer to an observation in the source data that supports an assertion. | A line in the source dataset. An input artifact. |
| **Cardinality** | One row may yield **0..N** events. | One per source observation used. | One per source line. |
| **Lives where** | Everywhere downstream of the Event Generator. | Postgres, referenced by ID. | **Only** in the Data Adapter and Schema Mapper. |
| **NOT** | Not a row. Not a DataFrame entry. | Not the row's contents — a locator plus metadata. | **Not a unit of reasoning.** LAW-EVENT: no row, DataFrame, or CSV column may exist downstream of the Event Generator. |
| **Where** | Event Generator `[planned]` | Confidence Scorer / persistence `[planned]` | Data Adapter `[planned]` |

> A DataCo row encodes order, shipping, and delivery moments with different timestamps.
> Treating it as one event destroys the temporal ordering the entire product depends on
> (ADR-0004).

### 2.4 State vs Status

| | **State** | **Status** |
|---|---|---|
| **Definition** | An engine concept: the condition of an entity at a time, produced by the State Engine from events, with a defined transition graph. | A raw source-data attribute — a string in a column, e.g. a delivery-status field. |
| **Provenance** | `OBSERVED` when directly evidenced, `ASSUMED` when derived from ontology rules. | `OBSERVED` only; it is input. |
| **Governed by** | The ontology's legal transition graph; an illegal transition is a hard error. | Nothing. The source system's conventions, which may be inconsistent. |
| **NOT** | Not a status string. Not free-text. | **Not a State.** A status is evidence *for* a state, never a state itself. Mapping status → state is the Schema Mapper's job and an unmapped status is a hard error, never a passthrough. |
| **Where** | State Engine `[planned]` | Data Adapter / Schema Mapper `[planned]` |

> Naming a variable `status` inside a core module is a smell and usually also a LAW-DOMAIN
> violation. The engine has states.

### 2.5 Intervention vs Recommendation vs Action

| | **Intervention** | **Recommendation** | **Action** |
|---|---|---|---|
| **Definition** | An **analytical construct**: a point in a causal chain where a change would interrupt propagation, with estimated cost, expected benefit, affected events, expected delay reduction, and confidence (prd.md §12, §32). | A **ranked, presented** intervention — the output surfaced to a user, ordered by benefit, cost, and confidence (prd.md §50). | Something a **human** does in the real world. |
| **Produced by** | Intervention Optimizer. | Intervention Optimizer + Explanation Generator, presented via Visualization API. | Not produced by this system at all. |
| **Provenance** | `SIMULATED` / `INFERRED`. | Inherits the weakest class of its inputs. | Outside the system. |
| **NOT** | Not a recommendation — an intervention may be identified and never recommended (too costly, too low confidence). | Not an action. Not a command. Not an instruction the system may execute. | **Never taken by the system.** Autonomous decision execution is explicitly out of scope (prd.md §6; `CONTEXT.md` §10). |

> The system recommends; a human decides and acts. Any code path that executes an
> intervention is a scope violation, not a feature.

### 2.6 Counterfactual vs Prediction

| | **Counterfactual** | **Prediction** |
|---|---|---|
| **Direction in time** | **Backward.** Re-evaluates a past world under a hypothetical change: "if inventory reconciliation had occurred within thirty minutes, would delivery still be delayed?" (prd.md §12, §33). | **Forward.** Estimates a future outcome from current state. |
| **Input** | An existing causal graph over observed history, plus a mutation. | Historical data plus a learned or fitted model. |
| **Provenance** | `SIMULATED`. | Would be a separate class; **the engine produces none in V1**. |
| **NOT** | **Not a prediction.** Not a causal effect estimate — V1's edges are rule- and statistics-derived, not identified causal effects, so the output is a *plausibility simulation* carrying an explicit no-unobserved-confounder assumption (`CONTEXT.md` OQ-007). Not a write to history. | **Not a product capability.** prd.md §62: this is not a machine learning model that predicts delays. Predictive maintenance and streaming inference are out of scope. |
| **Where** | Counterfactual Simulator `[planned]` | Nowhere. Intentionally. |

> If a session finds itself building a model that estimates a future outcome, it has left
> the product. Stop and re-read `CONTEXT.md` §1.
