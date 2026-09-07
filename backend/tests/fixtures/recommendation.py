"""Fixtures for module 14, built on module 12's and module 13's rather than beside them.

Every shape here reuses `fixtures.simulation`'s occurrences and graphs. That is deliberate:
module 14's whole correctness claim is that it estimates through module 13, and a test that
built its own world would be able to pass while the two modules disagreed about what world
they were looking at.

The one thing added is a declared actionability that makes `ORIGIN` actionable.
`fixtures.propagation.actionability` deliberately makes only `LEVER` actionable, so that
module 11's tests exercise the disagreement between actionability and magnitude; module 14's
tests need a candidate that survives its own gate AND sits upstream of a measured
consequence, which is `ORIGIN` in every shape `fixtures.simulation` builds.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder import PromotedGraph
from causalog.core.ontology_view import ActionabilityView, OrdinalClassView
from causalog.core.types import Event
from causalog.recommendation_engine import RecommendationContext
from causalog.rule_engine.dsl import ObjectiveWeightSpec, RecommendationSpec
from fixtures.facts import entity, evidence_record
from fixtures.propagation import (
    LEVER,
    MEASURED,
    ORIGIN,
    cost_classes,
    severity_classes,
    valued_event,
)
from fixtures.simulation import (
    RUN_ID,
    _graph,
    direct,
    instant,
    promoted,
    simulation_context,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "actionable_everywhere",
    "bottleneck_shape",
    "disjoint_shape",
    "recommendation_context",
    "recommendation_parameters",
    "risk_classes",
    "serial_chain_shape",
]

#: Benefit-first, matching prd.md §50's stated sequence. Fixed here so a test asserting a
#: sequencing is asserting the ranker's behaviour rather than a weighting it also chose.
DEFAULT_WEIGHTS: dict[str, float] = {
    "benefit": 0.40,
    "confidence": 0.20,
    "cost": 0.25,
    "risk": 0.15,
}


def risk_classes() -> tuple[OrdinalClassView, ...]:
    """Return an ordinal operational-risk vocabulary, sequenced by rank (ADR-0073)."""
    return (
        OrdinalClassView(id="NEGLIGIBLE", rank=0),
        OrdinalClassView(id="LOW", rank=1),
        OrdinalClassView(id="MODERATE", rank=2),
        OrdinalClassView(id="HIGH", rank=3),
    )


def actionable_everywhere(*, declare_risk: bool = True) -> tuple[ActionabilityView, ...]:
    """Return a declaration in which the antecedent types can be acted on.

    `MEASURED` stays NOT actionable throughout. It is the consequence -- the thing an
    operator wants less of -- and a fixture that let module 14 recommend acting on the
    outcome itself would make the actionability gate untestable in the direction that
    matters.

    `declare_risk=False` produces the ADR-0073 gap: actionable types carrying a cost and no
    operational risk, which is exactly what the hospital pack does and what DataCo cannot
    exercise because DataCo declares all fourteen.
    """
    return (
        ActionabilityView(
            event_type=LEVER,
            actionable=True,
            cost_class="LOW",
            severity_class="MAJOR",
            risk_class="LOW" if declare_risk else None,
        ),
        ActionabilityView(event_type=MEASURED, actionable=False, severity_class="CRITICAL"),
        ActionabilityView(
            event_type=ORIGIN,
            actionable=True,
            cost_class="MODERATE",
            severity_class="INFORMATIONAL",
            risk_class="MODERATE" if declare_risk else None,
        ),
    )


def recommendation_parameters(
    *,
    weights: dict[str, float] | None = None,
    belief_floor: float | None = 0.0,
    exact_ceiling: int | None = 12,
    node_cap: int | None = 200,
    size_cap: int | None = 3,
    limit: int | None = 10,
) -> RecommendationSpec:
    """Return a fully declared policy block, or one with a named knob withheld.

    `belief_floor` defaults to 0.0 rather than to the pack's 0.5. These fixtures carry no
    calibrated belief and a realistic floor would withhold everything, making every test
    pass for the wrong reason. A test about the floor sets it explicitly.
    """
    chosen = weights if weights is not None else DEFAULT_WEIGHTS
    return RecommendationSpec(
        scalarization="weighted_desirability_v1",
        objective_weights=tuple(
            ObjectiveWeightSpec(objective=name, weight=value)
            for name, value in sorted(chosen.items())
        ),
        cut_set_exact_ceiling=exact_ceiling,
        cut_set_node_cap=node_cap,
        portfolio_size_cap=size_cap,
        maximum_recommendations=limit,
        minimum_belief_to_publish=belief_floor,
    )


def recommendation_context(
    events: tuple[Event, ...],
    graph: PromotedGraph,
    *,
    outcomes: tuple[str, ...] = (),
    parameters: RecommendationSpec | None = None,
    actionability: tuple[ActionabilityView, ...] | None = None,
) -> RecommendationContext:
    """Return a context over the same world module 13's own fixtures build.

    `outcomes` defaults to every measured consequence in the shape, which is what a caller
    outside the engine would name: "which outcome matters" is a domain question and module
    14 refuses to answer it, so the fixture answers it here rather than leaving it empty and
    silently producing no chains.
    """
    simulation = simulation_context(events, graph)
    named = outcomes or tuple(
        sorted(event.event_id for event in events if event.event_type == MEASURED)
    )
    return RecommendationContext(
        propagation=simulation.propagation,
        simulation=simulation,
        actionability=actionability if actionability is not None else actionable_everywhere(),
        cost_vocabulary=cost_classes(),
        risk_vocabulary=risk_classes(),
        severity_vocabulary=severity_classes(),
        joint_groups=graph.joint_groups,
        outcome_event_ids=named,
        parameters=parameters if parameters is not None else recommendation_parameters(),
        run_id=RUN_ID,
    )


def bottleneck_shape(*, magnitude: float = 40.0) -> tuple[tuple[Event, ...], PromotedGraph, str]:
    """Return a shape whose optimal single act is provable by inspection.

    Two independent antecedents each transmit into ONE shared node, which transmits into two
    separately measured consequences::

        ORIGIN_a ─┐
                  ├─> LEVER ─┬─> MEASURED_1
        ORIGIN_b ─┘          └─> MEASURED_2

    Every chain from either antecedent to either consequence runs through `LEVER`. Removing
    `LEVER` therefore breaks all four (source, outcome) pairs; removing either antecedent
    breaks the two that start at it. The optimum is `LEVER`, at size one, and no arithmetic
    is needed to see it -- which is what makes a test written against this an assertion about
    behaviour rather than a restatement of the search.

    `LEVER` is also declared cheaper than either antecedent by `actionable_everywhere`, so
    the shape does not accidentally test whether coverage beats cost: here the same act wins
    on both, and a test about the trade-off uses a shape where they disagree.

    Returns the occurrences, the graph, and the identifier of the known optimum.
    """
    citation = evidence_record("row-bottleneck")
    participant = entity("B", citation=citation)
    first = valued_event(
        ORIGIN, instant(0), citation=citation, participants=(participant,), is_actionable=True
    )
    second = valued_event(
        ORIGIN, instant(1), citation=citation, participants=(participant,), is_actionable=True
    )
    middle = valued_event(
        LEVER, instant(2), citation=citation, participants=(participant,), is_actionable=True
    )
    left = valued_event(
        MEASURED,
        instant(6),
        citation=citation,
        participants=(participant,),
        magnitude=magnitude,
    )
    right = valued_event(
        MEASURED,
        instant(7),
        citation=citation,
        participants=(participant,),
        magnitude=magnitude,
    )
    edges = (
        promoted(first, middle, direct()),
        promoted(second, middle, direct()),
        promoted(middle, left, direct()),
        promoted(middle, right, direct()),
    )
    events = (first, second, middle, left, right)
    return events, _graph(edges), middle.event_id


def disjoint_shape() -> tuple[tuple[Event, ...], PromotedGraph, tuple[str, str]]:
    """Return two chains that share nothing, so their benefits really are additive.

    The control case for the non-additivity test. Asserting only that an overlapping pair
    comes out below its naive total would pass against a function that always returned less
    than the sum; pairing it with a disjoint set that comes out EQUAL to its naive total
    proves the mechanism rather than a constant.
    """
    citation = evidence_record("row-disjoint")
    left_participant = entity("D1", citation=citation)
    right_participant = entity("D2", citation=citation)
    first = valued_event(
        ORIGIN,
        instant(0),
        citation=citation,
        participants=(left_participant,),
        is_actionable=True,
    )
    second = valued_event(
        ORIGIN,
        instant(1),
        citation=citation,
        participants=(right_participant,),
        is_actionable=True,
    )
    left = valued_event(
        MEASURED,
        instant(5),
        citation=citation,
        participants=(left_participant,),
        magnitude=30.0,
    )
    right = valued_event(
        MEASURED,
        instant(6),
        citation=citation,
        participants=(right_participant,),
        magnitude=30.0,
    )
    edges = (promoted(first, left, direct()), promoted(second, right, direct()))
    return (
        (first, second, left, right),
        _graph(edges),
        (first.event_id, second.event_id),
    )


def serial_chain_shape(
    *, magnitude: float = 40.0
) -> tuple[tuple[Event, ...], PromotedGraph, tuple[str, str]]:
    """Return one strictly serial chain: two acts, one consequence, on the same route.

    ``ORIGIN ─> LEVER ─> MEASURED``

    **The shape non-additivity is asserted on.** Either act removes the same consequence, so
    each is individually worth the whole magnitude and the two together are worth the whole
    magnitude ONCE. Adding them gives twice the truth, which is precisely the mistake an
    operator makes when a ranked list shows two acts and says nothing about their relation.

    Returns the occurrences, the graph, and the two act identifiers in canonical sequence.
    """
    citation = evidence_record("row-serial")
    participant = entity("S", citation=citation)
    first = valued_event(
        ORIGIN, instant(0), citation=citation, participants=(participant,), is_actionable=True
    )
    middle = valued_event(
        LEVER, instant(2), citation=citation, participants=(participant,), is_actionable=True
    )
    last = valued_event(
        MEASURED,
        instant(6),
        citation=citation,
        participants=(participant,),
        magnitude=magnitude,
    )
    edges = (promoted(first, middle, direct()), promoted(middle, last, direct()))
    return (
        (first, middle, last),
        _graph(edges),
        tuple(sorted((first.event_id, middle.event_id))),  # type: ignore[return-value]
    )
