# contracts.md — the frozen public interface of `causalog.core`

**Contract version: 1.10.0** · Frozen 2026-08-25 by ADR-0025 · Layer L0
> *1.1.0 (2026-08-28, ADR-0028): `IdentifierPrefix` gains `ONTOLOGY = "ont"`. Purely
> additive — no existing address recipe changes, so no identifier in any store moves and
> `engine_version` does not bump.*
>
> *1.2.0 (2026-08-30, ADR-0035, ADR-0038): `IdentifierPrefix` gains `MAPPING = "map"`, and
> `core/ports/source.py` gains `SourceDescription` plus a `describe()` method on the
> `SourceReader` protocol. Both purely additive: no existing address recipe changes, no
> frozen type gains or loses a field, and **`RunKey` is untouched** — the schema mapping
> participates in run identity through `dataset_version`, not through a sixth key field.
> `engine_version` does not bump.*
>
> *1.3.0 (2026-08-30, ADR-0039, ADR-0040, ADR-0041): **no change to any frozen type.** The
> version moves because this document's statement of how the frozen types are USED by
> modules 3 and 4 changed: `Event.provenance_class` is the class the ontology event type
> declares rather than always `OBSERVED` (ADR-0041, correcting `docs/architecture.md` §2),
> and `Event.evidence_record_ids` carries every record witnessing one occurrence rather than
> the single record an event was built from. No field was added, removed or retyped; no
> address recipe moved; no identifier in any store changes; `engine_version` does not bump.
> Section 5 carries the two clarifications.*

> *1.4.0 (2026-09-01, ADR-0046): `IdentifierPrefix` gains `RULE_PACK = "rul"`, and
> `core/ontology_view.py` gains `ParticipantView`, `EventTypeView`, `EntityTypeView`,
> `RelationshipTypeView` and `VocabularyView` — the shape `rule_engine` (L5) reads instead of
> the ontology, which forbidden edge F3 blocks it from importing. Purely additive: **no frozen
> type gains, loses, or retypes a field**, no address recipe moves, no identifier in any store
> changes, and `engine_version` does not bump. `core/ontology_view.py` is not itself a frozen
> type — it is the plain-view seam ADR-0042's `Timeline` note describes — but the
> `IdentifierPrefix` change is to a frozen enum and is recorded here for that reason.*

> *1.5.0 (2026-09-02, ADR-0048): `IdentifierPrefix` gains `EVIDENCE_ITEM = "evi"`, and
> `core/types/candidate_edge.py` adds `CandidateEdge` as a **`draft`** type. Purely additive:
> **no frozen type gains, loses, or retypes a field**, no existing address recipe moves, no
> identifier in any store changes, and `engine_version` does not bump. `CandidateEdge` is
> `draft` and is documented in §5 beside `CausalEdge` because the two are easily confused and
> the distinction is load-bearing. The `EVIDENCE_ITEM` prefix exists because `EvidenceItem`
> carried a free-form identifier while nothing needed to MINT one; module 9 mints thousands
> per run, and an unaddressed item is one a rerun cannot reproduce.*

> *1.6.0 (2026-09-03, ADR-0052): **no frozen type gains, loses, or retypes a field.**
> `ConfidenceComponent` and `ConfidenceVector` are untouched. The version moves because the
> admissible `component_name` set — which §5 states and which
> `confidence_schema_version` versions — goes from six names to eight, and because
> `core/aggregation.py` registers a third strategy, `gated_weighted_mean_v1`, in which two
> of the eight components act as **ceilings rather than addends**.
>
> `weighted_mean_v1`, `minimum_v1` and `DEFAULT_COMPONENT_WEIGHTS` are byte-identical, so
> every scalar already stored under them still recomputes to itself. That is the whole
> reason 2.0.0 arrives as a new function beside the old one rather than as a revision of it.
> No address recipe moves, no identifier in any store changes, and `engine_version` does not
> bump — the arithmetic that changed is selected by name from inside the artifact.
>
> `AGGREGATOR_COMPONENT_NAMES` is added so a consumer can ASK what an aggregator accepts;
> the registry stopped being uniform the moment a second schema version landed, and
> discovering the answer by being refused is not a contract.*

> *1.7.0 (2026-09-04, ADR-0056): **no frozen type gains, loses, or retypes a field.** Two
> purely additive changes, both outside the frozen set.
>
> `core/ontology_view.py` gains `MeasurementExpressionOperator` (the full nine-member closed
> operator set), `MeasurementKindView` (the full seven-member kind set),
> `MeasurementExpressionView` and `MagnitudeMeasurementView`. These sit **beside**
> `DurationExpressionOperator` and `DurationMeasurementView` rather than widening them, and
> that placement is the decision: widening the duration enum would let a duration measurement
> declare a `RATIO` that `state_engine`'s evaluator refuses, and the refusal would arrive at
> evaluation time instead of at load time. `core/ontology_view.py` is a `draft` plain-view
> seam, not a frozen type, so this is recorded here for traceability rather than because it
> touches a frozen contract.
>
> `core/measurement.py` is new: `evaluate_measurement`, the one walk of a declared operator
> tree in this repository. It is typed against a structural `MeasurementNode` protocol rather
> than a concrete view, so it evaluates both mirrors without a conversion step and without
> either learning about the other. The cost is stated rather than discovered: **nothing here
> can check at type level that the two operator enums stay in step**, and that is checked by
> a test instead. `graph_engine.state_engine.measurement.evaluate_duration_seconds` becomes a
> thin restriction of it — same supported operators, same refusal, same message — so no
> existing consumer moves.
>
> No address recipe moves, no identifier in any store changes, and `engine_version` does not
> bump: nothing that was computable before computes differently now.*
>
> *1.8.0 (2026-09-05, ADR-0057): `core/precedence.py` is new, holding
> `temporal_binding_source`, `DerivedPrecedence` and `DerivedPrecedenceIndex` — the carrier
> for module 1's measurement of which of a source's instants were COMPUTED from another
> rather than recorded, read by module 10's `temporal_support`. At L0 so that
> `causal_engine` never imports `ingestion`.
>
> **`DerivedPrecedenceIndex.precedence_for` compares `TimeInterval.source` locators by
> string equality and may never parse one.** That locator is an opaque provenance string;
> engine code that split or pattern-matched it would be reading the source description,
> which is domain arriving as a value. The lookup is also DIRECTED — a reversed pair does
> not match — because the measurement claims one direction only.
>
> Purely additive. No existing type changes shape, no address recipe moves, no identifier in
> any store changes, and `engine_version` does not bump.*

