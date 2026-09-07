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
**Where.** State Engine `[built]`.

### Transition
**Definition.** A movement between two states of the same entity, caused by an event
(prd.md §12, §20). Carries `from_state`, `to_state`, and the causing event.
**NOT.** Not a causal edge between events. A transition is intra-entity and `OBSERVED`; a
causal edge is inter-event and usually `INFERRED`.
**Where.** State Engine `[built]`.

### Relationship
**Definition.** A structural, comparatively stable connection between entities — the
`BELONGS_TO`, `PART_OF`, `LOCATED_AT` class of links (prd.md §22).
**NOT.** Not causal. Not temporal. Relationships persist; events change the states of the
entities they connect.
**Where.** Relationship Resolver `[planned]`.

### Timeline
**Definition.** The sequenced view of events belonging to one or more entities —
`PROCESS_INSTANCE` (one process definition's anchor entity, sequenced against its declared
steps), `ENTITY` (one entity's full observed participation, no process definition involved),
or `JOINED` (the composed merge of two or more already-built timelines, generic over what
kind of entity produced either input). A `Timeline`'s `entries` mix observed `EVENT`
positions with explicit `GAP` markers for a declared step no record witnessed.
**NOT.** Not a causal chain — adjacency on a timeline implies sequence only, never
causation. Not a UI widget. A `GAP` is never a fabricated event with a guessed timestamp.
**Where.** Timeline Builder `[built]`; the type itself is declared in `causalog.core`
(ADR-0042), alongside `Event`/`State`/`Transition`.

### Sequence Provenance
**Definition.** The field on a `TimelineEntry` (and, by the same rule, on a `State`'s
`held_over` interval) naming how confidently its position relative to its neighbour was
decided: `OBSERVED` when `core.temporal.verdict` returned `CERTAIN` for the adjacent pair,
`ASSUMED` when the verdict was `UNDETERMINED` (a tie or overlap) and the position was
settled by the documented, stable tie-break rule (`event_id`) instead (ADR-0043).
**NOT.** Not a claim about which event truly happened first when `ASSUMED` — it is a
rendering choice made for determinism, explicitly marked as one rather than left
indistinguishable from a verified sequence.
**Where.** Timeline Builder, State Engine `[built]`.

### Conformance Score
**Definition.** Per process instance: the count of a process definition's required steps
(`canonical_sequence` minus `optional_steps`) witnessed by that instance's events, divided
by the total required-step count. Reported per instance and as a dataset-wide distribution
in `TimelineQualityReport`.
**NOT.** Not a judgement about whether the instance is "correct" — a low score is a finding
about what the data contains, and is never used to reject or resort a timeline.
**Where.** Timeline Builder `[built]`.

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
necessarily acyclic — feedback loops are expected and are a feature (prd.md §31). **Not
ranked**: its edges are sequenced canonically, never by score, because ranking is module 11's.
**Where.** Confidence Scorer, `causal_engine/confidence_scorer` (ADR-0052); stored as the
Neo4j projection (ADR-0001). One `Scored Edge` per `(source, target, edge_kind)` — module 9's
parallel candidates are fused, because `CausalEdge.address` omits `generator_id`.

### Candidate Edge
**Definition.** A hypothesized causal link between two events, generated before scoring,
from temporal proximity, business rules, shared entities, shared identifiers, historical
frequency, ontology, or statistical association (prd.md §27). Realised as
`causalog.core.types.CandidateEdge` (ADR-0048), which **carries no confidence field at all**
— "generation never scores" is enforced by the type rather than by convention.
**NOT.** Not a causal claim. Not yet confidence-scored. Not a `Causal Edge`: that is module
10's artifact and it requires a `Confidence Vector`. Its existence asserts only "worth
evaluating".
**Where.** Candidate Cause Generator, `causal_engine/candidate_cause_generator`.

### Candidate Graph
**Definition.** The multigraph of `Candidate Edge` values one run produced: parallel edges
between the same pair of events are retained separately, one per generator, each with its
own evidence (prd.md §27, ADR-0048). Keyed
`(source_event_id, target_event_id, edge_kind, generator_id)`.
**NOT.** Not the `Causal Graph` — nothing here is scored or ranked. Not deduplicated: two
generators reaching one pair by different reasoning is the finding, not a collision.
**Where.** Candidate Cause Generator.

### Proximity Window
**Definition.** A pack-declared separation, in whole seconds with per-end inclusivity, within
which a sequenced event-type pair is admitted as a hypothesis (ADR-0049). Declared in
`rule_engine/<domain>/rules.yaml` under `candidate_generation.proximity_windows`, each with a
required `rationale` and `evidence_strength`.
**NOT.** Not a precedence claim — precedence is `core.temporal.verdict`'s answer and no
declared width can override it. Not calibrated: the DataCo widths are authored, bounded by
what the pack already declares, and unvalidated (risk R-16).
**Where.** Rule pack DSL; read by the Candidate Cause Generator.

### Possible Mediation
**Definition.** A flag recording that candidates `X→Z`, `X→Y` and `Y→Z` all exist, so the
direct `X→Z` claim may be wholly or partly carried through Y (ADR-0051).
**NOT.** Not a finding that mediation occurred, and not grounds for removing or
down-weighting the edge. Nothing in V1 resolves it.
**Where.** Candidate Cause Generator, as a separate `ConfoundingFlag` artifact.

### Possible Common Cause
**Definition.** A flag recording that candidates `X→Y`, `X→Z` and `Y→Z` all exist, so the
`Y→Z` association may be explained by the shared parent X rather than by any effect of Y on
Z (ADR-0051).
**NOT.** Not a finding of confounding. **And its absence is not evidence of no confounding**
— an unobserved common cause leaves no shape in a graph built from observed events, which is
exactly the class risk R-05 names.
**Where.** Candidate Cause Generator, as a separate `ConfoundingFlag` artifact.

### Confidence Vector
**Definition.** The decomposed, named-component confidence attached to an inferred edge or
recommendation (prd.md §49; LAW-EVIDENCE). **Eight** components at
`confidence_schema_version` 2.0.0: the six prd.md §49 names — rule support, historical
support, temporal support, statistical support, graph connectivity, evidence count — plus
`evidence_diversity` and `contradiction_freedom` (ADR-0052). Six are addends; two are `Gate
Component`s. Every one is emitted on every edge, always.
**NOT.** Not a probability. Not a bare float — a bare float is a defect. **Not calibrated
against ground truth**: no causal ground truth exists in this repository, so the scores are
internally consistent and nothing more (OQ-024). Not a set that may be short a component —
an absent measurement is emitted at zero and flagged, never omitted.
**Where.** Confidence Scorer, `causal_engine/confidence_scorer`.

### Gate Component
**Definition.** A confidence component that **caps** the scalar rather than contributing to
the weighted sum. Two of the eight are gates: `temporal_support` and
`contradiction_freedom`. Each maps through a piecewise-linear, non-decreasing ceiling, and
the scalar is the minimum of the addend mean and both ceilings (ADR-0052).
**Why.** A claim that A caused B without knowing A came first is not a weak causal claim; it
is not a causal claim. A gate cannot be outvoted by enough correlation, which an addend can.
**NOT.** Not a veto — a gate lowers a ceiling, it does not delete an edge. Not a penalty
subtracted from the total: every component still rises with support, which is what keeps the
aggregation monotone.
**Where.** `core.aggregation.gated_weighted_mean_v1`.

### Contradiction Freedom
**Definition.** The component scoring the **absence** of counter-evidence against a claim:
1.0 means nothing on record argues against it, 0.0 means a great deal does. Drawn from four
sources, weighted by how directly each bears: a `CONSTRAINT` prohibition on the pair, a rule
conflict touching a supporting rule, the reverse pair also being proposed, and confounding
flags naming the edge.
**NOT.** **Not a contradiction *penalty*, despite scoring the same thing** — it is inverted
deliberately, so that every component rises with support and the aggregation stays monotone.
A HIGH value means LITTLE counter-evidence. Not support: a claim nothing argues against still
needs evidence *for* it. Not a confounding resolution — a flag marks a structure that could
explain the association away, and nothing at V1 resolves one (`CONTEXT.md` R-05).
**Where.** Confidence Scorer.

### Evidence Diversity
**Definition.** How many **independent** lines of reasoning support a claim — distinct
evidence kinds and distinct generators — as opposed to how many justifications there are,
which is `evidence_count`. Normalized against what the run could actually reach.
**NOT.** Not volume: ten items of one kind score zero here and score well on
`evidence_count`. Not statistical independence — two generators can rest on the same
underlying coincidence in the data, and nothing detects that.
**Where.** Confidence Scorer. Computable only because module 9 keeps parallel candidates
apart rather than merging them (ADR-0050).

### Insufficient Evidence
**Definition.** The outcome assigned when fewer components carried real, non-missing support
than the rule pack requires. Such an edge **still carries a full confidence vector** —
LAW-EVIDENCE is not waivable — but it is given **no band** and is never promoted to
`INFERRED`.
**NOT.** **Not a low confidence score.** "We did not measure enough to say" and "we measured,
and the support is weak" are different findings, and showing the first as the second presents
a gap as a measurement. The same distinction module 9 draws between `NOT_RUNNABLE` and a
generator that ran and found nothing.
**Where.** Confidence Scorer; the floor is declared per pack (ADR-0053).

### Confidence Band
**Definition.** A published, plain-language reading of a scalar — for example "strong
evidence", "suggestive", "weak — inspect before acting". The threshold **and** the wording are
declared in the rule pack's `confidence_scoring.confidence_bands` (ADR-0053).
**NOT.** Not engine or UI policy: a boundary written into a component is one no reviewer can
find, no test can pin, and two screens can silently disagree about. Not invented when absent
— a pack declaring no bands gets no labels, and the report says which knob is missing.
**Where.** `rule_engine/<domain>/rules.yaml`; applied by the Confidence Scorer.

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
**Definition.** A cycle **over event types, across process instances**, in which downstream
effects reinforce an upstream cause (prd.md §31). Detected only when every link in the
circuit has temporally sound, promoted support and the supporting events span more than one
process instance.
**NOT.** Not a bug in the graph, and not a data error — detecting these is a product
requirement, which is why the causal graph is not constrained to be acyclic. **Not a cycle
over event instances**: a `CERTAIN` verdict is a strict precedence relation and strict
precedence admits no cycle, so an all-`CERTAIN` circuit over instances is arithmetically
impossible and every instance-level cycle is a [Temporal Artifact Circuit](#temporal-artifact-circuit).
**Where.** Causal Graph Builder `causal_engine/causal_graph_builder/cycles.py`.

### Temporal Artifact Circuit
**Definition.** A cycle in the causal graph at least one of whose links has no temporally
sound support — every claim behind it is `UNDETERMINED` or rests on an event the source
never placed in time. The circuit closes *because* precedence could not be resolved.
**NOT.** Not a feedback loop, and never reported as one. It is a statement about the
source's timestamp granularity, not about the domain, and it is rendered in its own section
of the Graph Quality Report so that no reader can act on it as a finding.
**Where.** Causal Graph Builder.

### Loop Gain
**Definition.** The product of the propagation weights around a detected feedback loop,
multiplied by the declared multiplier of any modifier member. Above 1.0 is reinforcing.
**NOT.** Not a test for reinforcement on its own. Propagation weights are normalized shares
in `[0, 1]`, so a product of them **cannot exceed 1.0**; only an amplifying member's
multiplier can lift a gain above one. Read it as a ranking between loops.
**Where.** Causal Graph Builder.

### Weakest Link
**Definition.** The member of a genuine feedback loop with the lowest propagation weight —
the cheapest place to break the circuit *in propagation terms*.
**NOT.** Not the cheapest intervention. Real intervention cost is the ontology-supplied
`CostModel` and is module 14's, not this number's. Never named for a circuit the engine does
not assert, because naming an intervention point on a data artifact invites acting on one.
**Where.** Causal Graph Builder.

### Promotion
**Definition.** The assignment of provenance `INFERRED` to a scored causal edge, under a
per-edge-kind threshold declared in the rule pack's `graph_construction` namespace. The
moment the engine begins to assert a claim rather than merely hold it (ADR-0054).
**NOT.** Not scoring — module 10 measures, this decides. Not reversible in place: promotion
is a revision producing a new version, never an edit. Never possible for a claim whose
LAW-TIME verdict is not `CERTAIN`, whatever its score.
**Where.** Causal Graph Builder `causal_engine/causal_graph_builder/policy.py`, and nowhere
else in the engine.

### Demotion
**Definition.** The record of a scored claim the engine considered and did not assert,
carrying a closed-set reason, a plain-language detail, and the claim's full lineage
including its whole confidence vector.
**NOT.** Not a deletion, and not a judgement that the claim is false. A demotion for
`NO_THRESHOLD_DECLARED` is a statement about the *pack*; one for `TEMPORALLY_UNVERIFIABLE`
is a statement about the *source*; only `BELOW_KIND_THRESHOLD` is about the claim. The
reasons are never summed into a single "rejected" count.
**Where.** Causal Graph Builder.

### Stated View
**Definition.** The subset of scored claims the engine is willing to assert — the promoted
edges of one run, published beside the rejection ledger of everything it declined.
**NOT.** Not the truth, and not a closed world. A cause absent from the stated view was not
ruled out: it was never proposed, never measured, or never cleared. The graph asserts what
it contains and nothing about what it omits.
**Where.** Causal Graph Builder, `PromotedGraph`.

### Orphan Effect
**Definition.** An event type with no promoted incoming edge — an outcome the engine offers
no account of.
**NOT.** Not evidence that the outcome has no cause. A coverage gap, reported as one, with
"nothing was ever proposed" kept distinct from "proposals were made and fell short".
**Where.** Causal Graph Builder, `GraphQualityReport`.

### Joint Cause Group
**Definition.** A set of two or more contributing causes that *jointly* produce one effect,
none sufficient alone (prd.md §26). Promoted all-or-nothing.
**NOT.** Not N independent edges, and the difference is not cosmetic: over an independent
edge, "what if this cause were removed" answers "the effect does not occur"; over one member
of a joint group the honest answer is "the effect may still occur, because the others
remain". Promoting a subset tells every downstream consumer the first answer.
**Where.** Causal Graph Builder; `ContributingCause` payload in `core/types/causal_edge.py`.

### Simulated World
**Definition.** A derived copy of the causal graph with one or more interventions applied,
used to evaluate a hypothetical. All assertions in it carry provenance `SIMULATED`
(prd.md §33).
**NOT.** Not a write to history — prd.md §33 requires that historical records are never
modified. Not a forecast of the future. **Not a container of historical types:** it holds
`SimulatedEvent` and `SimulatedInstant` and never `Event` or `TimeInterval`, so prd.md §37's
non-conflation holds at the type level rather than by a provenance field a consumer must
remember to read (ADR-0068).
**Where.** Counterfactual Simulator, `world.py`.

### Intervention Specification
**Definition.** One of five typed changes a hypothetical may express — shift an occurrence's
timing, remove one, insert one, change a declared changeable attribute, or change a
participant's state — addressed by content, and validated against the ontology before
anything is simulated (ADR-0066).
**NOT.** Not a free-form mutation. Not an `Intervention` in prd.md §32's sense: that is a
*recommendation* the Intervention Optimizer produces, with a cost and a benefit. This is the
input to a simulation, and it carries neither.
**Where.** Counterfactual Simulator, `intervention.py`.

### Rejected Intervention
**Definition.** A proposed change the engine refused before simulating anything, carrying the
declaration it was checked against and why it failed.
**NOT.** Not an error path. It is an artifact of equal standing to the world that WAS
simulated, on the Causal Graph Builder's rejection-ledger precedent (ADR-0054): a simulator
that reported only what it accepted would be asserting a conclusion while withholding the
alternatives. `DECLARATION_ABSENT` is kept distinct from every reason meaning "checked and
refused" — the first says the pack was never asked.
**Where.** Counterfactual Simulator, `intervention.py`.

### Support Envelope
**Definition.** For one quantity a hypothetical moves: the range the run actually witnessed,
the value the change asks for, the count the range was measured over, and the distance
between them against the pack's declared tolerance (ADR-0070).
**NOT.** Not the ontology's `admissible_range`, which is what the DOMAIN declares possible.
The two are deliberately in different places, because a value can be entirely possible and
entirely outside anything the data contains — and that is exactly the case an extrapolation
verdict exists to name. **Not a confidence interval and not calibration.**
**Where.** Counterfactual Simulator, `validity.py`.

### Extrapolation
**Definition.** A verdict, returned **instead of** a simulated figure, when a hypothetical
asks the graph about a region beyond the range the run witnessed plus its declared tolerance.
**NOT.** Not a warning printed beside a number. The verdict REPLACES the magnitude in the
rendered table, because a number a reader can copy will be copied and a caveat above a table
does not survive a screenshot. Not the same as `NOT_ASSESSABLE`, which says the data never
spoke to the question at all.
**Where.** Counterfactual Simulator, `ValidityVerdict`.

### Sensitivity Sweep
**Definition.** Recomputing a simulated outcome under each perturbation the pack declares, to
see whether the answer survives a change in an assumption the data cannot adjudicate.
**NOT.** Not a probability distribution. An absent perturbation set means **absent, not
stable** — the report says so rather than reporting that nothing moved.
**Where.** Counterfactual Simulator, `validity.py`.

### Simulated Instant
**Definition.** When something happens in a hypothetical world: two bounds, the precision
carried from the interval it derives from, the locator of that interval, and the signed shift
that produced it. Always `SIMULATED`.
**NOT.** Not a `TimeInterval`, and not convertible to one. `TIMESTAMP_PROVENANCE_CLASSES`
excludes `SIMULATED` and the frozen type was not widened to admit it: a simulated time
wearing the observed type would be prd.md §37's conflation at the level where it is hardest
to see (ADR-0068). Never narrows precision — a hypothetical may move an instant and may not
make the source more precise about it than the source was.
**Where.** `core/perturbation.py`.

### Validation Gate
**Definition.** The checklist a module must pass, with recorded evidence, before its status
may become `done` (`CONVENTIONS.md` §3).
**NOT.** Not code review. Not "tests passed" as a claim — the gate requires pasted command
output in `PROGRESS.md`.
**Where.** `PROGRESS.md`; run by an Opus-tier session (`CONVENTIONS.md` §2).

### Time Interval / Precision
**Definition.** The representation of an event's time as `[t_earliest, t_latest]` plus a
precision tag (`EXACT | SECOND | MINUTE | HOUR | DAY | UNKNOWN`), a provenance class
(`OBSERVED | ASSUMED | INFERRED`), and a required `source` naming the derivation or locator
that produced the bounds (`CONVENTIONS.md` §10; ADR-0021).
**NOT.** Not a single datetime. Not a duration. Not imputable — a missing timestamp is
`UNKNOWN`, never filled in. Not a total precedence relation: two intervals that overlap are
incomparable, and overlap is never "before".
**Where.** `core/temporal.py`; produced by Event Generator `[planned]`.

### Timestamp Kind
**Definition.** The derived label for a timestamp's shape: `EXACT` (one observed instant),
`INTERVAL` (pinned to a coarser granularity), `INFERRED` (bounds narrowed by derivation from
other evidence), `UNKNOWN` (never placed by the source). Computed from `precision` and
`provenance` (ADR-0021).
**NOT.** Not a stored field — deriving it is what stops it contradicting the two fields it
summarizes. Not a precision: `INFERRED` says how the bounds were obtained, not how tight
they are.
**Where.** `core/temporal.py`.

### Temporally Unverifiable
**Definition.** A flag on a `Causal Edge` recording that at least one of its two events has
an `UNKNOWN` timestamp, so no temporal assertion about the pair is possible (ADR-0022).
**NOT.** Not the same as `UNDETERMINED`. `UNDETERMINED` means the data placed both events
and could not separate them; *temporally unverifiable* means the data never placed one of
them. Not a silent pass — such an edge is retained, reported, and barred from promotion to
`INFERRED`.
**Where.** `core/types/causal_edge.py`; stamped by `CausalEdge.between`.

### Derived Precedence
**Definition.** A precedence that holds by ARITHMETIC rather than by observation, because the
source computed the later instant from the earlier one — column B equals column A plus a
recorded count. Measured, not assumed: a mapping declares a `temporal_derivation_check` and
module 1 tests it over every evaluable row, reporting an agreement rate and a residual
histogram (ADR-0057). Where confirmed, the pair's `temporal_support` is capped at the value
the rule pack declares in `derived_precedence_temporal_support`.
**NOT.** Not `UNDETERMINED`, and worth strictly less. An `UNDETERMINED` pair was placed twice
and could not be separated — genuine information the engine could not resolve; a derived pair
was placed once and the second instant is the first restated. Not a rejection either: the
precedence holds. What it lacks is any evidence that the precedence was *observed*. Not
inferred from a column's shape or name — an unmeasured suspicion produces nothing.
**Where.** Measured in `ingestion/data_adapter`; carried as `core.precedence.DerivedPrecedence`;
read by `confidence_scorer/scorers/temporal_support.py`.

### Rejected Proposal
**Definition.** One claim the gate or the per-effect cap refused, retained with the effect
event it was refused FOR — so "what was rejected for this outcome, and why?" is answerable at
instance level rather than only per generator (ADR-0058). Records are held under a declared
bound (`SAMPLED_REJECTIONS`); the per-effect COUNTS are complete regardless.
**NOT.** Not a `Candidate Edge` — nothing was constructed. Not complete coverage of every
rejection reason: `GENERATOR_NOT_RUNNABLE` is recorded when a generator never ran, so there
was no proposal and no effect to name, and it stays a per-generator count. Not a judgement
about the outcome — three of the four reasons are properties of the data and one is a bound
the run declared on itself.
**Where.** `causal_engine/candidate_cause_generator/graph.py`; populated in `generate.py`.

### Causal Edge types (prd.md §26)

| Type | Definition | NOT |
|---|---|---|
| **Direct Cause** | A produces B without an intermediary in the modeled graph. | Not "proven"; not "the only cause". |
| **Conditional Cause** | A produces B only when condition C holds. | Not a probability — the condition is explicit and checkable. |
| **Contributing Cause** | Several causes jointly produce an outcome; none is sufficient alone. | Not a ranked list — contributors are conjunctive, not competing. |
| **Amplifying Cause** | Increases the magnitude of a downstream effect without being its origin. | Not a cause of the effect's *existence*, only of its size. |
| **Inhibiting Cause** | Reduces propagation of a downstream effect. | Not the absence of a cause; an inhibitor is a positive, recorded event. |

Each kind is a **first-class payload type**, not a string label on a shared edge (ADR-0022):
`DirectCause` (no fields — the absence of extra data is the claim), `ConditionalCause`
(`condition_expression`, `condition_holds`), `ContributingCause` (`joint_cause_group_id`,
`co_cause_event_ids`), `AmplifyingCause` (`magnitude_multiplier > 1.0`), `InhibitingCause`
(`0.0 <= magnitude_multiplier < 1.0`). They form a discriminated union under
`CausalEdgePayload`, so an edge missing the data its kind requires cannot be constructed.
**Where.** `core/types/causal_edge.py`.

### Evidence Item
**Definition.** One independently re-verifiable reason an assertion is believed: a `kind`
drawn from the closed `EvidenceKind` set (prd.md §27), a description, the supporting
artifact identifiers, a strength, and — the load-bearing field — the exact rule identifier
or query text under `verification` (LAW-EVIDENCE).
**NOT.** Not an `Evidence Record`. A record is a *citation* into a dataset; an item is a
*justification* built on top of one. Not a confidence: confidence is a vector assembled from
many items. An item nobody can re-execute is a defect, not a weak item.
**Where.** `core/types/evidence.py`.

### Aggregator
**Definition.** A pure, named function from confidence components to a scalar rollup in
`[0.0, 1.0]`, registered by name in `AGGREGATORS` (ADR-0009). Two ship: `weighted_mean_v1`
(the default) and `minimum_v1` (conservative). The name travels with the data in
`ConfidenceVector.aggregation`.
**NOT.** Not a way of combining provenance — that is always the weakest class present, and
is computed separately. Not authoritative: the components are the value, the scalar is a
convenience.
**Where.** `core/aggregation.py`.

### Lifecycle
**Definition.** The ontology-declared state space an entity type may move through: the set
of legal state names and the legal moves between them. Carried on `Entity`, provenance
always `ASSUMED`.
**NOT.** Not learned from the data — the engine checks observations against the declaration
rather than inferring it. Not the entity's *current* state, which is a function of the
entity and an instant and is computed by `core.derivation.current_state`, never stored.
**Where.** `core/types/entity.py`.

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
under `rule_engine/<domain>/rules.yaml` (prd.md §46). `rule_pack_version` participates in the
`run_id`, so editing a rule creates a new Run. Six rule kinds: the five prd.md §26 causal
categories (`CAUSAL`, `CONDITIONAL`, `JOINT`, `AMPLIFICATION`, `INHIBITION`) plus
`CONSTRAINT`.
**NOT.** Not source code. There is no expression string, no callable reference and no plugin
hook anywhere in the schema. Not optional — a pack that contradicts itself raises
`RuleConflictError` at load time, never a runtime coin-flip.
**Where.** `rule_engine/<domain>/` (data); loaded and evaluated by `causalog.rule_engine`
(ADR-0044).

### Constraint Rule
**Definition.** A rule stating a structural impossibility — an entity in a named state
cannot participate in a named event type. It **prunes** candidates rather than proposing
them, which is why it is a sixth kind with no `CausalEdge` counterpart.
**NOT.** Not a negative causal rule, and not rankable. When a constraint and a generator
disagree the constraint wins, unconditionally and documented (ADR-0047) — a weight is a
strength of belief about a claim and a constraint is a statement of impossibility, and
comparing them would make impossibility purchasable with a large enough weight.
**Where.** `rule_engine/<domain>/rules.yaml`; applied by `causalog.rule_engine.evaluate`.

### Knowledge Provenance
**Definition.** Where a RULE's knowledge came from: `DOMAIN_EXPERTISE`,
`DATASET_OBSERVATION`, or `ASSUMPTION` (ADR-0045). Every rule declares one plus a non-empty
`evidence_basis`; an `ASSUMPTION` with an empty basis is refused at load.
**NOT.** Not `ProvenanceClass`, and the two are never combined. `ProvenanceClass` answers
*how a fact came to be known* and is folded by `core.aggregation.combine`; this answers
*where a policy came from*. A rule carrying `ASSUMED` would invite that fold and would claim
an assumption about the world is the same kind of thing as an unrecorded timestamp.
**Where.** `causalog.rule_engine.dsl.KnowledgeProvenance`.

### Rule Firing
**Definition.** One rule matching one binding of events, carrying the whole of its
reasoning: the bindings, the matched event identifiers, every condition evaluated with the
value it read, the observed separation, and the LAW-TIME verdict.
**NOT.** Not a causal edge — Module 9 owns the LAW-TIME gate and `CausalEdge` construction,
and this layer returns fired rule identifiers to it. Not a confidence: `base_strength` is the
rule's authored weight, the one admissible bare float here, named as `EvidenceItem.strength`
is named so it is not mistaken for a judgement. **A firing without its trace cannot be
constructed** (ADR-0047) — it raises, so it does not exist to be persisted or shown.
**Where.** `causalog.rule_engine.trace.RuleFiring`.

### Rule Coverage / Blind Spot
**Definition.** Which declared event types have a rule EXPLAINING them (naming them as a
consequent). A **blind spot** is a witnessable declared type that no enabled rule explains:
an occurrence of one can never receive an incoming candidate edge, so a root-cause query
reaching it stops there.
**NOT.** Not a quality score, and not a target to raise. Coverage is measured over
**declared** types, deliberately — the denominator that flatters a pack is the one that
hides a declared type having no rule. A type nothing can witness is reported separately, so
coverage cannot be raised by writing rules for types no record will ever produce.
**Where.** `causalog.rule_engine.coverage`; `scripts/check_rule_pack.py`;
`docs/reports/<domain>/rule-coverage.md`.

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
**Where.** `ontology/packs/<domain>/ontology.yaml`, in the `actionability` block of each
event type, alongside its `cost_class` and `severity_class` (ADR-0026);
`core/types/event.py`; consumed by Root Cause Analyzer `[planned]`.

### Domain Pack
**Definition.** One `ontology/packs/<domain>/ontology.yaml`: the complete declarative
description of a domain, in nine namespaces — event categories, cost classes, severity
classes, entity types, relationship types, event types, external event types, process
definitions, measurement definitions (ADR-0026). It is the `OntologySpec` seam
(`docs/architecture.md` §5.1) and the only place domain vocabulary may live.
**NOT.** Not code, and not extensible by code: there is no expression string, no callable
reference, and no plugin hook anywhere in the schema. Not a configuration file that the
engine falls back from — an unmapped value is a hard error, never a default. Not a
correctness guarantee: a pack that validates cleanly can still be semantically wrong
(`CONTEXT.md` R-16).
**Where.** `ontology/packs/`; loaded by `causalog.ontology_runtime`; specified in
`docs/ontology.md`.

### Pack Schema Version
**Definition.** The version of the **DSL itself** (`PACK_SCHEMA_VERSION`, `1.0.0`), declared
by every pack and identical across all of them. A pack declaring a different value is
refused rather than best-effort parsed.
**NOT.** Not `ontology_version`, which is each individual pack's own semver and moves
independently. Two numbers on purpose: one says which language the pack is written in, the
other says which revision of that pack this is.
**Where.** `causalog.ontology_runtime.dsl`; `CONTEXT.md` §7.

### Base Pack / Overlay
**Definition.** A pack may `extend` another. The **base pack** (`_base`) declares what is
true of every domain — today the ordinal cost and severity vocabularies and nothing else.
The **overlay** is the domain pack that extends it. Merging is by identifier, per namespace,
with **whole-entry replacement**: an overlay entry replaces the base entry entirely, a new
identifier is appended, and a base identifier is withdrawn only through an explicit
`removes:` block (ADR-0027).
**NOT.** Not a deep merge — the effective declaration would then exist in no file. Not
removable by omission: omission and decision must not be the same text, so a withdrawal that
removes nothing is a load error.
**Where.** `ontology/packs/_base/`; `causalog.ontology_runtime.resolution`.

### Derived Event Type
**Definition.** An event type the source **implies rather than logs** — declared
`observation: DERIVED`, carrying a `derivation.basis` naming what it is reconstructed from
and a `default_confidence` (ADR-0029). The canonical case: DataCo records a shipping date
column and no dispatch record, so `SHIPMENT_DISPATCHED` is derived from the date.
**NOT.** Never `OBSERVED`. A derived event may not claim observed provenance, and the loader
refuses a pack in which one does. The distinction is load-bearing because a fabricated
occurrence with a real column standing behind it reads as *better* evidence than an honest
gap. Not the same as a low-confidence observation: provenance is how a thing came to be
known, confidence is how sure we are (`docs/contracts.md` §4).
**Where.** `ontology/packs/<domain>/ontology.yaml`; enforced in
`causalog.ontology_runtime.dsl` and `structural.py`.

### Process Definition
**Definition.** A named canonical flow: the expected happy-path sequence of event types for
one anchor entity type, plus its declared variants, optional steps and repeatable steps. It
is what the Timeline Builder groups against and the Rule Engine reasons against.
**NOT.** Not a constraint. A run that departs from the canonical sequence produces a
*finding*, never a rejected record — the process states what was expected, not what is
permitted.
**Where.** `ontology/packs/<domain>/ontology.yaml`, `process_definitions`.

### Emission Rule
**Definition.** The machine-readable statement of **which records witness one event type's
occurrence**: a closed `ConditionExpression` operator tree plus a declared `occurred_at`
policy, one per event type, in `ontology/packs/<domain>/mapping.yaml` (ADR-0039). It is the
executable half of a Derived Event Type's `derivation.basis`, which is prose.
**NOT.** Not a statement about the domain — that is the basis, and it lives in the pack so a
second dataset for the same domain reuses it unchanged. Not a place a provenance class can
be named: an emitted event takes the class its event type declares, so a rule has no path to
an `OBSERVED` event. Not an expression string; a data file that becomes executable defeats
review and hashing alike (ADR-0026, ADR-0039).
**Where.** `ontology/packs/<domain>/mapping.yaml`, `event_emissions`; schema in
`causalog.ingestion.schema_mapper.dsl`; evaluated in
`causalog.extraction.event_generator.conditions`.

### Occurrence
**Definition.** One thing that happened, as distinct from the records that witness it. Two
records agreeing on event type, participants, interval and recorded attributes witness ONE
occurrence and become ONE `Event` whose `evidence_record_ids` names both.
**NOT.** Not a record. On a source whose records are sub-items of a larger transaction,
emitting one event per record multiplies every downstream count by the average sub-item
count — which looks, from the inside, exactly like a busier business.
**Where.** `causalog.extraction.event_generator.emit.occurrence_key`.

### Process-Coverage Gap
**Definition.** A step a Process Definition expects for one anchor entity and no event
supplies. Reported per process, per step, with the count of instances expecting it and
whether **any** record could ever witness it.
**NOT.** Not one thing. A step absent from ONE instance is a fact about that instance; a
step absent from EVERY instance because no emission rule can witness it is a fact about the
source, and it bounds every conclusion drawn around it. Collapsing the two buries the second
inside the first. Not an error, and never filled: under the default `RECORD_GAP` policy no
event is fabricated (ADR-0040).
**Where.** `causalog.extraction.event_generator.coverage`; reported in the Event Quality
Report.

### Reconciliation Report
**Definition.** Module 3's account of identity resolution: entities created, records merged
into an existing entity, entities carrying a recorded attribute disagreement, records naming
no derivable key, and attribute versions — per entity type, with the active `ConflictPolicy`.
**NOT.** Not a log line. Identity resolution is the one step whose mistakes are invisible
afterwards: two participants merged into one produce a graph that is well-formed,
self-consistent and wrong. Not a function of the policy: every disagreement is reported
under every policy that tolerates one, because a report that could be quieted by
configuration is a report about configuration.
**Where.** `causalog.extraction.entity_extractor.report`.

### Event Quality Report
**Definition.** Module 4's account of the event log it produced: counts by type and by
provenance class, the timestamp-precision and timestamp-kind distributions, orphan events,
conditions that could not be evaluated, process coverage per definition, and the active
missing-event and conflict policies.
**NOT.** Not optional, and not a score. The causal engine's honesty depends on knowing what
it does not have — a graph built on an unmeasured event log looks exactly like one built on
a complete log, and the difference surfaces only as a confident wrong answer. It carries no
grade, because a report that scored itself would invite tuning the score.
**Where.** `causalog.extraction.event_generator.quality`.

### Attribute Version
**Definition.** One recorded value of one attribute of one entity, with the instant the
source dates its statement to (the identity binding's declared `observed_at`), its citation,
and whether a later version supersedes it.
**NOT.** Not a field of `Entity`. The entity's content address deliberately excludes its
attributes, so enriching an entity must not rename it (`docs/contracts.md` §5); a version
carried inside would either mutate a frozen artifact or mint a second identifier for one
participant. Not a record of when the value CHANGED — no source in this project records
that. A version exists only where the value differed from the one already held; a record
that repeated what was known introduces nothing.
**Where.** `causalog.extraction.entity_extractor.versioning`.

### Measurement Definition
**Definition.** How one domain metric (a delay, a cost, an impact) is computed from event
attributes, expressed as a closed declarative operator tree — `CONSTANT`, `ATTRIBUTE`,
`SUM`, `DIFFERENCE`, `PRODUCT`, `RATIO`, `DURATION_BETWEEN`, `MINIMUM`, `MAXIMUM`
(ADR-0026). It exists so that no metric formula is hardcoded in a reasoning module.
**NOT.** Not an expression string and not evaluated by the ontology layer. A tree can be
inspected, diffed and hashed without being executed; a string has to be executed before
anyone knows what it says. A metric the operator set cannot express requires a new operator
and an ADR, never an escape hatch.
**Where.** `ontology/packs/<domain>/ontology.yaml`, `measurement_definitions`.

### Cost Class / Severity Class
**Definition.** Pack-declared ordinal vocabularies, each member carrying an explicit `rank`.
An actionable event type names a `cost_class`; every event type names a `severity_class`.
Root-cause ranking and intervention costing read the ranks.
**NOT.** Not names the engine knows — a ranker compares `rank` and never reads the
identifier, which is what lets an unrelated domain declare an unrelated vocabulary. A cost
class is not a currency amount: `cost.yaml` maps the class to an ordinal band, and no
monetary figure is ever inferred (`CONTEXT.md` OQ-013).
**Where.** `ontology/packs/_base/ontology.yaml`, inherited by every domain.

### ontology_hash
**Definition.** The content address of a **resolved** pack:
`digest(ONTOLOGY, to_canonical_json(resolved_pack))`, rendered `ont:<16 hex>` (ADR-0028). It
participates in `run_id` (ADR-0013).
**NOT.** Not a hash of the file. It is invariant to comments, indentation, key sequence, and
how a pack was split across an inheritance chain — none of which changes what the pack says
— and sensitive to every declared value. Not a statement about correctness: it establishes
identity only.
**Where.** `causalog.ontology_runtime.hashing`; `CONTEXT.md` §7.

### NOT_RUNNABLE (diagnostic severity)
**Definition.** A pack diagnostic reporting a check the validator **could not perform**,
distinct from `ERROR` (the pack is refused) and `WARNING` (it is not). Emitted by the
ontology loader (`ONT-N-RULE-COVERAGE`, when no rule pack is supplied) and by the rule
loader (`RUL-N-VOCABULARY`, when no ontology is supplied; `RUL-N-CONDITIONAL-CONFLICT`, for
the contradictions no static check can decide).
**NOT.** Not a passing check, and never silently omitted. It exists because this repository
has twice mistaken an unrunnable check for a passing one — DEF-0001, where a lint matched
nothing, and OQ-014, where a determinism gate has no pipeline to run against.
**Where.** `causalog.ontology_runtime.diagnostics`.

### Graph relationship types (prd.md §47)
`CAUSES` · `PRECEDES` · `BELONGS_TO` · `LOCATED_AT` · `TRANSITIONS_TO` · `PART_OF` ·
`AFFECTS` · `BLOCKS` · `AMPLIFIES` · `REDUCES` · `RECOMMENDS`.

**Critical distinction:** `PRECEDES` is temporal and `OBSERVED`. `CAUSES` is causal and
`INFERRED`. Writing `CAUSES` where only ordering is known is the single most damaging
defect this system can contain. `PRECEDES` lives in the Temporal Property Graph;
`CAUSES` may only be written by the Confidence Scorer.

### Valid Time
The interval over which the world was in a described condition — `State.held_over`,
`Relationship.valid_over`. One of the two axes of [[Bi-temporal]] storage. It is the
interval the reasoning core computes over, and it is the only one of the two that appears
in a content address.

### System Time
The interval over which *this system believed* something — `system_from` to `system_to`,
where `'infinity'` means "still believed". Database-managed. It appears in no
`causalog.core` type, in no content address, and in no output envelope, and no reasoning
module may read it: an identifier that depended on insertion wall-clock would stop being
reproducible (ADR-0013). Closing a system period is the single mutation the fact store
admits.

### Bi-temporal
Carrying Valid Time and System Time as two independent axes (ADR-0032). Applied to
`state`, `state_transition`, and `relationship`, because those are the artifacts a
re-inference can legitimately restate. A correction **inserts** a superseding row and
**closes** the prior belief; it never edits one. Without the second axis a re-derivation
would overwrite the interval a past conclusion was computed against, and that conclusion
would become unreproducible, unauditable, and incomparable at the same moment — silently.

### Retraction
Closing a belief's System Time. It records that the engine has stopped believing something;
it does not remove what the engine believed. Not a deletion: every past conclusion computed
against the retracted belief would otherwise become unauditable.

### Schema Migration
One numbered, raw-SQL change to the PostgreSQL schema, shipped with its exact reverse under
the same basename (ADR-0033). `NNNN_<verb>_<subject>.sql`. There is no ORM and no migration
framework (ADR-0015); the numeric prefix is the only thing ordering the series.

### Migration Ledger
`schema_migration` — the authority on what schema a database holds, recording each applied
migration's version, name, content hash, instant, and duration. A schema whose ledger is
empty is indistinguishable from an unmigrated one, which is why the PostgreSQL init
directory is not used to apply migrations: it applies them without writing a ledger.

### Projection Namespace
The identifier of one build of the [[Graph Projection]], stamped on every node and
relationship it contains. Staging a rebuild into a new namespace is what lets the live
projection keep serving while a rebuild runs, and what makes a failed rebuild harmless.
Which namespace is live is recorded in PostgreSQL, never asked of the graph store — the
derived store has no authority (ADR-0001).

### Projection Content Hash
A canonical hash over the sorted token stream of one projection namespace. Two rebuilds of
one `run_id` must produce the same hash; a difference is a **determinism defect**, not a
retryable error, because it means something in the pipeline is not a function of its
inputs. `graph_projection_version` = `gpv:` + `digest(run_id | content_hash)`.

### Staging Table
An `UNLOGGED` mirror of a target table, used only by the bulk ingestion path. Rows are
`COPY`d into it and then promoted with `INSERT … SELECT … ON CONFLICT DO NOTHING`, which is
how the load stays idempotent — `COPY` cannot express a conflict clause. Dropped inside the
same transaction; nothing ever reads one.

### Dataset Pin
`datasets/<dataset_id>.pin.json`. The committed statement of exactly which bytes a run
consumed: source file name and publisher, byte count, `content_sha256`, row count, header,
the codec chosen and the codecs rejected, plus the mapping and ontology identities. The data
itself is not committed, so the pin is the only durable description of it. **It carries no
timestamp** — a `pinned_at` field would make two runs over identical inputs differ, which is
the determinism guarantee failing in the one artifact whose job is reproducibility.

### Schema Mapping
`ontology/packs/<domain>/mapping.yaml`, extension seam 3. Binds source columns and source
values to ontology concepts through a **closed** transform registry. Distinct from the
**ontology pack**, which describes the domain: the pack says what an `ORDER` is, the mapping
says which column carries one. Versioned (`mapping_version`) and content-addressed
(`mapping_hash`, prefix `map:`).

### Mapping Proposal
A machine-generated `mapping.yaml` carrying `status: PROPOSED_UNCONFIRMED`, produced by
`suggest_mapping` from a column profile and a pack. **The loader refuses it.** That refusal
is the entire human-confirmation mechanism: a human reads every binding and its stated
`basis`, corrects what is wrong, and removes the status line in a commit. A proposal is never
a mapping.

### Data Quality Report
`docs/reports/<dataset_id>/<dataset_version>/data-quality.{json,md}`. One model, two
renderings, generated from the same object so they cannot disagree. Canonical JSON, so two
imports of one file produce identical bytes and an identical `report_sha256`. Committed; the
data it describes is not.

### Headline Constraint
A limitation that bounds what any downstream conclusion about a dataset may claim, rendered
**first** in both report forms. Distinct from a **finding**: a finding says something is
wrong with the data and can be fixed; a headline constraint says something is permanently
true about what the data can support and can only be known about. Every one carries the
measurement behind it — a constraint asserted without a number is an opinion.

### Downstream Consequence
A required, non-empty field on every validation rule and every coverage finding, naming what
stops working. `min_length=1` on the model, so a rule cannot be registered without one. A
finding without a consequence is an observation, and observations are what reports get
ignored for.

### Quarantine
`datasets/clean/<dataset_version>/quarantine.jsonl`. A row withheld from the clean layer,
written out in full with the rule codes that put it there. **Nothing is dropped silently:**
`rows_read == rows_clean + rows_quarantined` is asserted at the end of every import, and the
run raises rather than publishing a report whose own arithmetic disagrees with itself.

### Clean Layer
`datasets/clean/<dataset_version>/`, holding `records.jsonl`, `quarantine.jsonl` and
`cleaning_ledger.jsonl`. A **new, versioned** layer; the raw file is opened read-only and is
byte-identical afterwards. Cleaning never edits its own evidence, because the record a
conclusion cites must still say what it said when the conclusion was drawn (LAW-EVIDENCE).

### Cleaning Ledger
One receipt per `(transform, column)`: the rule, the count of rows changed, a before/after
example, the rationale, and the provenance class. The complete list of differences between
the raw bytes and the clean layer.

### Manufactured Precision
A source column that displays more precision than it observed — typically because its value
is arithmetic on another column. Distinct from **coarse** precision, and worse: a coarse
column announces its limits, while a column showing `22:56` because a different column said
`22:56` does not. Detected only where a mapping declares a `temporal_derivation_check`, which
the adapter then measures. Risk R-20; observed in the reference dataset (DEF-0004).

### Granularity
How finely a source pins an instant down, measured rather than inferred from a format
string. Reported per temporal column as the count of values carrying a real time component.
A column is **date-granular** when no parsed value pins anything finer than a calendar day —
which makes two events on one date OVERLAP, so `core.temporal.verdict` returns
`UNDETERMINED` and no edge between them can be promoted to `INFERRED`.

---

### Graph Standing
Which graph a traversal walked, and therefore whether the engine stands behind what it
found. `STATED` walks the promoted graph and its findings are the engine's. **`UNPROMOTED_DIAGNOSTIC`
walks the scored graph before promotion and its findings are disowned** — refused `INFERRED`
by a validator, printed under a fixed notice, written to separate files, and refused as input
by everything downstream. A required field with no default on every artifact modules 11 and 12
and the pattern miner produce (ADR-0059).

### Consequence Set
The set of nodes reachable downstream of a seed, keyed by event identifier and validated
sorted and unique at construction. **The unit of attribution.** A consequence reachable four
ways is one consequence and contributes its magnitude once; the routes are reported as
structure (`route_count`) and multiply nothing (ADR-0061).

### Path Composition
How the per-link confidences along a chain compose into one belief about the chain.
Distinct from **aggregation**, which rolls one claim's components into one scalar. The
composition function is named on every artifact, as an aggregation is. `weakest_link_v1` (the
minimum) is the default; `independent_product_v1` is registered beside it and reported in its
own column, never blended (ADR-0060).

### Plateau
Several candidates carrying one identical composed value or sequencing value, so the engine
cannot separate them. **A plateau is not a ranking.** It is reported as a plateau and the tie
is not broken: any sequence imposed on tied candidates is arbitrary, and breaking it on
earliness would reintroduce the blend ADR-0008 forbids. On the measured slice 310 scored links
sit at exactly 0.400000, so plateaus are common rather than exceptional.

### Counterfactual-Lite
The purely structural question "what does the graph say stops occurring if this node is
removed", answered by re-running reachability with the node deleted and diffing —
`reachable(seed) \ reachable(seed, excluding=n)`. **A re-reachability diff, not a subtraction:**
a consequence with another surviving ancestor does not disappear, which is what makes it
correct on a diamond. Not a causal effect estimate; module 13's simulation is a different and
larger claim (ADR-0061).

**How module 13's claim is larger.** Counterfactual-lite answers one question — what stops
being reachable — and answers it over node removal alone. A simulation applies five typed
changes, validates each against the ontology, propagates per edge KIND (a contributing cause
removed reduces rather than eliminates), recomputes magnitudes through declared measurement
trees, re-times what the source computed, and returns a validity assessment. Both are graph
surgery over frozen links and neither identifies a causal effect; the second says more, and
therefore has more to be wrong about, which is why it carries an envelope and a verdict and
the first does not.

### Eliminated vs Reduced
| | **Eliminated** | **Reduced** |
|---|---|---|
| **Claim** | Nothing transmits into this consequence any more, so the graph says it would not have happened. | It still would have happened, and would have been smaller. |
| **Established by** | Re-reachability over the graph. A fact about the graph's shape. | Arithmetic over the apportioned shares of the causes that stopped. |
| **Typical cause** | The one link carrying it was removed. | One of several joint causes was removed and the others survive. |
| **NOT** | **Not "the removed shares summed to one."** Shares summing to one under an apportionment is an arithmetic coincidence; nothing reaching a consequence is a fact. Reading the first as the second is how a partial removal comes to be reported as a prevention. | **Not "prevented."** |
| **Where** | `WorldDiff.eliminated_event_ids` | `WorldDiff.reduced_event_ids` |

> **The two are never summed and never merged into one headline.** This is the single most
> common counterfactual error, and it is held apart by two accessors on a type rather than by
> care taken at a call site.

### Motif
A recurring cause-type-to-effect-type shape in the event-TYPE projection, above a declared
support threshold. Always reported with the number of **process instances it spans**, because
one shape repeating inside a single instance is a local pathology and the same count across
many instances is systemic, and one number cannot tell them apart (ADR-0064).

### Chronic Bottleneck
An event type sitting on many claims in the type projection. In-degree and out-degree are
reported separately and **never summed**: a type consequence collects at and a type consequence
originates from are different structures needing different responses (ADR-0064).

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

### 2.7 Request Id vs Correlation Id

**They are the same thing, and only one of the names is correct here.**

prd.md §54 and the persistence brief speak of a *request id*. `CONVENTIONS.md` §8 and this
glossary define that identifier as **`correlation_id`**: the identifier threading through
one API request, present on every log record and every audit entry that request produced.

`CONTEXT.md` §5 is explicit that a term used in code identifiers, API fields, or ADRs that
is not in this glossary is a defect, and that a second definition of an existing term is
also one. So there is no `request_id` column and no `request_id` field. The synonym is
recorded in `docs/data-model.md` §9 so that a reader arriving from prd.md §54 finds the
mapping instead of concluding the requirement was dropped.

Distinct from `execution_id` (one pipeline execution, random, excluded from determinism
comparisons) and from `run_id` (content-addressed, stable across reruns, included).

---

## Module 14 terms (ADR-0073 through ADR-0079)

### `risk_class` — and how it differs from `severity_class`

**The operational risk of TAKING an act**, declared per event type in the ontology pack as a
member of the `risk_classes` ordinal vocabulary (ADR-0073). Provenance is pinned to `ASSUMED`:
no observation in any dataset establishes what taking an act risks (R-25).

**`severity_class` is not this and must never be substituted for it.** Severity describes the
occurrence being acted ON; risk describes the ACT. A cheap act against a critical occurrence
can be entirely safe to take, and an expensive act against a minor one can still destabilise
the process around it. Conflating them would make prd.md §50's fourth objective a restatement
of a quantity the ranking already reads.

**Absent is not `NEGLIGIBLE`.** An actionable type may omit `risk_class`; it is then reported
`NOT_DECLARED` and costs the candidate its whole risk term in the scalarization. An actionable
type may NOT omit `cost_class`, because an absent cost would rank it as free.

### Cut set

A set of acts whose removal disconnects the largest number of **(source, outcome) pairs**.
Pairs, never routes: two routes between one source and one outcome are one chain, because they
are one thing an operator cares about (ADR-0076, ADR-0061's ruling in a new place).

A cut set is **`EXACT`** — enumerated, provably minimal — or
**`GREEDY_NOT_PROVEN_MINIMAL`**, which is often minimal and is never claimed to be.

### Portfolio benefit, and overlap loss

The benefit of a SET of acts, obtained by simulating the whole set in one call to module 13
(ADR-0077). **Never the sum of its members' benefits.** `overlap_loss` is the gap between the
naive sum and the joint figure, published so the non-additivity is visible rather than merely
corrected — and withheld, with a reason, when the members do not interact, because the two
totals are then not comparable.

### Desirability — and why it is not called a score

The scalarized trade-off across benefit, cost, belief and operational risk, produced by a
**named** function in `core.scalarization` under weights the rule pack declares (ADR-0078).
prd.md §50 calls it an "impact score"; this glossary does not, because a score reads as a
property of the act and this is a property of one weighting **of** the act.

Always published beside `on_pareto_frontier`, which is weight-independent and therefore the
stronger claim: nothing else beats this act on all four objectives at once.

### Belief floor — a gate, not a term

`recommendation.minimum_belief_to_publish`. A candidate below it is **withheld** to the ledger
naming the threshold, never published low down a ranked list. A weight lets a large benefit buy
its way past a weak belief; a floor does not, and a ranked list is read as a list of things to
do where position outweighs any number printed beside it (ADR-0079, module 10's gated-component
ruling one layer up).

Named `belief` rather than `confidence` for the reason `core.ranking` names its own parameter
`chain_scalar`: LAW-EVIDENCE reserves the second word for the decomposed vector, and
`check_confidence_is_a_vector.py` refuses a float that borrows it.

### Withheld recommendation

A candidate that passed the actionability gate and was still not published. Of **equal
standing** to the ranked list and published with it: what was nearly recommended, and why it
was not, is frequently a sharper statement about a dataset than what was.

It carries what was measured — benefit, cost, risk, coverage, belief — so a reader deciding
whether a threshold is set correctly can see what it excluded. It carries **no** confidence
vector, evidence chain, assumptions or justification, so it cannot be rendered as a
recommendation or mistaken for one.
