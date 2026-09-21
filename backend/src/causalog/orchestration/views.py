"""The L9/L10 translation seam: reasoning artifacts rendered as wire-safe views.

**Why this module exists at all.** Forbidden edge F5 gives `causalog.api` exactly three
import targets -- `core`, `orchestration`, and itself -- so the API layer physically cannot
name `PromotedGraph`, `RootCauseRanking`, `SimulatedWorld`, `Recommendation`, or even
`GraphStanding`. That is not an inconvenience to route around; it is the boundary that
stops a route handler from reaching into a reasoning package and computing something.
Translation therefore happens here, where importing a reasoning package is legal, and the
API serializes what this module returns.

**Why some views are hand-written and others carry a canonical body.** The API shell is
frozen at `api_schema_version` 1.0.0 (ADR-0085); the reasoning artifacts it carries are
still `draft` in `CONTEXT.md` §6, and modules 7, 8 and 15 do not exist. Hand-mirroring a
draft type into a frozen wire shape would freeze it by assertion in a second place -- the
error OQ-009 exists to prevent. So:

* Anything the API **guarantees structurally** is a hand-written, frozen view:
  `ConfidenceView` (components, `min_length=1`), `EvidenceReference`, `ProvenanceSummary`,
  `RootCauseView`'s four never-merged fields, the separation of `SimulatedEventView` from
  `EventView`.
* Everything else travels as `body`: `core.serialization.canonical_form` output, which is
  the **frozen** canonical wire shape (ADR-0023) that `CONTEXT.md` §6 already names the
  Visualization API as a consumer of. It carries its own `schema_version`, so a reader can
  re-validate an artifact this module does not describe. This is migration 0013's ruling
  applied to the wire instead of to a column, for the same stated reason.

The cost is real and is recorded rather than glossed: a client reading `body` is reading a
shape that may change without an API version bump. `docs/api.md` says so on every endpoint
that has one, and the fields a client may rely on are exactly the hand-written ones.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.propagation_analyzer import GraphStanding
from causalog.core.provenance import ProvenanceClass
from causalog.core.serialization import canonical_form
from causalog.core.temporal import TimeInterval
from causalog.core.types import ConfidenceVector, Event, EvidenceRecord

__all__ = [
    "ConfidenceComponentView",
    "ConfidenceView",
    "EventView",
    "EvidenceReference",
    "GraphEdgeView",
    "GraphNodeView",
    "GraphStandingView",
    "GraphSubgraphView",
    "InterventionSpec",
    "JobStageView",
    "JobView",
    "OntologyConceptView",
    "OntologySummaryView",
    "PlateauGroupView",
    "ProvenanceSummary",
    "RankedCauseView",
    "RecommendationSetView",
    "RecommendationView",
    "RootCauseView",
    "RulePackView",
    "RuleSummaryView",
    "RunComparisonView",
    "RunView",
    "SimulatedEventView",
    "SimulationView",
    "StageStatusView",
    "TimeIntervalView",
    "TimelineEntryView",
    "TimelineView",
    "TradeOffView",
    "ValidationStatusView",
    "WithheldRecommendationView",
    "artifact_body",
    "confidence_view",
    "event_view",
    "evidence_references",
    "provenance_summary",
    "standing_view",
]


class GraphStandingView(str, Enum):
    """Which graph a traversal walked (ADR-0059), mirrored for the presentation layer.

    A mirror rather than a re-export because `GraphStanding` lives in `causal_engine` (L6)
    and the API may not import it. The two are kept in step by
    `tests/api/test_standing_mirror_is_total.py`, which enumerates both enums: a member
    added to one and not the other fails, so the mirror cannot silently narrow.

    `UNPROMOTED_DIAGNOSTIC` is carried into responses ON PURPOSE. It marks output the
    engine has disowned -- walked over module 10's scored graph before promotion -- and
    ADR-0059 defends it with a required field, one construction site, a validator refusing
    `INFERRED`, and a fixed notice. OQ-026 records the residual risk honestly: none of
    those four mechanisms survives a screenshot. The API adds the fifth it can: the notice
    is a REQUIRED field on any response carrying this standing, not an optional annotation.
    """

    STATED = "STATED"
    UNPROMOTED_DIAGNOSTIC = "UNPROMOTED_DIAGNOSTIC"


class StageStatusView(str, Enum):
    """Whether the pipeline stage behind a payload actually produced it.

    `NOT_RUNNABLE` is what an endpoint returns when its owning module has not been built --
    modules 7, 8 and 15 today. It is a 200 with a full envelope and an explicit statement,
    never an empty success: `docs/architecture.md` §2 requires that a partially computed
    run "returns what exists with the stage stated, never a silently truncated graph", and
    an empty list with no explanation is exactly the silent truncation that forbids.
    """

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_RUNNABLE = "NOT_RUNNABLE"


class ConfidenceComponentView(BaseModel):
    """One named, inspectable component of a confidence number (LAW-EVIDENCE)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_name: str = Field(min_length=1)
    value: float = Field(ge=0.0, le=1.0)
    provenance_class: ProvenanceClass
    evidence_record_ids: tuple[str, ...] = ()


