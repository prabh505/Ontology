"""Fixtures for module 13: graphs whose edge KINDS are chosen, and contexts over them.

`fixtures.propagation.promoted_graph` runs modules 9, 10 and the Causal Graph Builder for
real, which is the right thing for a traversal test and the wrong thing here. Those modules
type every link they propose, and module 13's whole subject is that a `CONTRIBUTING` link
and a `DIRECT` one mean different things under a hypothetical. A fixture that cannot choose
the kind cannot exercise the difference.

So this module assembles a `PromotedGraph` directly, with the kind named per link. That is a
deliberate departure and it costs something real: these graphs did not come through the
promotion policy, so a test here proves module 13's behaviour and proves nothing about what
module 10 would have scored or what the builder would have promoted. Tests that need the
whole pipeline use the other fixture; tests that need a specific shape use this one, and
`test_simulation_properties.py` runs over both.

**Domain-neutral by default** (`CONVENTIONS.md` §14): every generated name is a synthetic
token and the type names come from `fixtures.propagation`, which chose them abstractly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from causalog.causal_engine.causal_graph_builder.graph import (
    EdgeLineage,
    JointCauseGroup,
    PromotedEdge,
    PromotedGraph,
    PropagationWeight,
    TypingBasis,
    TypingRecord,
    WeightBasis,
)
from causalog.causal_engine.propagation_analyzer import (
    PropagationContext,
    stated_view,
)
from causalog.core.precedence import DerivedPrecedence, DerivedPrecedenceIndex
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision, TimeInterval
from causalog.core.types import Event, Timeline
from causalog.core.types.causal_edge import (
    AmplifyingCause,
    CausalEdge,
    CausalEdgeKind,
    CausalEdgePayload,
    ConditionalCause,
    ContributingCause,
    DirectCause,
    InhibitingCause,
)
from causalog.core.types.evidence import EvidenceItem, EvidenceKind
from causalog.counterfactual_engine import SimulationContext, stated_links
from causalog.rule_engine import CounterfactualSimulationSpec
from causalog.rule_engine.facts import FactSet
from fixtures.candidates import RUN_ID
from fixtures.facts import confidence, entity, evidence_record
from fixtures.propagation import (
    MEASURED,
    MEASUREMENT_ID,
    ORIGIN,
    measurement,
    propagation_parameters,
    valued_event,
)

__all__ = [
    "amplifying",
    "conditional",
    "contributing",
    "derived_precedence_between",
    "direct",
    "inhibiting",
    "instant",
    "joint_cause_shape",
    "linear_shape",
    "promoted",
    "scale_shape",
    "simulation_context",
    "simulation_parameters",
    "single_instance",
]

#: A fixed base instant. Injected rather than read: `datetime.now()` in anything the engine
#: touches is a determinism defect (`CONVENTIONS.md` §11).
BASE_INSTANT = datetime(2026, 1, 1, tzinfo=UTC)

#: The one declared process these fixtures group against. Abstract, as the type names are.
PROCESS_ID = "PROC_FIXTURE"


def instant(hours: int, *, source: str | None = None) -> TimeInterval:
    """Return a placed, hour-granular interval a fixed distance from the base instant.

    `INTERVAL` precision rather than `EXACT`, and `ASSUMED` provenance, so the intervals
    behave like the ones the real pipeline produces. Separated by a whole hour, so
    `strictly_before` holds between any two and a `CERTAIN` verdict is reachable.
    """
    moment = BASE_INSTANT + timedelta(hours=hours)
    return TimeInterval(
        t_earliest=moment,
        t_latest=moment + timedelta(minutes=1),
        precision=Precision.MINUTE,
        provenance=ProvenanceClass.ASSUMED,
        source=source or f"fixture:hour-{hours}",
    )


def direct() -> CausalEdgePayload:
    """Return a `DIRECT` payload."""
    return DirectCause()


def conditional(expression: str, *, holds: bool = True) -> CausalEdgePayload:
    """Return a `CONDITIONAL` payload carrying the expression that was evaluated."""
    return ConditionalCause(condition_expression=expression, condition_holds=holds)


def contributing(group_id: str, co_causes: tuple[str, ...]) -> CausalEdgePayload:
    """Return a `CONTRIBUTING` payload naming its group and its co-causes."""
    return ContributingCause(
        joint_cause_group_id=group_id, co_cause_event_ids=tuple(sorted(co_causes))
    )


def amplifying(multiplier: float) -> CausalEdgePayload:
    """Return an `AMPLIFYING` payload. The multiplier must exceed 1.0."""
    return AmplifyingCause(magnitude_multiplier=multiplier)


def inhibiting(multiplier: float) -> CausalEdgePayload:
    """Return an `INHIBITING` payload. The multiplier must lie in [0.0, 1.0)."""
    return InhibitingCause(magnitude_multiplier=multiplier)


def _lineage() -> EdgeLineage:
    """Return a minimal lineage. Not what the real builder attributes; enough to construct."""
    return EdgeLineage(
        candidate_edge_ids=("edg:fixture",),
        generator_ids=("fixture",),
        evidence_item_ids=("evi:fixture",),
        confidence=confidence(evidence_record_ids=("evd:fixture",)),
        band_name="FIXTURE",
        scored_component_count=1,
        outcome="SCORED",
    )


def _evidence() -> tuple[EvidenceItem, ...]:
    """Return one re-verifiable evidence item, as LAW-EVIDENCE requires on every edge."""
    return (
        EvidenceItem(
            evidence_item_id="evi:fixture",
            kind=EvidenceKind.RULE,
            description="fixture link, asserted by the fixture and by nothing else",
            supporting_ids=("evd:fixture",),
            strength=1.0,
            verification="fixtures.simulation.promoted",
            provenance_class=ProvenanceClass.ASSUMED,
        ),
    )


def _weight_for(payload: CausalEdgePayload, weight: float) -> PropagationWeight:
    """Return the apportioned weight, with the basis its kind admits.

    A modifier's weight may NOT name a measurement: `PropagationWeight` refuses it, because
    citing a quantity that was not apportioned would present a share of belief as a share of
    that quantity. The fixture obeys the type rather than working around it.
    """
    if payload.edge_kind in (CausalEdgeKind.AMPLIFYING, CausalEdgeKind.INHIBITING):
        return PropagationWeight(
            weight=weight, basis=WeightBasis.MODIFIER_MULTIPLIER, competing_edge_count=0
        )
    return PropagationWeight(
        weight=weight,
        basis=WeightBasis.MEASURED_MAGNITUDE,
        measurement_id=MEASUREMENT_ID,
        competing_edge_count=0,
    )


def promoted(
    source: Event,
    target: Event,
    payload: CausalEdgePayload,
    *,
    weight: float = 1.0,
    scalar: float = 0.8,
    group_id: str | None = None,
) -> PromotedEdge:
    """Return one promoted link of the named kind, between two placed occurrences.

    `CausalEdge.between` is the only constructor that sees both intervals and therefore the
    only one that can evaluate LAW-TIME. It is used here rather than bypassed: a fixture
    that constructed an edge without the gate would let a test pass over a link the engine
    could never hold.
    """
    edge = CausalEdge.between(
        source_event=source,
        target_event=target,
        payload=payload,
        confidence=confidence(evidence_record_ids=("evd:fixture",), scalar=scalar),
        evidence=_evidence(),
        propagation_weight=weight,
        provenance_class=ProvenanceClass.INFERRED,
        run_id=RUN_ID,
    )
    return PromotedEdge(
        edge=edge,
        lineage=_lineage(),
        typing=TypingRecord(
            edge_kind=payload.edge_kind.value,
            basis=TypingBasis.RULE_DECLARED,
            supporting_rule_ids=("rul:fixture",),
        ),
        weight=_weight_for(payload, weight),
        threshold_band="FIXTURE",
        joint_cause_group_id=group_id,
    )


def _graph(
    edges: tuple[PromotedEdge, ...], groups: tuple[JointCauseGroup, ...] = ()
) -> PromotedGraph:
    """Return a promoted graph over these links, with its own arithmetic satisfied."""
    return PromotedGraph(
        run_id=RUN_ID,
        edges=tuple(
            sorted(
                edges,
                key=lambda item: (
                    item.edge.source_event_id,
                    item.edge.target_event_id,
                    item.edge.payload.edge_kind.value,
                ),
            )
        ),
        demotions=(),
        joint_groups=groups,
        claims_considered=len(edges),
    )


def single_instance(events: tuple[Event, ...]) -> tuple[Timeline, ...]:
    """Return one process-instance timeline holding every occurrence.

    One instance rather than one per occurrence, because a magnitude measurement is defined
    over an instance and module 13 reads magnitudes for consequences that must sit together.
    """
    from causalog.core.types.timeline import TimelineView
    from fixtures.facts import timeline

    return (
        timeline(
            *sorted(events, key=lambda item: item.event_id),
            view=TimelineView.PROCESS_INSTANCE,
            process_definition_id=PROCESS_ID,
        ),
    )


def simulation_parameters(
    *,
    depth: int | None = 6,
    node_cap: int | None = 500,
    tolerance: float | None = 0.10,
    perturbations: tuple[float, ...] = (0.5, 2.0),
    composition: str | None = "weakest_link_v1",
) -> CounterfactualSimulationSpec:
    """Return a fully declared simulation block, or one with a named hole.

    Every parameter is exposed so a test can withhold exactly one and assert the resulting
    `PolicyGap` -- which is how ADR-0049's absent-means-CANNOT-RUN rule is tested rather
    than assumed.
    """
    return CounterfactualSimulationSpec(
        maximum_simulation_depth=depth,
        affected_subgraph_node_cap=node_cap,
        support_envelope_tolerance=tolerance,
        sensitivity_perturbations=perturbations,
        path_composition=composition,
    )


def simulation_context(
    events: tuple[Event, ...],
    graph: PromotedGraph,
    *,
    timelines: tuple[Timeline, ...] | None = None,
    parameters: CounterfactualSimulationSpec | None = None,
    derived_precedence: DerivedPrecedenceIndex | None = None,
) -> SimulationContext:
    """Return a simulation context over a real promoted graph."""
    held = timelines if timelines is not None else single_instance(events)
    return SimulationContext(
        propagation=PropagationContext(
            facts=FactSet.of(events=events),
            timelines=held,
            view=stated_view(graph),
            parameters=propagation_parameters(),
            magnitude_measurements=(measurement(),),
            magnitude_attributions=((MEASURED, MEASUREMENT_ID),),
            run_id=RUN_ID,
        ),
        links=stated_links(graph),
        joint_groups=graph.joint_groups,
        parameters=parameters if parameters is not None else simulation_parameters(),
        derived_precedence=derived_precedence,
        run_id=RUN_ID,
    )


def linear_shape(
    *, magnitude: float = 90.0, actionable: bool = False
) -> tuple[tuple[Event, ...], PromotedGraph]:
    """Return two occurrences and one `DIRECT` link between them.

    The smallest shape that can answer "what would have happened": one antecedent, one
    measured consequence, one link.

    `actionable` stamps the antecedents' `Event.is_actionable`. It defaults to False, which
    is what every module 13 test has always had; module 14's actionability gate reads the
    stamp AND the pack declaration and refuses a candidate when they disagree, so its tests
    pass True. The parameter lives here rather than in a shape of module 14's own so that
    both modules reason over ONE world -- module 14's correctness claim is that it estimates
    through module 13, and two worlds could let that claim pass while the modules disagreed.
    """
    citation = evidence_record("row-linear")
    participant = entity("L", citation=citation)
    antecedent = valued_event(
        ORIGIN,
        instant(0),
        citation=citation,
        participants=(participant,),
        is_actionable=actionable,
    )
    consequence = valued_event(
        MEASURED,
        instant(4),
        citation=citation,
        participants=(participant,),
        magnitude=magnitude,
    )
    events = (antecedent, consequence)
    return events, _graph((promoted(antecedent, consequence, direct()),))


def joint_cause_shape(
    *, magnitude: float = 90.0, members: int = 4, actionable: bool = False
) -> tuple[tuple[Event, ...], PromotedGraph, tuple[str, ...]]:
    """Return N contributing antecedents jointly producing one measured consequence.

    **The shape the differentiator is asserted on.** Each member carries an equal
    apportioned share, so removing one leaves the consequence standing at `(N-1)/N` of its
    measured size -- a figure a reader can check by hand, which is what makes the test an
    assertion about behaviour rather than a restatement of the implementation.

    `members` defaults to FOUR rather than three, so the equal share is 0.25 and every
    figure the test asserts is exact at six decimal places (`CONVENTIONS.md` §11). At three
    members the share is 0.333333 and the surviving magnitude lands a rounding artifact away
    from two thirds -- a real property of the quantization and a terrible thing to write an
    analytic assertion against. Tests that only need "several joint causes" pass three.

    Returns the occurrences, the graph, and the member identifiers in canonical sequence.

    `actionable` stamps the antecedents' `Event.is_actionable`. It defaults to False, which
    is what every module 13 test has always had; module 14's actionability gate reads the
    stamp AND the pack declaration and refuses a candidate when they disagree, so its tests
    pass True. The parameter lives here rather than in a shape of module 14's own so that
    both modules reason over ONE world -- module 14's correctness claim is that it estimates
    through module 13, and two worlds could let that claim pass while the modules disagreed.
    """
    citation = evidence_record("row-joint")
    participant = entity("J", citation=citation)
    antecedents = tuple(
        valued_event(
            ORIGIN,
            instant(index),
            citation=citation,
            participants=(participant,),
            is_actionable=actionable,
        )
        for index in range(members)
    )
    consequence = valued_event(
        MEASURED,
        instant(members + 4),
        citation=citation,
        participants=(participant,),
        magnitude=magnitude,
    )
    member_ids = tuple(sorted(item.event_id for item in antecedents))
    share = 1.0 / members
    edges = tuple(
        promoted(
            antecedent,
            consequence,
            contributing(
                "grp:fixture",
                tuple(other for other in member_ids if other != antecedent.event_id),
            ),
            weight=share,
            group_id="grp:fixture",
        )
        for antecedent in antecedents
    )
    group = JointCauseGroup(
        joint_cause_group_id="grp:fixture",
        target_event_id=consequence.event_id,
        member_source_event_ids=member_ids,
        promoted=True,
        detail="fixture joint group; every member carries an equal apportioned share",
    )
    return (*antecedents, consequence), _graph(edges, (group,)), member_ids


def derived_precedence_between(
    cause: Event, effect: Event, *, check_id: str = "chk:fixture"
) -> DerivedPrecedenceIndex:
    """Return an index saying the source COMPUTED the effect's instant from the cause's.

    What lets a move propagate through time at all. Without it, module 13 re-times nothing
    downstream and says so -- which is itself a behaviour worth a test.
    """
    return DerivedPrecedenceIndex.of(
        (
            DerivedPrecedence(
                check_id=check_id,
                cause_interval_source=cause.occurred_at.source,
                effect_interval_source=effect.occurred_at.source,
                agreement_rate=1.0,
                evaluated=100,
                rationale="fixture derivation, asserted by the fixture and nothing else",
            ),
        )
    )


def scale_shape(
    event_count: int, fan_out: int, *, magnitude_every: int = 3, actionable: bool = False
) -> tuple[tuple[Event, ...], PromotedGraph]:
    """Build a wide layered graph at a chosen scale, with real promoted links.

    Built through `promoted` -- and therefore through `CausalEdge.between` -- rather than
    through the view internals `fixtures.propagation.scale_graph` reaches into. Module 13
    branches on the PAYLOAD, so a link assembled without one would measure a traversal this
    module does not perform. The cost is fixture construction time, which the benchmark
    reports separately and does not budget.

    FANNED RATHER THAN CHAINED, for `scale_graph`'s reason: each occurrence links forward to
    the next `fan_out` occurrences, so a change near the front reaches most of the graph,
    which is the expensive shape. A single chain would reach one consequence per level and
    would measure almost nothing.

    The kinds are MIXED -- roughly a third contributing, a sixth conditional, the rest
    direct -- because the whole subject of this module is that the kinds behave differently,
    and a benchmark over one kind would time a branch the real work does not take.

    `actionable` stamps the ORIGIN occurrences. It defaults to False, which is what module
    13's benchmark has always had; module 14's benchmark passes True, because its
    actionability gate refuses every candidate otherwise and the run would then be measured
    on having no work to do -- the failure this fixture's own callers warn about.
    """
    citation = evidence_record("row-scale")
    participant = entity("S", citation=citation)
    events = tuple(
        valued_event(
            MEASURED if index % magnitude_every else ORIGIN,
            instant(index),
            citation=citation,
            participants=(participant,),
            magnitude=float(index % 17) if index % magnitude_every else None,
            is_actionable=actionable and not index % magnitude_every,
        )
        for index in range(event_count)
    )
    edges: list[PromotedEdge] = []
    for index, source in enumerate(events):
        for step in range(1, fan_out + 1):
            target_index = index + step
            if target_index >= event_count:
                break
            target = events[target_index]
            group_id: str | None = None
            if step % 3 == 0:
                group_id = f"grp:{index}"
                payload = contributing(group_id, (events[max(0, index - 1)].event_id,))
            elif step % 6 == 1:
                payload = conditional(f"SUBJECT.tier == 'T{index % 5}'")
            else:
                payload = direct()
            edges.append(promoted(source, target, payload, weight=1.0 / fan_out, group_id=group_id))
    return events, _graph(tuple(edges))
