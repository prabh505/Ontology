"""Synthetic, domain-neutral scaffolding for the module 11 and 12 tests.

`CONVENTIONS.md` §14: fixtures are synthetic and domain-neutral. Event types here are
`STAGE_ORIGIN`, `STAGE_LEVER` and `STAGE_MEASURED`, and nothing names a real domain -- two
modules whose whole premise is domain independence must not be tested through domain
vocabulary.

Built on `fixtures.graphs` rather than beside it, so the promoted graphs these helpers
produce are made by **running the Causal Graph Builder for real**. A hand-assembled
`PromotedGraph` could carry a weight that disagrees with its own lineage, and every test
would then be asserting against an artifact the engine would never produce.

THE GROUND TRUTH THESE FIXTURES CARRY BY CONSTRUCTION

`storm_shaped_chain` plants prd.md §29's example in domain-neutral vocabulary, and it plants
the shape the reference domain actually has rather than a convenient one:

    STAGE_ORIGIN  ->  STAGE_LEVER  ->  STAGE_MEASURED
    earliest          actionable       carries the magnitude
    NOT actionable    no magnitude     NOT actionable

Three separate facts on three separate nodes. The earliest event cannot be acted on, the
actionable event is worth nothing by itself, and the only node carrying a quantity is one
nobody can change. So "where did this start?", "what is the biggest?" and "what should we
change?" have three different answers **by construction**, and a module that collapsed them
into one number would be visibly wrong rather than arguably wrong. This is not a contrived
arrangement: the DataCo pack declares exactly it, with the dispatch event actionable and the
delivery event that carries the measured variance not.

`diamond_chain` plants one consequence reachable by two routes, so that a magnitude counted
per route rather than per node is arithmetically visible against a hand-computed constant.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder import build_causal_graph
from causalog.causal_engine.causal_graph_builder.graph import PromotedGraph
from causalog.causal_engine.propagation_analyzer import PropagationContext, stated_view
from causalog.causal_engine.propagation_analyzer.view import (
    GraphStanding,
    GraphView,
    _IndexedView,
    _Link,
)
from causalog.core.ontology_view import (
    ActionabilityView,
    MagnitudeMeasurementView,
    MeasurementExpressionOperator,
    MeasurementExpressionView,
    MeasurementKindView,
    OrdinalClassView,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TimeInterval
from causalog.core.types import Entity, Event, EvidenceRecord, Timeline, TimelineView
from causalog.rule_engine import ImpactAggregationSpec, PropagationAnalysisSpec
from causalog.rule_engine.dsl import MagnitudeAttributionSpec, RootCauseAnalysisSpec
from causalog.rule_engine.facts import FactSet
from fixtures.candidates import RUN_ID
from fixtures.facts import ONTOLOGY_HASH, confidence, entity, evidence_record, interval, timeline
from fixtures.graphs import build_context, candidate, graph_parameters
from fixtures.graphs import scored_graph as run_scoring

__all__ = [
    "LEVER",
    "MEASURED",
    "MEASURED_ATTRIBUTE",
    "MEASUREMENT_ID",
    "ORIGIN",
    "actionability",
    "cost_classes",
    "diamond_chain",
    "measurement",
    "promoted_graph",
    "propagation_context",
    "propagation_parameters",
    "root_cause_parameters",
    "scale_graph",
    "severity_classes",
    "storm_shaped_chain",
    "valued_event",
]

#: The three type names these fixtures use. Abstract, so nothing implies a domain.
ORIGIN = "STAGE_ORIGIN"
LEVER = "STAGE_LEVER"
MEASURED = "STAGE_MEASURED"

#: The one declared measurement. Attributed only to `MEASURED`, which is what makes the
#: actionable node worth nothing by itself.
MEASUREMENT_ID = "STAGE_MAGNITUDE"

#: The attribute the measurement reads. Deliberately not named for any metric stem: those
#: are exactly what `scripts/check_metrics_are_declared.py` fires on, and a fixture needing
#: an allowlist entry would be teaching the wrong lesson.
MEASURED_ATTRIBUTE = "magnitude"


def measurement() -> MagnitudeMeasurementView:
    """Return the one declared measurement: read one attribute off `MEASURED`.

    An `ATTRIBUTE` leaf rather than an arithmetic tree, because these tests are about
    attribution and traversal and not about the evaluator -- `core.measurement` has its own
    tests for the nine operators.
    """
    return MagnitudeMeasurementView(
        id=MEASUREMENT_ID,
        kind=MeasurementKindView.COUNT,
        unit="UNITS",
        expression=MeasurementExpressionView(
            op=MeasurementExpressionOperator.ATTRIBUTE,
            event_type=MEASURED,
            attribute=MEASURED_ATTRIBUTE,
        ),
    )


def actionability() -> tuple[ActionabilityView, ...]:
    """Return the declared actionability of the three types, as the adapter would.

    `LEVER` is the only actionable one, and it is the one carrying no magnitude. That
    disagreement is the whole point of the fixture.
    """
    return (
        ActionabilityView(
            event_type=LEVER, actionable=True, cost_class="LOW", severity_class="MAJOR"
        ),
        ActionabilityView(event_type=MEASURED, actionable=False, severity_class="CRITICAL"),
        ActionabilityView(event_type=ORIGIN, actionable=False, severity_class="INFORMATIONAL"),
    )


def cost_classes() -> tuple[OrdinalClassView, ...]:
    """Return an ordinal cost vocabulary, sequenced by rank."""
    return (
        OrdinalClassView(id="LOW", rank=1),
        OrdinalClassView(id="MODERATE", rank=2),
        OrdinalClassView(id="HIGH", rank=3),
    )


def severity_classes() -> tuple[OrdinalClassView, ...]:
    """Return an ordinal severity vocabulary, sequenced by rank."""
    return (
        OrdinalClassView(id="INFORMATIONAL", rank=0),
        OrdinalClassView(id="MAJOR", rank=3),
        OrdinalClassView(id="CRITICAL", rank=4),
    )


def valued_event(
    event_type: str,
    occurred_at: TimeInterval,
    *,
    citation: EvidenceRecord,
    participants: tuple[Entity, ...] = (),
    is_actionable: bool = False,
    magnitude: float | None = None,
) -> Event:
    """Return an event that optionally carries a readable magnitude on itself.

    A variant of `fixtures.facts.event` rather than a widening of it: that builder is used
    by every module-9 and module-10 test and adding a parameter there would move two hundred
    content addresses for a reason unrelated to those tests.
    """
    entity_ids = tuple(participant.entity_id for participant in participants)
    changed: tuple[tuple[str, str], ...] = (("stage", event_type),)
    if magnitude is not None:
        changed = (*changed, (MEASURED_ATTRIBUTE, f"{magnitude:.6f}"))
    citation_id = citation.evidence_record_id
    return Event(
        event_id=Event.address(
            ONTOLOGY_HASH, event_type, entity_ids, occurred_at, changed, (citation_id,)
        ),
        event_type=event_type,
        occurred_at=occurred_at,
        trigger=None,
        source_entity_ids=entity_ids,
        target_entity_ids=(),
        changed_attributes=changed,
        metadata=(("origin", "fixture"),),
        provenance_class=ProvenanceClass.OBSERVED,
        confidence=confidence(evidence_record_ids=(citation_id,)),
        is_actionable=is_actionable,
        source_record_ref=citation_id,
        evidence_record_ids=(citation_id,),
    )


def _instance(event: Event) -> Timeline:
    """Return a one-event process-instance timeline.

    One instance per consequence, deliberately. A measurement is defined over one instance
    (`core.measurement`'s own contract), so giving each consequence its own instance is what
    lets each carry its own reading -- which is what makes a double-counted total visible as
    a wrong number rather than as a coincidence.
    """
    return timeline(
        event,
        view=TimelineView.PROCESS_INSTANCE,
        process_definition_id="FIXTURE_PROCESS",
    )


def storm_shaped_chain(
    *, magnitude: float = 10.0
) -> tuple[tuple[Event, ...], tuple[Timeline, ...]]:
    """Return prd.md §29's three-node shape: earliest, actionable, and measured.

    Two days apart with DAY precision, so `verdict` returns `CERTAIN` for every forward pair
    -- which is what lets the promotion path be exercised at all.

    Returns the events in chain sequence, so a caller can name them positionally:
    `origin, lever, measured = events`.
    """
    citation = evidence_record("row-storm")
    participant = entity("A", citation=citation)
    origin = valued_event(ORIGIN, interval(0), citation=citation, participants=(participant,))
    lever = valued_event(
        LEVER, interval(2), citation=citation, participants=(participant,), is_actionable=True
    )
    measured = valued_event(
        MEASURED,
        interval(4),
        citation=citation,
        participants=(participant,),
        magnitude=magnitude,
    )
    events = (origin, lever, measured)
    return events, tuple(_instance(item) for item in events)


def diamond_chain(
    *, left: float = 3.0, right: float = 5.0, shared: float = 7.0
) -> tuple[tuple[Event, ...], tuple[Timeline, ...]]:
    """Return a diamond: one origin, two intermediates, one shared consequence.

    ORIGIN -> LEFT -> SHARED and ORIGIN -> RIGHT -> SHARED. All three consequences carry a
    magnitude, so the correct set total is `left + right + shared` and a per-route total
    would be `left + right + 2*shared`. The two differ by `shared`, which is the constant
    `tests/graph/test_impact_is_not_double_counted.py` asserts against.

    Returns `(origin, left, right, shared)` in that sequence.
    """
    citation = evidence_record("row-diamond")
    participant = entity("D", citation=citation)
    origin = valued_event(ORIGIN, interval(0), citation=citation, participants=(participant,))
    left_event = valued_event(
        MEASURED, interval(2), citation=citation, participants=(participant,), magnitude=left
    )
    right_event = valued_event(
        MEASURED, interval(3), citation=citation, participants=(participant,), magnitude=right
    )
    shared_event = valued_event(
        MEASURED, interval(6), citation=citation, participants=(participant,), magnitude=shared
    )
    events = (origin, left_event, right_event, shared_event)
    return events, tuple(_instance(item) for item in events)


def propagation_parameters(
    *,
    maximum_depth: int | None = 6,
    node_cap: int | None = 500,
    operator: str = "SUM",
    composition: str | None = "weakest_link_v1",
) -> PropagationAnalysisSpec:
    """Return a fully declared propagation spec, with every bound overridable.

    Every knob is a parameter so a test can withdraw exactly one declaration and assert the
    reported gap, which is the failure mode ADR-0049 makes the module responsible for.
    """
    return PropagationAnalysisSpec(
        maximum_depth=maximum_depth,
        traversal_node_cap=node_cap,
        impact_aggregation=(
            ImpactAggregationSpec(
                measurement_id=MEASUREMENT_ID,
                operator=operator,
                rationale="fixture combination; not calibrated against anything",
            ),
        ),
        path_confidence_composition=composition,
    )


def root_cause_parameters(
    *,
    ranking_function: str | None = "prevented_weight_v1",
    minimum_chain_scalar: float | None = None,
    candidate_cap: int | None = 100,
    recurrence_minimum_support: int | None = 2,
) -> RootCauseAnalysisSpec:
    """Return a fully declared ranking spec, with every knob overridable.

    `minimum_chain_scalar` defaults to None rather than to a number: the fixture graphs
    are scored under `permissive_scoring`, whose whole purpose is to make promotion
    reachable, and a floor here would silently re-impose the thing that fixture removes.
    """
    return RootCauseAnalysisSpec(
        ranking_function=ranking_function,
        minimum_chain_scalar=minimum_chain_scalar,
        candidate_cap=candidate_cap,
        recurrence_minimum_support=recurrence_minimum_support,
    )


def promoted_graph(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    links: tuple[tuple[Event, Event], ...],
) -> PromotedGraph:
    """Run modules 9-10 and the Causal Graph Builder for real over the named links.

    `links` names the pairs to propose, cause first. Everything else is defaulted, and
    scoring runs under `permissive_scoring` so the promotion path is reachable -- the
    shipped pack puts `STRONG` at 0.70 and nothing on the measured slice reaches it, which
    is the honest finding module 10 reports and a terrible basis for testing a traversal.
    """
    proposals = tuple(candidate(source, target) for source, target in links)
    scored = run_scoring(proposals, events, timelines)
    context = build_context(
        events,
        timelines,
        proposals,
        graph_parameters(
            attributions=(
                MagnitudeAttributionSpec(
                    effect_event_type=MEASURED,
                    measurement_id=MEASUREMENT_ID,
                    rationale="fixture attribution; not calibrated against anything",
                ),
            )
        ),
        measurements=(measurement(),),
    )
    from fixtures.candidates import envelope

    return build_causal_graph(scored, context, envelope()).graph


def propagation_context(
    events: tuple[Event, ...],
    timelines: tuple[Timeline, ...],
    graph: PromotedGraph,
    parameters: PropagationAnalysisSpec | None = None,
    *,
    run_id: str = RUN_ID,
) -> PropagationContext:
    """Return a propagation context over a real promoted graph."""
    return PropagationContext(
        facts=FactSet.of(events=events),
        timelines=timelines,
        view=stated_view(graph),
        parameters=parameters if parameters is not None else propagation_parameters(),
        magnitude_measurements=(measurement(),),
        magnitude_attributions=((MEASURED, MEASUREMENT_ID),),
        run_id=run_id,
    )


def scale_graph(
    event_count: int, fan_out: int, *, actionable_every: int = 2
) -> tuple[PropagationContext, str, str]:
    """Build a wide layered graph at a chosen scale, and a context over it.

    **Assembled through the view's own internals rather than through modules 9-10 and the
    graph builder**, and the reason is stated rather than left as a shortcut: scoring ten
    thousand claims takes minutes and is not what a traversal benchmark is timing. Reaching
    into `propagation_analyzer.view` is confined to this fixture, which is the package's own
    scaffolding, so no test file imports a private name.

    The links carry exactly what a promoted edge carries -- a confidence, an apportioned
    weight, a provenance class -- so the traversal does the same work it does in production.

    FANNED RATHER THAN CHAINED, deliberately. Each event links forward to the next
    `fan_out` events, so every node has real out-degree and the ancestor set of a late
    outcome is most of the graph -- which is the expensive shape, because the query asks a
    counterfactual re-reachability question per candidate. A single chain would give one
    ancestor per level and would measure almost nothing.

    An earlier version of this fixture strided by a fixed width, and every ancestor of the
    final node then shared that node's index parity -- so with actionability set on even
    indices, not one candidate was actionable and the ranking path went unmeasured. The
    stride is one because a benchmark that silently skips half the work it claims to time is
    worse than no benchmark.

    Returns the context, the first event's identifier (a seed) and the last one's (an
    outcome).
    """
    citation = evidence_record("row-scale")
    participant = entity("S", citation=citation)
    events = tuple(
        valued_event(
            MEASURED if index % 3 else LEVER,
            interval(index),
            citation=citation,
            participants=(participant,),
            is_actionable=index % actionable_every == 0,
            magnitude=float(index % 17) if index % 3 else None,
        )
        for index in range(event_count)
    )
    links = tuple(
        _Link(
            source_event_id=events[index].event_id,
            target_event_id=events[index + step].event_id,
            edge_kind="DIRECT",
            link_scalar=0.4,
            weight=1.0 / (1 + step),
            provenance_class=ProvenanceClass.INFERRED,
        )
        for index in range(event_count)
        for step in range(1, 1 + fan_out)
        if index + step < event_count
    )
    view: GraphView = _IndexedView(links, GraphStanding.STATED, RUN_ID)
    context = PropagationContext(
        facts=FactSet.of(events=events),
        timelines=tuple(_instance(item) for item in events),
        view=view,
        parameters=propagation_parameters(),
        magnitude_measurements=(measurement(),),
        magnitude_attributions=((MEASURED, MEASUREMENT_ID),),
        run_id=RUN_ID,
    )
    return context, events[0].event_id, events[-1].event_id