class ConfidenceView(BaseModel):
    """A confidence number that cannot exist without its decomposition.

    `components` carries `min_length=1`, so **the API is structurally incapable of
    returning a bare float wearing a confidence's name**. LAW-EVIDENCE says a bare float is
    a defect; this makes it an unconstructable one rather than something a test has to go
    looking for. It is the same move ADR-0075 made for a recommendation's evidence, in the
    place a client actually reads.

    `scalar` is derived and names the `aggregation` that produced it, exactly as
    `ConfidenceVector` does. A consumer that reads `scalar` and ignores `components` has
    been given everything it needs to know better.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scalar: float = Field(ge=0.0, le=1.0)
    aggregation: str = Field(min_length=1)
    provenance_class: ProvenanceClass
    components: tuple[ConfidenceComponentView, ...] = Field(min_length=1)


class EvidenceReference(BaseModel):
    """A citation resolving back to the record that justified an assertion.

    A reference, not the evidence itself: `CONVENTIONS.md` §7 forbids any message or
    payload from carrying a raw source record, and `source_locator` names where the record
    is without reproducing what it says.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_record_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)


class ProvenanceSummary(BaseModel):
    """The epistemic status of a payload, without flattening the five classes.

    `weakest` is `core.provenance.combine` over everything in the payload, which returns
    the weakest input and never a stronger one (ADR-0005). `present` is every class the
    payload actually contains, so a reader can see that a response mixing `OBSERVED` facts
    with one `SIMULATED` value is not uniformly simulated.

    Both are carried because either alone misleads. `weakest` alone hides that most of a
    payload is observed; `present` alone leaves a reader to compute the floor themselves
    and get it wrong. `docs/architecture.md` §2 forbids the API from "flattening five
    provenance classes into two", and reporting only one summary number would be that.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    weakest: ProvenanceClass
    present: tuple[ProvenanceClass, ...] = Field(min_length=1)


class TimeIntervalView(BaseModel):
    """An instant as this system actually knows it: a bounded interval with a precision.

    Never collapsed to a single timestamp. ADR-0021 makes time an interval because a
    day-granular source does not know an instant, and a wire shape that emitted `t_earliest`
    alone would hand a client a precision the data does not have -- which is the failure
    LAW-TIME's whole interval treatment exists to avoid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    t_earliest: datetime
    t_latest: datetime
    precision: str = Field(min_length=1)
    provenance_class: ProvenanceClass
    source: str