> This document is the module contract document `CONTEXT.md` OQ-009 required. It specifies
> every public type in `causalog.core`: its fields, its invariants, how it fails, and what
> it is forbidden from doing.
>
> **Frozen means a change requires an ADR and a coordinated update of every consumer**
> (`CONTEXT.md` §6). It does not mean the contract is right; it means changing it is a
> decision rather than an edit. Section 9 lists the five choices here most likely to be
> regretted, with what each would cost to undo.
>
> Where this document and `CONVENTIONS.md` disagree, `CONVENTIONS.md` governs *how* and this
> document governs *what the types are* — and the disagreement is itself a defect to be
> filed, not reconciled by preference.

> *1.9.0 (2026-09-06, ADR-0060, ADR-0061, ADR-0062, ADR-0063): **no frozen type gains, loses,
> or retypes a field.** Purely additive, in four places.
>
> `IdentifierPrefix` gains `PROPAGATION = "prp"`, `ROOT_CAUSE = "rca"` and `PATTERN = "pat"`,
> as `ONTOLOGY`, `MAPPING`, `TIMELINE`, `EVIDENCE_ITEM` and `RULE_PACK` were added before them.
> Each names an artifact a rerun must reproduce byte-identically. **No existing address recipe
> moves and no identifier in any store changes.**
>
> `core/ontology_view.py` gains `ActionabilityView` and `OrdinalClassView`, added BESIDE the
> magnitude views rather than by widening them — the same choice ADR-0056 made and for the same
> reason: widening a view lets a declaration reach a consumer that has no meaning for it, and
> the refusal then arrives at evaluation time instead of at load time.
>
> Three new L0 modules, none of them frozen and all of them registries whose names travel with
> the data: `core/composition.py` (`PATH_COMPOSERS` — how a chain's belief derives from its
> links, distinct from how one claim's components roll up), `core/attribution.py` (combining
> attributed magnitudes over a consequence SET without double counting), and `core/ranking.py`
> (`RANKERS` — ADR-0008's prevented-times-confidence criterion under a versioned name). All
> three sit at L0 for the reason `core/measurement.py` does: `check_metrics_are_declared.py`
> refuses this arithmetic inside a reasoning package, and a generic routine that never mentions
> a metric is the sanctioned alternative that lint exists to push code toward.
>
> `engine_version` does not bump. `rule_pack_schema_version` moves 1.4.0 → 1.5.0 separately
> (ADR-0063), and `run_id` moves with it — which is ADR-0013 working as designed and is why
> every committed report under `docs/reports/dataco/` was regenerated in this commit.*

> *1.10.0 (2026-09-07, ADR-0067, ADR-0068, ADR-0069): `IdentifierPrefix` gains
> `INTERVENTION = "itv"` and `CAUSAL_GRAPH = "cgr"`; `core/ontology_view.py` gains
> `AttributeView` and `MutabilityView`; and one new L0 module lands, `core/perturbation.py`.
> Purely additive: **no frozen type gains, loses, or retypes a field**, no existing address
> recipe moves, no identifier in any store changes, and `engine_version` does not bump.
>
> `CAUSAL_GRAPH` exists because `CONVENTIONS.md` §9 addresses a simulated world as
> `sim:digest(base_graph_id | mutations)` and nothing had ever needed the first half. A
> `run_id` will not serve as one: `PromotedGraph` and module 10's `CausalGraph` are both
> scoped to a run and **one run holds both**, so addressing on the run alone would give the
> graph the engine states and the graph it declined to state a single identifier.
>
> `core/perturbation.py` carries `SimulatedInstant` and the arithmetic a hypothetical performs
> on an instant and on a magnitude. It sits at L0 for the reason `core/attribution.py` does
> (ADR-0061): `check_metrics_are_declared.py` scans `counterfactual_engine/` and refuses this
> arithmetic there, correctly.
>
> **`SimulatedInstant` is deliberately not a `TimeInterval`, and the frozen type was NOT
> widened to make it one.** `TIMESTAMP_PROVENANCE_CLASSES` excludes `SIMULATED` (§3), and the
> one-line change that would admit it — adding the member to that frozenset — would make every
> consumer of `TimeInterval` a consumer of simulated times without any of them being told.
> prd.md §37 requires that observed facts and counterfactual simulations never be conflated
> "in the implementation or the user interface"; one type carrying both is that conflation at
> the level where it is hardest to see and easiest to spread. The cost is two parallel shapes
> for one concept, paid deliberately and recorded in ADR-0068.
>
> `AttributeView` / `MutabilityView` land beside the magnitude views (1.5.0) and the
> actionability views, on the same terms: `EventTypeView.required_attributes` stays a bare
> `tuple[str, ...]` and is not widened. `ontology_hash` moves separately (pack schema
> 1.0.0 → 1.1.0, ADR-0067) and `rule_pack_schema_version` moves 1.5.0 → 1.6.0 separately
> (ADR-0071); `run_id` moves with BOTH, which is why every committed report under
> `docs/reports/dataco/` was regenerated in this commit.*

---

## 1. What this package is, and what it may not do

`causalog.core` declares the canonical types every layer computes over. LAW-EVENT: the
reasoning core computes over `Event`, `Entity`, `State`, `Transition`, `Relationship` —
never over rows, DataFrames, or CSV columns.

**Forbidden, structurally:**

| | Enforced by |
|---|---|
| Importing any other project package (F1) | `scripts/check_layers.py` |
| Importing any third party except `pydantic` (F8) | `scripts/check_layers.py` |
| Any I/O — no file handle, no socket, no clock, no database | code review; `Clock` is a port precisely so time is injected |
| Any domain vocabulary, including in comments and docstrings (LAW-DOMAIN) | `scripts/check_domain_independence.py` |
| A confidence carried as a bare float (LAW-EVIDENCE) | `scripts/check_confidence_is_a_vector.py` |

The package is importable with no services running. That is a hard property: every module
in the system depends on it, and a `core` that needed a database would make the entire
dependency graph require one.

**Module map**

| Module | Holds |
|---|---|
| `core/errors.py` | the closed error taxonomy |
| `core/identifiers.py` | content addressing and canonical encoding |
| `core/provenance.py` | the provenance classes and their algebra |
| `core/temporal.py` | interval timestamps and the LAW-TIME verdict |
| `core/aggregation.py` | the confidence aggregator registry, its weight tables, and the gate ceilings |
| `core/serialization.py` | the canonical wire format |
| `core/immutability.py` | the observed-fact guard |
| `core/derivation.py` | derived views that are functions, not fields |
| `core/measurement.py` | the one walk of an ontology-declared operator tree (ADR-0056) |
| `core/ontology_view.py` | the plain views of ontology configuration that L4–L10 read (F3) |
| `core/run.py` | the reproducibility unit and the output envelope |
| `core/types/` | the canonical types |
| `core/ports/` | the Protocols infrastructure implements (ADR-0014) |

---

## 2. The hashing scheme, and why 64 bits

Every identifier is `<type_prefix>:<sha256(canonical_payload)[:16]>` (`CONVENTIONS.md` §9).

**Why SHA-256.** It is in the standard library, stable across interpreter versions and
platforms, and unseeded. Python's built-in `hash()` has none of those properties — it is
randomized per process unless `PYTHONHASHSEED` is pinned — and a digest that varies by
process makes every rerun a false determinism failure.

**Why truncated to 16 hex characters.** That is 64 bits. By the birthday bound a 64-bit
space reaches roughly a one-in-a-million collision probability near six million distinct
payloads, and an even chance near five billion. The reference dataset is six orders of
magnitude below the second figure. The truncation buys identifiers short enough to read in a
log line, paste into a URL, and scan in a Cypher result.

**A collision is a defect, not an event to handle.** A collision on *differing* payloads is
`CRITICAL`, checked at insert by the persistence port, and never retried (`CONVENTIONS.md`
§9). There is no fallback identifier and no disambiguating suffix: either would make the
address depend on insertion sequence, which destroys reproducibility to avoid an event that
should not occur.

**Reserved characters and why leaves are escaped.** Three characters structure a payload:
`|` between top-level fields, `,` between collection members, `=` inside a pair. A leaf
value may legitimately contain any of them, so leaves are escaped (`\\` → `\\\\`, `|` → `\p`,
`,` → `\c`, `=` → `\e`) rather than rejected. Escaping is injective; rejecting would make
some admissible source values unrepresentable, and stripping would let `("a|b")` and
`("a", "b")` produce one identifier. That last failure is silent, permanent, and merges two
artifacts into one.

**Payload recipes** (`CONVENTIONS.md` §9), each exposed as an `address` classmethod on its
type:

| Prefix | Type | Payload |
|---|---|---|
| `evt` | `Event` | `ontology_hash \| event_type \| entity_ids(sorted) \| interval \| changed_attributes(sorted) \| evidence_record_ids(sorted)` |
| `ent` | `Entity` | `ontology_hash \| entity_type \| natural_key` |
| `sta` | `State` | `entity_id \| state_name \| interval` |
| `trn` | `Transition` | `from_state_id \| to_state_id \| causing_event_id` |
| `edg` | `CausalEdge` | `source_event_id \| target_event_id \| edge_kind` |
| `evd` | `EvidenceRecord` | `dataset_version \| source_locator` |
| `run` | `RunKey` | `dataset_version \| ontology_hash \| rule_pack_version \| engine_version \| seed` |
| `ont` | *(resolved domain pack — `ontology_runtime`)* | `to_canonical_json(resolved_pack)` — the canonical JSON of the whole resolved pack, not a field list (ADR-0028) |
| `map` | *(schema mapping — `ingestion.schema_mapper`)* | `to_canonical_json(mapping)` — the same shape as `ont` and for the same reason: a mapping is a document, not a field list (ADR-0035) |
| `sim` | *(simulated world — module 13)* | `base_graph_id \| mutations(canonically serialized)` |

**`dataset_version` is not an address and does not appear above.** It is a legible
composite, `<dataset_id>@<content_sha256[:16]>+map<mapping_digest[:16]>` (ADR-0035), and it
is deliberately readable rather than digested: the mapping reaches `run_id` through it
because `RunKey` is frozen, so both halves have to stay recoverable by eye. Its full
decomposition lives in `datasets/<dataset_id>.pin.json`.

An interval encodes as `t_earliest,t_latest,precision`. Provenance and `source` are excluded:
they record how the bounds were obtained, not which moment is described. The bounds
themselves participate, so narrowing an interval mints a new identifier — content addressing
working correctly, since a different claim about when something happened is a different
claim.

**What is deliberately absent from an address.** `Entity.lifecycle` and `Entity.attributes`
(identity is what a thing *is*, not what has been recorded about it, so enriching attributes
must not rename it); `Event.trigger` (an `OBSERVED` mechanism label, ADR-0020 — two otherwise
identical events are the same event whether or not the source named the mechanism); and
`Run.created_at` (two runs over identical inputs are the same run, whatever hour they
started).

---

## 3. Timestamp comparison semantics under uncertainty

**This section governs LAW-TIME enforcement. Read it before changing anything in
`core/temporal.py`.**

An interval timestamp is a **partial** precedence relation. Two intervals may be genuinely
incomparable, and the entire point of ADR-0007 (as extended by ADR-0021) is that the engine
says so rather than guessing.

```
strictly_before(cause, effect)   is   cause.t_latest < effect.t_earliest
```

That is the whole definition. It is the most conservative reading available: precedence
holds only when the latest moment the cause could have happened is still before the earliest
moment the effect could have happened, so no assignment of true instants within the two
intervals could reverse it.

### Overlap is never "before"

If two intervals share even one instant, the data cannot separate them and the answer is
`UNDETERMINED` — not `CERTAIN`, not `VIOLATION`, and never a tie broken by a midpoint, a
start bound, or a sort position. Each of those manufactures precedence the source never
recorded, which is the exact failure LAW-TIME exists to prevent.

`TimeInterval.sort_key()` exists for a stable display sequence and is **not** a precedence
claim. Two intervals may sort adjacently and be temporally incomparable.

### The verdict table

Applied in this sequence:

| Condition | Verdict |
|---|---|
| either interval has `UNKNOWN` precision | `UNDETERMINED` (and the edge is flagged `temporally_unverifiable`) |
| `cause.t_earliest >= effect.t_latest` | `VIOLATION` — the edge is rejected and never created |
| `cause.t_latest < effect.t_earliest`, and neither interval is `INFERRED` | `CERTAIN` — may be promoted to `INFERRED` |
| anything else (the intervals overlap) | `UNDETERMINED` — retained, blocked from promotion |

The verdict is **total** over the interval space — every pair yields exactly one answer —
while the precedence relation underneath is **partial**. `UNDETERMINED` is the name for the
pairs where precedence has no answer.

**Why the `UNKNOWN` guard precedes the `VIOLATION` test.** An absent bound supports no
assertion at all, including the negative one. With no information you cannot claim a
violation any more than you can claim precedence. An implementation that compared the
sentinel bounds directly would report violations for pairs the source simply never placed.

**Why an `INFERRED` interval never yields `CERTAIN`.** Its bounds were derived rather than
observed (ADR-0021). Promoting an edge to `INFERRED` on the strength of them would let one
inference certify another with no observation anywhere underneath the chain.

### Two kinds of "we cannot tell"

| | Meaning | Field |
|---|---|---|
| `UNDETERMINED` | The data placed both events and could not separate them. | `CausalEdge.temporal_verdict` |
| `temporally_unverifiable` | The data never placed one of them. | `CausalEdge.temporally_unverifiable` |

Both block promotion to `INFERRED`. They are kept apart because they are different findings
about the dataset, and collapsing them would hide which one a run actually hit — which is
exactly what risk R-14 needs to be able to report. **A consumer that reads only the verdict
conflates them**; this is the fourth regret in section 9.

---

## 4. The provenance algebra

`ProvenanceClass` is closed and disjoint: `OBSERVED | ASSUMED | STATISTICAL | INFERRED |
SIMULATED` (LAW-PROVENANCE, ADR-0005). It answers *how a thing came to be known*, and is
orthogonal to *how sure we are* — a low-confidence `OBSERVED` fact and a high-confidence
`INFERRED` edge differ in kind, not in degree.

Strength, weakest first: `SIMULATED` < `ASSUMED` < `STATISTICAL` < `INFERRED` < `OBSERVED`.
`WEAKEST_FIRST` is the single source of that ranking; `PROVENANCE_STRENGTH` is derived
from it.

```
combine(*classes) -> the weakest class present
```

**The result is never stronger than the weakest input.** An assertion built on an `ASSUMED`
input is `ASSUMED`, however strong its other inputs. There is no promotion path in this
function and deliberately no argument that supplies one: promotion is a separate, explicit,
evidence-bearing operation performed by a named module, never a side effect of combining.

`combine()` with no arguments raises `ContractViolationError`. Returning `OBSERVED` for an
empty combination would mint the strongest class in the system out of nothing.

### The full combination table

| | SIMULATED | ASSUMED | STATISTICAL | INFERRED | OBSERVED |
|---|---|---|---|---|---|
| **SIMULATED** | SIMULATED | SIMULATED | SIMULATED | SIMULATED | SIMULATED |
| **ASSUMED** | SIMULATED | ASSUMED | ASSUMED | ASSUMED | ASSUMED |
| **STATISTICAL** | SIMULATED | ASSUMED | STATISTICAL | STATISTICAL | STATISTICAL |
| **INFERRED** | SIMULATED | ASSUMED | STATISTICAL | INFERRED | INFERRED |
| **OBSERVED** | SIMULATED | ASSUMED | STATISTICAL | INFERRED | OBSERVED |

Commutative, associative, and idempotent — all asserted as properties in
`tests/unit/core/test_provenance_algebra.py`, because a pipeline folds these in an arbitrary
shape and the answer must not depend on the fold.

---

## 5. The canonical types

Every type below is `frozen=True, extra="forbid"`. Attribute assignment raises; an
undeclared field raises.

### `TimeInterval` — `core/temporal.py`

| Field | Type |
|---|---|
| `t_earliest`, `t_latest` | `datetime` (timezone-aware, UTC, inclusive) |
| `precision` | `EXACT \| SECOND \| MINUTE \| HOUR \| DAY \| UNKNOWN` |
| `provenance` | `OBSERVED \| ASSUMED \| INFERRED` |
| `source` | `str`, non-empty |

**Invariants** (all enforced in the validator): both bounds tz-aware and UTC — a naive
datetime is a defect, refused rather than assumed; `t_earliest <= t_latest`; `EXACT` implies
equal bounds; `UNKNOWN` implies `ASSUMED` provenance and the unbounded sentinels
`UNKNOWN_EARLIEST`/`UNKNOWN_LATEST`; provenance is one of `TIMESTAMP_PROVENANCE_CLASSES`
(`STATISTICAL` and `SIMULATED` are imputation under another name); `INFERRED` implies
precision is not `EXACT`.

**Derived:** `kind -> TimestampKind`, `sort_key() -> (t_earliest, t_latest)`.

**Forbidden:** imputation of any kind. Not `now()`, not epoch, not the previous event's
time, not the median (`CONVENTIONS.md` §10).

### `Event` — `core/types/event.py`

`event_id`, `event_type`, `occurred_at: TimeInterval`, `trigger: str | None`,
`source_entity_ids`, `target_entity_ids`, `changed_attributes`, `metadata`,
`provenance_class`, `confidence: ConfidenceVector`, `is_actionable: bool`,
`source_record_ref`, `evidence_record_ids`.

**Invariants:** immutable — a correction emits a new event (ADR-0004);
`source_record_ref` appears in `evidence_record_ids`; an `OBSERVED` event has at least one
evidence record; an `UNKNOWN`-precision event may sit on a timeline but may never
participate in an `INFERRED` causal edge.

**`provenance_class` is the class the event's ontology type declares (ADR-0041).** It is not
always `OBSERVED`, and on a source that logs one occurrence and implies the rest it is
overwhelmingly not: ADR-0029 declares one `OBSERVED` event type in the DataCo pack and
nineteen `DERIVED` ones that may never claim `OBSERVED`. No heuristic may produce an
`OBSERVED` event, and the emission rules that decide which records witness an occurrence
(ADR-0039) name no provenance class at all, so there is nothing there to get wrong.

**`evidence_record_ids` names every record witnessing ONE occurrence, not one record.** Two
records agreeing on type, participants, interval and recorded attributes are corroborating
witnesses of one thing that happened; they become one event citing both, and
`source_record_ref` names the first in canonical sequence. The set participates in the
content address, which is why an event's identity is not knowable until every record has
been read.

**Forbidden:** **no module may read `Event.trigger` to create, filter, or score a causal
edge** (ADR-0020). Doing so turns an `OBSERVED` field into a causal claim that skipped both
the LAW-TIME and LAW-EVIDENCE gates. `confidence` is a vector, never a float — LAW-EVIDENCE
exempts no type (ADR-0009).

### `Entity`, `Lifecycle` — `core/types/entity.py`

`Entity`: `entity_id`, `entity_type`, `natural_key`, `attributes`, `lifecycle`,
`provenance_class`, `evidence_record_ids`.
`Lifecycle`: `state_names` (sorted, non-empty, unique), `legal_transitions` (sorted, every
endpoint declared), `provenance_class` (always `ASSUMED`).

**There is deliberately no `current_state` field.** The condition an entity is in is a
function of the entity *and an instant*, computed by `core.derivation.current_state`.
Storing it would force one of two defects: the entity mutates as history advances,
contradicting LAW-PROVENANCE, or its content address changes every time the world moves,
making every reference to it stale.

### `State`, `Transition` — `core/types/state.py`, `transition.py`

`State`: `state_id`, `entity_id`, `state_name`, `held_over: TimeInterval`,
`derived_from_event_id`, `provenance_class`, `evidence_record_ids`.

`held_over` **is** the validity interval — `t_earliest` is `valid_from`, `t_latest` is
`valid_to`. There are not also two bare instant fields: one interval carrying its own
precision and provenance says everything two instants would and cannot disagree with itself.
A state still holding at the end of the dataset has `t_latest` at `UNKNOWN_LATEST`, the
honest statement that no end was recorded.

`Transition`: `transition_id`, `from_state_id`, `to_state_id`, `causing_event_id`,
`provenance_class`. "Causing" here is the *observed* attribution recorded at
state-derivation time; it is not an inferred causal edge and never carries `INFERRED`.

### `Timeline`, `TimelineEntry` — `core/types/timeline.py` (draft, ADR-0042)

`Timeline`: `timeline_id`, `view: TimelineView` (`PROCESS_INSTANCE` | `ENTITY` | `JOINED`),
`process_definition_id: str | None`, `subject_entity_ids: tuple[str, ...]` (sorted),
`entries: tuple[TimelineEntry, ...]`, `provenance_class`.

`TimelineEntry`: `kind: TimelineEntryKind` (`EVENT` | `GAP`), and one of two mutually
exclusive field groups selected by `kind` — `event_id`/`occurred_at`/`sequence_provenance`
for `EVENT`, or `expected_event_type`/`process_definition_id`/`step_witnessable` for `GAP`.
`entries` is checked, not decided, at construction: `EVENT` entries must already be
strictly increasing by `(occurred_at.t_earliest, occurred_at.t_latest, event_id)`
(`CONVENTIONS.md` §11); `GAP` entries carry no ordering claim of their own.

`sequence_provenance` records the adjacency tie-break (ADR-0043): `OBSERVED` when
`core.temporal.verdict` returned `CERTAIN` for the pair, `ASSUMED` when the verdict was
`UNDETERMINED` and the position was settled by sorting on `event_id` instead — a rendering
choice, not a claim about which event truly happened first.

`Timeline.address()` payload: `ontology_hash | view | process_definition_id |
subject_entity_ids(sorted) | event_ids(sorted)`. `GAP` entries are excluded — they are
derived from the process definition and the placed events, not an independent fact.

### `Relationship` — `core/types/relationship.py`

Structural, non-causal edges between entities. **`CAUSES` may never be a
`relationship_type`** — causal edges are a separate artifact produced only by the causal
engine.

### `EvidenceRecord`, `EvidenceItem` — `core/types/evidence.py`

Two distinct things that must not be conflated:

- **`EvidenceRecord` is a citation** — an opaque, dataset-version-scoped pointer at one
  source record. It answers *where did this come from*. The raw record is never carried
  here and never appears in a log or error message.
- **`EvidenceItem` is a justification** — one named reason an assertion is believed,
  carrying `kind`, `description`, `supporting_ids` (sorted, non-empty), `strength`,
  `provenance_class`, and `verification`.

`EvidenceKind` is closed (prd.md §27), and the members are listed here so a consumer never
has to leave this document to construct one: `RULE`, `TEMPORAL_PROXIMITY`, `SHARED_ENTITY`,
`SHARED_IDENTIFIER`, `HISTORICAL_FREQUENCY`, `ONTOLOGY`, `STATISTICAL_ASSOCIATION`. A
justification fitting none of them is unmodelled, not weak, and needs an ADR.

`strength` is a bare float in `[0,1]` and is **not** a confidence: it is one item's own
weight. Confidence is a `ConfidenceVector` assembled from many items. This is the single
admissible bare float in the vicinity of a judgement, and it is named `strength` precisely
so it is not mistaken for one.

`verification` is the load-bearing field: the exact rule identifier or query text that
produced the item. **An item a reader cannot re-execute is a defect, not a weak item.** An
explanation assembled from unverifiable items cannot be audited by anyone who was not
present when it ran.

### `ConfidenceComponent`, `ConfidenceVector` — `core/types/confidence.py`

`ConfidenceComponent`: `component_name`, `value` in `[0,1]`, `provenance_class`,
`evidence_record_ids`. A component expressing a count is normalized *before* becoming a
component, so no aggregator has to know which components are counts.

**The admissible `component_name` values are closed under each weighted aggregator**, and are
listed here because a consumer that invents a name gets a `ContractViolationError` at runtime
rather than a type error at the boundary. `AGGREGATOR_COMPONENT_NAMES` declares which names
each registered aggregator accepts, because the registry is no longer uniform.

At `confidence_schema_version` **1.0.0**, `weighted_mean_v1` renormalizes these six over
those supplied: `rule_support` (0.25), `temporal_support` (0.20), `historical_support`
(0.15), `statistical_support` (0.15), `evidence_count` (0.15), `graph_connectivity` (0.10).
**Unchanged and still registered** — a vector naming it still recomputes to the same scalar.

At **2.0.0** (ADR-0052), `gated_weighted_mean_v1` takes **eight** names and requires all of
them. Six are addends, renormalized over the declared table: `rule_support` (0.28),
`historical_support` (0.17), `statistical_support` (0.17), `evidence_diversity` (0.16),
`evidence_count` (0.12), `graph_connectivity` (0.10). Two are **gates**, entering by `min`
rather than by sum: `temporal_support` and `contradiction_freedom` each map through a
piecewise-linear, non-decreasing ceiling and cap the scalar.

```
scalar = min(weighted_mean(the six addends),
             ceiling(temporal_support), ceiling(contradiction_freedom))
```

Monotone in all eight, and the ceilings are quantized so the cap holds at the resolution the
scalar is stored at. Unlike `weighted_mean_v1`, an absent component does **not** abstain
here: module 10 never omits one, so an absent name means the vector was assembled elsewhere
and is refused. `minimum_v1` is name-agnostic and accepts any name.

The name set is part of `confidence_schema_version`; adding a name means shipping a new
aggregator version beside the old one, never revising it in place.

`ConfidenceVector`: `components` (non-empty, sorted by name, no repeats), `scalar` in
`[0,1]`, `aggregation`, `provenance_class`.

**`scalar` is derived and non-authoritative.** It may be displayed; it may never be the sole
persisted representation, and no module may reconstruct a judgement from it alone.
`aggregation` names the function that produced it so it can be recomputed and disagreed
with — a scalar whose function is unnamed is exactly the unexplained number prd.md §49
forbids. `provenance_class` is the weakest component class, computed by `combine`, never by
the aggregator's arithmetic.

### `CausalEdge` and the taxonomy — `core/types/causal_edge.py`

`causal_edge_id`, `source_event_id`, `target_event_id`, `payload`, `confidence`, `evidence`,
`propagation_weight`, `provenance_class`, `temporal_verdict`, `temporally_unverifiable`,
`run_id`.

**Derived properties:** `edge_kind` (read from the payload), `rule_support` and
`statistical_support` (read from the named confidence components). prd.md §25 lists the
latter two as edge fields and prd.md §49 as confidence components; storing both would be one
number in two places, free to diverge.

The five kinds are payload **types**, not string labels (ADR-0022):

| Kind | Payload | Constraint |
|---|---|---|
| `DirectCause` | *(no fields)* | The absence of extra data is the claim. |
| `ConditionalCause` | `condition_expression`, `condition_holds` | Expression non-empty, exactly as evaluated. |
| `ContributingCause` | `joint_cause_group_id`, `co_cause_event_ids` | Both non-empty; co-causes sorted. Conjunctive, never ranked. |
| `AmplifyingCause` | `magnitude_multiplier` | `> 1.0` |
| `InhibitingCause` | `magnitude_multiplier` | `0.0 <= m < 1.0` |

**Construct with `CausalEdge.between`.** It is the sanctioned constructor and the only one
that can evaluate LAW-TIME, which is why it takes the two `Event` objects rather than their
identifiers — an edge built from ids alone could not check the law, and a check that cannot
run is indistinguishable from one that passes.

```
CausalEdge.between(
    *, source_event: Event, target_event: Event, payload: CausalEdgePayload,
    confidence: ConfidenceVector, evidence: tuple[EvidenceItem, ...],
    propagation_weight: float, provenance_class: ProvenanceClass, run_id: str,
) -> CausalEdge
```

`temporal_verdict` and `temporally_unverifiable` are **computed and stamped on**, never
passed in. There is no `skip` or `force` argument: a caller able to pass
`temporal_verdict=CERTAIN` could launder a rejected edge into the graph. A `VIOLATION`
raises `LawViolationError`. Absent time is the only accommodation, and it is a recorded
state (`temporally_unverifiable`), not a silent pass. `causal_edge_id` is derived via
`CausalEdge.address(source_event_id, target_event_id, edge_kind)` — the class does **not**
re-derive or check a supplied id, unlike `Run`. See §6 for what deserialization can and
cannot re-check (DEF-0002).

**Invariants:** `temporal_verdict` is never `VIOLATION`; `INFERRED` provenance requires
`CERTAIN` and not `temporally_unverifiable`; `provenance_class` is never `OBSERVED`
(causation is never read from a source record); `evidence` is non-empty;
`source_event_id != target_event_id`; `propagation_weight` in `[0,1]`; `run_id` present.
Every one of these raises `LawViolationError` except the self-edge, the weight bound, and
the empty `run_id`, which raise `ContractViolationError`.

### `CandidateEdge` — `core/types/candidate_edge.py` (draft, ADR-0048)

`candidate_edge_id`, `generator_id`, `source_event_id`, `target_event_id`, `payload`,
`evidence`, `provenance_class`, `temporal_verdict`, `temporally_unverifiable`, `run_id`.

**Derived properties:** `edge_kind` (read from the payload), `admits_promotion` (reads the
two temporal fields and nothing else — it says only that time does not block promotion, never
that the candidate has merit), `sort_key`.

**What is deliberately ABSENT is the contract.** There is no `confidence` field and no
`propagation_weight`. Module 9 is forbidden from assigning confidence, and the enforcement is
that the artifact has nowhere to put one — a generator cannot score, rather than being asked
not to. Module 10 constructs `CausalEdge` from these, and `CausalEdge` is where a
`ConfidenceVector` first appears.

**Not `CausalEdge`, and the difference matters at every use.** A candidate is one generator's
proposal, carrying its own evidence; a causal edge is the single scored claim module 10
assembles from every proposal over that pair. Several candidates collapse into one edge, so
the two do not share an identifier and tracing one to the other is a join on
`(source, target, kind)`.

**The payload union IS shared**, imported unchanged from the frozen `causal_edge` module. One
taxonomy for prd.md §26's five categories, not a second and weaker one.

**Address:** `CandidateEdge.address(source_event_id, target_event_id, payload, generator_id)`
over `source | target | edge_type | generator_id | payload`. Two departures from
`CausalEdge.address`, both deliberate:

* **`generator_id` participates** because the candidate graph is a multigraph — two
  generators reaching one pair by different reasoning are two proposals with two evidence
  trails, and merging them would destroy the fact that two unrelated lines of reasoning
  arrived at the same place, which is exactly what module 10 needs to see.
* **The whole payload participates, not just its kind.** One generator legitimately reaches
  one pair twice with two different claims — two `CONDITIONAL` claims under different
  conditions, two `CONTRIBUTING` claims in different joint groups. Under a kind-only recipe
  those collide (DEF-0006). Two proposals with an identical payload are genuinely one
  hypothesis with two justifications and are merged into one candidate carrying both.

**Construct with `CandidateEdge.between`**, which mirrors `CausalEdge.between` exactly: it
takes the two `Event` objects because it is the only place both intervals are visible,
computes and stamps `temporal_verdict` and `temporally_unverifiable`, and offers no `skip` or
`force` argument. A `VIOLATION` raises `LawViolationError`.

**The DEF-0002 boundary applies here identically and is restated rather than inherited.** The
artifact stores identifiers, not intervals, so nothing inside it can recompute `verdict(...)`.
An `UNDETERMINED` verdict rewritten to `CERTAIN` on the wire is accepted. Closing that means
putting the intervals into the artifact — an ADR, not an edit.

**Invariants:** `temporal_verdict` is never `VIOLATION`; `provenance_class` is never
`OBSERVED`; `INFERRED` requires `CERTAIN` and not `temporally_unverifiable`; `evidence` is
non-empty; `source_event_id != target_event_id`; `generator_id` non-empty; `run_id` present.
In practice module 9 never emits `INFERRED` at all — promotion is a judgement and judgement is
module 10's — but the invariant is enforced on the type so a deserialized edge cannot claim it.

### `RunKey`, `Run`, `OutputEnvelope` — `core/run.py`

`RunKey` is the five-tuple that determines a `run_id`. `Run` adds the identifier and
`created_at`, which is **passed in** from the `Clock` port — `datetime.now()` inside a
reasoning module is a determinism defect — and is excluded from the `run_id` payload.
`Run` re-derives its own identifier on construction, so a `run_id` that disagrees with its
key is refused.

Every inferred artifact is scoped to a `run_id`; observed facts are dataset-scoped. That
asymmetry is what makes "inference never overwrites observation" structural rather than
procedural (ADR-0013).

`OutputEnvelope` accompanies every persisted artifact and API response. An output without
its envelope cannot be verified and is a defect (`CONVENTIONS.md` §11).

---

## 6. Behaviour contracts

### `core/aggregation.py`

`Aggregator` is a pure function from components to a scalar in `[0,1]`, registered by name.
`AGGREGATORS` is frozen — an aggregator added at runtime would not survive into the
artifact's `aggregation` field on another machine, and the rollup would stop being
reproducible.

- `weighted_mean_v1` *(default)* — renormalizes `DEFAULT_COMPONENT_WEIGHTS` over the
  components present, so **an absent component abstains** rather than scoring zero.
  Treating absence as zero would punish an edge for evidence the pipeline never sought.
  Raises on an unweighted component name: the names are part of
  `confidence_schema_version`, and guessing a weight would let a schema change pass
  silently and shift every score.
- `minimum_v1` — the conservative rollup; name-agnostic; ranks poorly by design.

The weights are a **stated editorial judgement, not a measurement.** This dataset has no
causal ground truth to fit them against, so no procedure could have derived them. They sit
in one table so that disagreement is possible.

`aggregate()` never silently substitutes the default for an unknown name: that would produce
a vector whose `aggregation` field misdescribes its own scalar.

### `core/serialization.py`

`to_canonical_json` emits `{payload, schema_version, type}` with keys sorted at every depth,
fixed separators, ISO-8601 UTC instants, and floats **as quantized strings**. Strings
because a JSON number is re-formatted by whichever parser reads it next, and byte-identity
would not survive a round trip through another language's encoder.

`from_canonical_json` re-runs every invariant. A missing envelope, a version mismatch, or a
mismatched type is a `ContractViolationError` — none is repaired.

**Re-running an invariant is not the same as re-deriving the value it guards (DEF-0002).**
For `CausalEdge` the difference is load-bearing. A stored `VIOLATION` verdict and a stored
`OBSERVED` provenance are banned *values* of a stored field, so the validator sees them and
refuses. The verdict itself cannot be re-derived here, because the artifact carries
`source_event_id` and `target_event_id` — identifiers, not intervals. An `UNDETERMINED`
verdict rewritten to `CERTAIN`, or a cleared `temporally_unverifiable`, reads back clean and
may then carry `INFERRED`. The same hole is reachable with no serialization at all: a direct
`CausalEdge(...)` call accepts `temporal_verdict` as an argument, and pydantic cannot
distinguish it from the `model_validate` deserialization needs. `CausalEdge.between` is the
**sanctioned** constructor, not an enforceable one. The boundary is pinned by
`tests/law/test_law_time_survives_the_wire.py`; closing it requires the intervals or a
verdict-bearing address inside the artifact, which is §8's path, not an edit.

**Round-trip precondition:** quantization to six places is lossy, so
`from_canonical_json(to_canonical_json(x)) == x` holds exactly when `x` already carries
quantized floats. That is the intended state of every artifact; an artifact holding an
unquantized float has already lost byte-identity before reaching this function.

`CANONICAL_SCHEMA_VERSION` versions the wire shape. The per-artifact schema versions in
`CONTEXT.md` §7 move independently.

### `core/immutability.py`

`revise(artifact, **updates)` returns a re-validated new version, and **raises
`LawViolationError` when the artifact is `OBSERVED`.** Including when the update is
`provenance_class` itself — relabelling an observation as inferred and then editing it
freely is the obvious way around the guard, and the first step already fails.

The caller supplies a recomputed identifier when a revision touches an addressed field. This
function does not recompute it: the recipe differs per type, and a helper that guessed would
mint an identifier disagreeing with the recipe.

### `core/derivation.py`

`current_state(states, entity_id, as_of)` returns the single state holding at an instant, or
`None`. **Raises `ContractViolationError` if more than one holds** — two simultaneous states
are a contradiction in the source, and returning either would resolve it by arbitrary
choice. `states_holding_at` exposes the overlap when overlap is the thing being examined.

### `core/errors.py`

Closed taxonomy rooted at `CausaLogError`: `LawViolationError`, `ContractViolationError`,
`OntologyMappingError`, `DataQualityError`, `RuleConflictError`, `ProjectionStaleError`.
Never raise a bare `Exception` or `ValueError` across a module boundary.

**A breach of a named Law raises `LawViolationError` on every path, including
deserialization** — pydantic propagates a non-`ValueError` from a validator unwrapped, which
is what lets a validator report a law breach as a law breach rather than as a generic
validation failure. Ordinary contract breaches raise `ContractViolationError`.

---

## 7. How this contract is defended

| Property | Test |
|---|---|
| Identifier determinism, including across a fresh interpreter | `tests/unit/core/test_identifier_determinism.py` |
| Timestamp comparison under uncertainty | `tests/unit/core/test_temporal_comparison.py` |
| Provenance algebra never increases certainty | `tests/unit/core/test_provenance_algebra.py` |
| Aggregation bounds, monotonicity, gate ceilings, and the weakest-provenance rule | `tests/unit/core/test_confidence_aggregation.py` |
| Every scored edge carries all eight components, each traced to evidence | `tests/law/test_law_evidence_gates_every_edge.py` |
| A missing component is emitted at zero, flagged, and counted — never omitted | `tests/unit/causal_engine/confidence_scorer/test_score.py` |
| Base rates: a pattern present everywhere has lift 1.0 and scores zero | `tests/unit/causal_engine/confidence_scorer/test_base_rates.py` |
| Serialization round-trip and byte stability | `tests/unit/core/test_serialization_round_trip.py` |
| LAW-TIME enforced at construction *and* deserialization | `tests/law/test_law_time_is_enforced_at_construction.py` |
| The measured limit of that enforcement on the wire (DEF-0002) | `tests/law/test_law_time_survives_the_wire.py` |
| Observed facts immutable | `tests/law/test_observed_facts_are_immutable.py` |
| Confidence is never a bare float, and the lint does not fire on `strength` | `tests/law/test_law_confidence_lint.py` |

The first five are property-based (`hypothesis`, ADR-0024) under a `derandomize=True`
profile, so a given commit explores the same inputs everywhere and a failure reproduces from
the test name alone. The cost, stated plainly: a derandomized suite is a regression net, not
a search — it stops finding *new* counterexamples on reruns.

**No test here asserts that a causal conclusion is correct.** This dataset has no causal
ground truth (`CONVENTIONS.md` §14). Every property is structural.

---

## 8. Changing a frozen contract

1. Write the ADR first (`CONTEXT.md` §0). It names every consumer and the migration.
2. Bump this document's version, and the relevant `CONTEXT.md` §7 schema version.
3. Update the type, its tests, and `GLOSSARY.md` in the same commit.
4. If the change touches an address recipe, it is an `engine_version` bump and a full
   re-derivation — every identifier in every store changes.

---

## 9. The five decisions most likely to be regretted

Stated now, while they are cheap to reverse, rather than discovered later.

### 1. Identifiers are 64 bits — **migration cost: high**

Sixteen hex characters is a readability choice, and readability is not usually worth a
collision. The bound is comfortable for one dataset version and is not comfortable for
"every dataset anyone ever loads into this engine", which is what a domain-agnostic system
implicitly promises. Widening `DIGEST_LENGTH` changes **every identifier in every store**:
an `engine_version` bump, a full re-derivation, and no in-place migration path, because the
identifier *is* the content. The mitigating fact is that the collision check at insert makes
the failure loud rather than silent.

### 2. `INFERRED` timestamp provenance — **migration cost: medium-high**

ADR-0021 reopens a door ADR-0007 deliberately shut. The guards — never `EXACT`, never
`CERTAIN` — bound the damage, but they are a validator and a docstring, not a proof. Nothing
structurally prevents a module from labelling a guessed window `INFERRED` with a plausible
`source` string, and **no test can detect it**, because there is no ground truth to check the
bound against. `source` being free text will also drift toward uninformative values unless
review holds the line. Reversing means reclassifying every `INFERRED` interval and
re-deriving every verdict that depended on those bounds.

### 3. The five-payload edge union — **migration cost: low to add, high to alter**

Adding a sixth kind is additive and cheap. Changing an existing payload's shape is not: it
breaks the `edg` address, forcing a re-derivation of every edge identifier. The five payloads
are effectively frozen from now on. The specific hostage to fortune is the
`AMPLIFYING`/`INHIBITING` split at exactly 1.0, which makes a multiplier of 1.0
unrepresentable — deliberate, and it will at some point reject a legitimately computed no-op
amplifier and force a caller to decide what it meant.

### 4. `temporally_unverifiable` as a flag beside the verdict — **migration cost: medium**

Two fields must be read together, and a consumer that reads only `temporal_verdict`
conflates "the data could not separate these" with "the data never placed one of them". That
consumer will exist; the type system does not prevent it, and the mistake is invisible
because both values are `UNDETERMINED`. Promoting it to a fourth `TemporalVerdict` member is
mechanical but touches every consumer that reads the verdict, plus ADR-0007's table,
`CONVENTIONS.md` §10, and every stored edge.

### 5. `current_state` derived rather than stored — **migration cost: low-medium**

Correct for immutability and content addressing, and it means every read of an entity's
condition pays a scan over `State`. On a large corpus that is a real cost on a hot path, and
the pressure to memoize it will be constant. Adding a materialized projection later is
additive — a new derived artifact, not a change to `Entity` — but it invalidates any cached
entity view and introduces a staleness question that does not exist today.

### Also worth watching, below the top five

- **The `weighted_mean_v1` weights are asserted, not measured** (ADR-0009). They are visible,
  which is the mitigation; they are not right, and nothing in this dataset can make them so.
- **Two serialization paths coexist.** A module reaching for pydantic's own
  `model_dump_json` gets output that looks correct and is not byte-stable. Nothing currently
  detects that.
- **`Event` now carries a full `ConfidenceVector`** where it carried one float — a real
  storage and payload cost on the largest table in the system, paid so that LAW-EVIDENCE has
  no exceptions.