class EventView(BaseModel):
    """One OBSERVED-or-derived event. Distinct from `SimulatedEventView`, permanently."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    occurred_at: TimeIntervalView
    trigger: str | None = None
    source_entity_ids: tuple[str, ...] = ()
    target_entity_ids: tuple[str, ...] = ()
    provenance_class: ProvenanceClass
    confidence: ConfidenceView
    is_actionable: bool
    evidence_record_ids: tuple[str, ...] = ()


class SimulatedEventView(BaseModel):
    """An event in a simulated world, deliberately NOT an `EventView`.

    OQ-031 and prd.md §37: a simulated value must never be presentable as an observed one.
    Module 13 already holds that structurally -- a `SimulatedWorld` contains no `Event` and
    no `TimeInterval` (ADR-0068) -- and this type carries the guarantee onto the wire. The
    two have different names, different fields, and appear under different response keys,
    so an interface cannot render one as the other by accident and a client cannot
    deserialize one into the other's type.

    Note what is missing and why: there is no `occurred_at: TimeIntervalView` here. A
    simulated instant is a `core.perturbation.SimulatedInstant`, not a `TimeInterval`, and
    giving this view the observed field name would undo ADR-0068 at the last hop.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated_event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    #: Always `SIMULATED`. Constrained rather than merely documented, so the one value this
    #: field may hold is enforced by the type instead of by the code that fills it.
    provenance_class: ProvenanceClass = Field(default=ProvenanceClass.SIMULATED, frozen=True)
    derived_from_event_id: str | None = None
    body: dict[str, Any] = Field(default_factory=dict)


class TimelineEntryView(BaseModel):
    """One entry in a timeline: an event, or a marked gap where an event is absent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(min_length=1)
    event_id: str | None = None
    occurred_at: TimeIntervalView | None = None
    sequence_index: int = Field(ge=0)
    detail: str | None = None


class TimelineView(BaseModel):
    """One process instance's timeline. A gap is a marked entry, never an interpolation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeline_id: str = Field(min_length=1)
    process_instance_id: str = Field(min_length=1)
    entries: tuple[TimelineEntryView, ...] = ()
    provenance_class: ProvenanceClass


class GraphNodeView(BaseModel):
    """One node of an extracted subgraph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    occurred_at: TimeIntervalView | None = None
    provenance_class: ProvenanceClass
    depth_from_seed: int = Field(ge=0)


class GraphEdgeView(BaseModel):
    """One edge of an extracted subgraph, carrying its confidence and its temporal verdict.

    `temporal_verdict` and `temporally_unverifiable` are separate fields and are both
    carried. On the committed slice 79.3% of claims are stopped by the temporal verdict
    rather than by any threshold (R-22), so an edge payload that omitted the verdict would
    leave a client unable to tell a weak claim from an untimeable one -- which is the single
    most common misreading this dataset invites.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    causal_edge_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    target_event_id: str = Field(min_length=1)
    edge_kind: str = Field(min_length=1)
    confidence: ConfidenceView
    propagation_weight: float
    provenance_class: ProvenanceClass
    temporal_verdict: str = Field(min_length=1)
    temporally_unverifiable: bool


class GraphSubgraphView(BaseModel):
    """An extracted subgraph, with what was left out stated rather than implied."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    standing: GraphStandingView
    standing_notice: str | None = None
    seed_event_id: str | None = None
    depth: int = Field(ge=0)
    nodes: tuple[GraphNodeView, ...] = ()
    edges: tuple[GraphEdgeView, ...] = ()
    #: True when the traversal hit its bound. A truncated graph that does not say so is the
    #: "silently truncated graph" `docs/architecture.md` §2 names as a failure mode.
    truncated: bool = False
    truncation_detail: str | None = None
    #: Why the subgraph is empty, when it is. An empty `edges` list reads as "this event
    #: causes nothing", and on this dataset the true statement is almost always different:
    #: the graph was built, claims were made, and every one of them was refused -- with its
    #: reason recorded in the rejection ledger. Returning the empty list without the reason
    #: invites precisely the wrong reading of a correct result.
    empty_because: str | None = None
    #: How many claims the builder declined to promote. Carried beside the empty graph
    #: because it is the number that makes the emptiness interpretable: zero promoted out of
    #: zero proposed and zero promoted out of several thousand are different situations.
    rejected_claim_count: int = Field(default=0, ge=0)


class TradeOffView(BaseModel):
    """One pair of root-cause views that name different events, and what it costs to pick."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    first_view: str = Field(min_length=1)
    first_event_id: str = Field(min_length=1)
    second_view: str = Field(min_length=1)
    second_event_id: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class RankedCauseView(BaseModel):
    """One candidate cause, with its chain, its evidence and its caveats attached."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    confidence: ConfidenceView
    chain_scalar: float
    chain_composition: str = Field(min_length=1)
    chain_length: int = Field(ge=0)
    earliness_rank: int = Field(ge=1)
    is_actionable: bool
    cost_class: str | None = None
    prevented_event_ids: tuple[str, ...] = ()
    prevented_magnitude: float | None = None
    prevented_unit: str | None = None
    prevented_share: float | None = None
    evidence_item_ids: tuple[str, ...] = Field(min_length=1)
    provenance_class: ProvenanceClass
    partial_data_flag: str | None = None


class PlateauGroupView(BaseModel):
    """A set of causes that the engine did not sequence, presented unsequenced (OQ-027).

    On the committed slice 310 scored links sit at exactly 0.400000, so under
    `weakest_link_v1` many chains compose identically and the recommended set is frequently
    unsequenceable. OQ-027's stated default is to present tied candidates as an explicitly
    unsequenced SET rather than as a list with an arbitrary first row -- and specifically
    **not** to break the tie on earliness, which would reintroduce ADR-0008's forbidden
    blend by the back door.

    `tied` is therefore a required field rather than an inference a client draws from equal
    scores: a client comparing floats would break the tie itself, which is the outcome this
    type exists to prevent. `members` is the set; nothing about its sequence is meaningful,
    and `docs/api.md` says so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tied: bool
    plateau_value: float | None = None
    plateau_notice: str | None = None
    members: tuple[RankedCauseView, ...] = Field(min_length=1)


class RootCauseView(BaseModel):
    """ADR-0008's four answers, as four fields that are never merged.

    `earliest` answers "where did this start?", `highest_consequence` answers "what is the
    biggest?", `most_actionable` answers "what can anybody change?", and
    `recommended_groups` answers "what should we change?". A response, interface or client
    that presents any one of them as *the* root cause is a defect (ADR-0008), and there is
    **no root-cause score anywhere on this type** -- a single number would have to weight a
    quantity against a position in a chain, and any figure produced would be a judgement
    disguised as arithmetic.

    `recommended_groups` is a tuple of `PlateauGroupView` rather than of causes, so a tie is
    representable. `actionability_notice` and `standing_notice` are carried as fields rather
    than left to the client, because a notice a client may omit is a notice that will be
    omitted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome_event_id: str = Field(min_length=1)
    standing: GraphStandingView
    standing_notice: str | None = None
    actionability_notice: str = Field(min_length=1)
    earliest: RankedCauseView | None = None
    highest_consequence: RankedCauseView | None = None
    most_actionable: RankedCauseView | None = None
    recommended_groups: tuple[PlateauGroupView, ...] = ()
    trade_offs: tuple[TradeOffView, ...] = ()
    views_agree: bool
    candidate_search_truncated: bool = False
    sequencing_function: str | None = None
    #: Why nothing was returned, when nothing was. On the committed slice the promoted
    #: graph is EMPTY, so the honest answer to most outcomes is "no cause under this
    #: standing" WITH its reason -- not an empty list, which reads as "we looked and there
    #: is nothing to find".
    empty_because: str | None = None
    provenance_class: ProvenanceClass


class SimulationView(BaseModel):
    """A counterfactual world, labelled as a simulation in its type and in its fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated_world_id: str = Field(min_length=1)
    base_world_address: str = Field(min_length=1)
    standing: GraphStandingView
    standing_notice: str | None = None
    #: The fixed notice from `core.perturbation`. Required, so a figure cannot travel
    #: without the statement that it is a plausibility simulation and not an effect
    #: estimate (OQ-007's accepted default).
    simulation_notice: str = Field(min_length=1)
    interventions: tuple[dict[str, Any], ...] = ()
    rejected_interventions: tuple[dict[str, Any], ...] = ()
    simulated_events: tuple[SimulatedEventView, ...] = ()
    validity: dict[str, Any] = Field(default_factory=dict)
    provenance_class: ProvenanceClass = Field(default=ProvenanceClass.SIMULATED, frozen=True)


class InterventionSpec(BaseModel):
    """One proposed change, as it arrives on the wire.

    Deliberately NOT module 13's `Intervention`. Forbidden edge F5 gives `causalog.api`
    three import targets -- `core`, `orchestration`, and itself -- so the API layer cannot
    name a `counterfactual_engine` type at all, and a request model that did would be
    reaching through the boundary that stops a route handler from reasoning.

    So the wire shape is a mapping plus a rationale, and `EngineFacade.counterfactual`
    parses it into module 13's closed discriminated union (ADR-0066) on the far side of the
    seam. Two validations result and neither is redundant: this side checks that a
    rationale is present, the parse checks the SHAPE against the five admissible kinds, and
    module 13 then checks the MEANING against the ontology before anything simulates.

    `rationale` carries `min_length=1` because prd.md Principle 5 requires assumptions to
    be explicit, and an intervention with no stated reason is one nobody can review.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: dict[str, Any]
    rationale: str = Field(min_length=1)


class AssumptionView(BaseModel):
    """One assumption a recommendation rests on, and what would falsify it.

    `falsified_by` is required and non-empty. An assumption nobody can test is not an
    assumption, it is a hope; naming its falsifier is what makes prd.md Principle 5's
    "assumptions" bullet something a reader can act on rather than a disclaimer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    why_needed: str = Field(min_length=1)
    falsified_by: str = Field(min_length=1)


class BenefitRangeView(BaseModel):
    """What an act is expected to prevent, as a RANGE rather than a point.

    `low`/`high` are nullable together with `unit`: a benefit whose whole is unmeasurable
    has no proportion, and ADR-0075 makes the range the artifact rather than a single
    number precisely so that an estimate cannot be read as a measurement. A `None` here
    means "not measurable from this run", never zero.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    low: float | None = None
    high: float | None = None
    point_of_departure: float | None = None
    unit: str | None = None
    headline_event_id: str | None = None


class OrdinalAssessmentView(BaseModel):
    """An ordinal band read from the pack -- a cost or an operational risk.

    `class_id` is nullable and the nullability is load-bearing in opposite directions for
    the two uses (ADR-0073): an absent COST ranks a candidate as free, which is a wrong
    number, so cost is mandatory in the pack; an absent RISK ranks it nowhere, which is a
    true statement about the pack, so risk is optional. The view carries both the same way
    and `provenance_class` is `ASSUMED` for both, because an ordinal band declared by a
    domain author is never an observation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    class_id: str | None = None
    rank: int | None = None
    span: int = Field(ge=0)
    provenance_class: ProvenanceClass


class RecommendationView(BaseModel):
    """One ranked act, with prd.md Principle 5 enforced by this type.

    Principle 5: "Every recommendation must identify: expected benefit, confidence,
    supporting evidence, assumptions." All four are REQUIRED here -- `evidence_item_ids`
    and `assumptions` carry `min_length=1`, `confidence` is a `ConfidenceView` which itself
    cannot exist without components, and `expected_benefit` has no default. **An
    unsupported recommendation cannot be instantiated**, which is the same move ADR-0075
    made on the artifact, carried to the place a client actually reads.

    That is deliberately stronger than filtering unsupported recommendations out later: a
    filter is a step somebody can forget, and a type is not.

    There is no single "score" field. `desirability` is present but names the
    `core.scalarization` function that produced it and the weights it was produced under,
    so a ranking can never be read under a weighting that did not make it. `pareto_optimal`
    is carried beside it because it is a stronger statement than a high desirability and is
    independent of any weighting.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation_id: str = Field(min_length=1)
    standing: GraphStandingView
    node_event_ids: tuple[str, ...] = Field(min_length=1)
    node_event_types: tuple[str, ...] = Field(min_length=1)
    description: str = Field(min_length=1)
    sources: tuple[str, ...] = Field(min_length=1)
    #: Principle 5, bullet 1.
    expected_benefit: BenefitRangeView
    #: Principle 5, bullet 2. A `ConfidenceView`, so it cannot be a bare float.
    confidence: ConfidenceView
    #: Principle 5, bullet 3.
    evidence_item_ids: tuple[str, ...] = Field(min_length=1)
    #: Principle 5, bullet 4.
    assumptions: tuple[AssumptionView, ...] = Field(min_length=1)
    implementation_cost: OrdinalAssessmentView
    operational_risk: OrdinalAssessmentView
    #: True when this act is a SET of nodes simulated jointly. The joint figure and the
    #: naive sum are both published (ADR-0077) so the overlap is visible rather than merely
    #: corrected.
    is_set: bool = False
    is_set_because: str | None = None
    portfolio_joint_low: float | None = None
    portfolio_joint_high: float | None = None
    affected_event_ids: tuple[str, ...] = ()
    affected_instance_count: int = Field(default=0, ge=0)
    affected_magnitude: float | None = None
    affected_magnitude_unit: str | None = None
    affected_share: float | None = None
    desirability: float | None = None
    scalarization: str | None = None
    objective_weights: tuple[tuple[str, float], ...] = ()
    pareto_optimal: bool = False
    provenance_class: ProvenanceClass


class WithheldRecommendationView(BaseModel):
    """An act the engine considered and declined to recommend, with its reason.

    Published beside the recommendations rather than discarded, for the reason the Causal
    Graph Builder publishes its rejection ledger: on this dataset the engine frequently
    recommends NOTHING, and a bare empty list says "we found nothing" where the true
    statement is "we found candidates and every one fell short, here is which test each
    failed". `reason` is the closed `WithholdingReason` vocabulary, so a client can count
    by reason without parsing prose.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_event_ids: tuple[str, ...] = Field(min_length=1)
    node_event_types: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    checked_against: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class RecommendationSetView(BaseModel):
    """What this run recommends, what it withheld, and why the set may be empty."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    standing: GraphStandingView
    standing_notice: str | None = None
    recommendations: tuple[RecommendationView, ...] = ()
    withheld: tuple[WithheldRecommendationView, ...] = ()
    withheld_by_reason: tuple[tuple[str, int], ...] = ()
    #: Why nothing is recommended, when nothing is. Same contract as `empty_because`
    #: elsewhere: an empty list without its reason invites the wrong reading of a correct
    #: result.
    empty_because: str | None = None


class ValidationStatusView(BaseModel):
    """Whether a dataset is fit to reason over, and what is wrong with it if not.

    Two independent measurements, deliberately not merged into one verdict:

    * **Mapping coverage** (module 2) -- which source columns bind to an ontology concept,
      and every finding an author should see. Answers "is this dataset DESCRIBED?".
    * **Data quality** (module 1) -- what the pinned file actually contains, with every
      finding carrying the downstream consequence of ignoring it. Answers "is this dataset
      USABLE?".

    A dataset can pass either and fail the other, and a single "valid: true/false" would
    collapse the difference. `quality_report_available` is a third state rather than a
    quiet false: a report that was never produced and a report that found nothing are
    different, and only one of them is a reason to proceed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_version: str = Field(min_length=1)
    mapping_id: str = Field(min_length=1)
    mapping_version: str = Field(min_length=1)
    ontology_pack: str = Field(min_length=1)
    ontology_version: str = Field(min_length=1)
    bound_column_count: int = Field(ge=0)
    binding_count: int = Field(ge=0)
    mapping_findings: tuple[dict[str, Any], ...] = ()
    quality_report_available: bool
    quality_report_absent_because: str | None = None
    quality_findings: tuple[dict[str, Any], ...] = ()
    row_count: int | None = None
    reject_count: int | None = None


class OntologyConceptView(BaseModel):
    """One concept a domain pack declares, as the presentation layer may see it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_kind: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    label: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class OntologySummaryView(BaseModel):
    """What ontology a run reasoned under, and what it declares."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ontology_version: str = Field(min_length=1)
    ontology_hash: str = Field(min_length=1)
    pack_schema_version: str = Field(min_length=1)
    concepts: tuple[OntologyConceptView, ...] = ()


class RuleSummaryView(BaseModel):
    """One rule, in enough detail that a user can see what governed a conclusion.

    prd.md **Principle 4** is the requirement: "the user must be able to inspect every
    inferred relationship", and a relationship inferred by a rule is not inspectable while
    the rule is invisible. `condition` and `conclusion` are rendered from the pack's own
    closed condition tree rather than paraphrased, so what a reader sees is what fired.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(min_length=1)
    rule_kind: str = Field(min_length=1)
    knowledge_provenance: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    conclusion: dict[str, Any] = Field(default_factory=dict)


class RulePackView(BaseModel):
    """The rule pack a run reasoned under, with its coverage gaps named.

    `event_types_without_a_rule` is carried because ADR-0044's coverage report exists and
    because `docs/architecture.md` §7 risk 2 is explicit that recall is bounded by rule
    coverage. Publishing the rules without publishing what they do not cover would satisfy
    Principle 4's letter and invert its purpose.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_pack_version: str = Field(min_length=1)
    rule_pack_schema_version: str = Field(min_length=1)
    rule_pack_hash: str = Field(min_length=1)
    rules: tuple[RuleSummaryView, ...] = ()
    event_types_without_a_rule: tuple[str, ...] = ()


class RunView(BaseModel):
    """One Run: the five inputs that determine it, and what has been derived from it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    ontology_hash: str = Field(min_length=1)
    rule_pack_version: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)
    seed: int
    created_at: datetime | None = None
    graph_projection_version: str | None = None
    causal_edge_count: int = Field(default=0, ge=0)


class RunComparisonView(BaseModel):
    """Two runs and the inputs that differ, so one input's effect can be isolated.

    `differing_inputs` is the point of the endpoint. Two runs that differ in one `RunKey`
    field isolate that field's effect on the output (ADR-0013's stated positive
    consequence); two runs that differ in four do not, and a comparison that did not say
    which had changed would invite the first reading regardless.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    left: RunView
    right: RunView
    differing_inputs: tuple[str, ...] = ()
    identical: bool


class JobStageView(BaseModel):
    """One stage of one execution: its status, its timing, and why it is not SUCCEEDED."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    requires: tuple[str, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None
    error_code: str | None = None
    detail: str | None = None


class JobView(BaseModel):
    """One pipeline execution, with per-stage progress and timing (prd.md §55).

    `progress` is `completed / total` over stages that CAN run. A `NOT_RUNNABLE` stage is
    excluded from the denominator rather than counted as incomplete: a job that can never
    exceed 6/9 because three modules are unbuilt would otherwise report permanent failure
    to progress, which says something false about the execution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str = Field(min_length=1)
    run_id: str | None = None
    dataset_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    stages: tuple[JobStageView, ...] = ()
    runnable_stage_count: int = Field(ge=0)
    completed_stage_count: int = Field(ge=0)
    not_runnable_stage_count: int = Field(ge=0)
    total_elapsed_seconds: float | None = None


# ---------------------------------------------------------------------------
# Conversions. Every one is total over its input and raises rather than guessing.
# ---------------------------------------------------------------------------


def standing_view(standing: GraphStanding) -> GraphStandingView:
    """Mirror a `GraphStanding` into the presentation enum.

    Total by construction: `GraphStandingView(standing.value)` raises on a member this
    mirror does not have, so adding a standing in `causal_engine` and forgetting it here
    fails loudly at the first response rather than degrading to a default.
    """
    return GraphStandingView(standing.value)


def confidence_view(vector: ConfidenceVector) -> ConfidenceView:
    """Render a `ConfidenceVector`, components and all.

    There is deliberately no overload that takes a float. LAW-EVIDENCE makes a bare float a
    defect, and the way to keep it a defect is to give the wire layer no function that
    accepts one.
    """
    return ConfidenceView(
        scalar=vector.scalar,
        aggregation=vector.aggregation,
        provenance_class=vector.provenance_class,
        components=tuple(
            ConfidenceComponentView(
                component_name=component.component_name,
                value=component.value,
                provenance_class=component.provenance_class,
                evidence_record_ids=component.evidence_record_ids,
            )
            for component in vector.components
        ),
    )


def interval_view(interval: TimeInterval) -> TimeIntervalView:
    """Render a `TimeInterval` without collapsing it to a point."""
    return TimeIntervalView(
        t_earliest=interval.t_earliest,
        t_latest=interval.t_latest,
        precision=interval.precision.value,
        provenance_class=interval.provenance,
        source=interval.source,
    )


def event_view(event: Event) -> EventView:
    """Render an `Event`. `changed_attributes` and `metadata` are deliberately omitted.

    Both are free-form `(key, value)` pairs sourced from the domain mapping, and both can
    carry values copied from a source record. `CONVENTIONS.md` §7 forbids any payload from
    leaking a raw record, and the reference that keeps the data reachable is
    `evidence_record_ids` -- a citation rather than a copy.
    """
    return EventView(
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=interval_view(event.occurred_at),
        trigger=event.trigger,
        source_entity_ids=event.source_entity_ids,
        target_entity_ids=event.target_entity_ids,
        provenance_class=event.provenance_class,
        confidence=confidence_view(event.confidence),
        is_actionable=event.is_actionable,
        evidence_record_ids=event.evidence_record_ids,
    )


def evidence_references(records: tuple[EvidenceRecord, ...]) -> tuple[EvidenceReference, ...]:
    """Render evidence records as citations, in canonical sequence."""
    return tuple(
        EvidenceReference(
            evidence_record_id=record.evidence_record_id,
            dataset_version=record.dataset_version,
            source_locator=record.source_locator,
        )
        for record in sorted(records, key=lambda item: item.evidence_record_id)
    )


def provenance_summary(classes: tuple[ProvenanceClass, ...]) -> ProvenanceSummary:
    """Summarize a payload's provenance without flattening the five classes.

    An empty input is `OBSERVED`, and that needs saying: a payload containing no assertion
    at all -- an empty event list, a run with no edges -- makes no claim, and the weakest
    class over nothing is the strongest rather than the weakest. Reporting `INFERRED` for
    an empty payload would attach an epistemic warning to the absence of any claim.
    """
    if not classes:
        return ProvenanceSummary(
            weakest=ProvenanceClass.OBSERVED, present=(ProvenanceClass.OBSERVED,)
        )
    from causalog.core.provenance import combine

    present = tuple(member for member in ProvenanceClass if member in frozenset(classes))
    return ProvenanceSummary(weakest=combine(*classes), present=present)


def artifact_body(artifact: BaseModel) -> dict[str, Any]:
    """Render a `draft` artifact through the frozen canonical wire shape (ADR-0023).

    Not `model_dump`. `canonical_form` sorts every mapping, quantizes every float through
    the one formatter, and renders every instant as ISO-8601 UTC -- which is what makes two
    responses to the same request byte-identical (`CONVENTIONS.md` §11). `model_dump` would
    follow field declaration sequence and emit unquantized floats, and the determinism test
    would then report a difference that is purely a formatting artifact.
    """
    rendered = canonical_form(artifact)
    if not isinstance(rendered, dict):
        raise TypeError(
            f"canonical_form({type(artifact).__name__}) produced "
            f"{type(rendered).__name__}, not a mapping. Every artifact body on the wire "
            "is an object so that it can carry its own schema_version."
        )
    return rendered
