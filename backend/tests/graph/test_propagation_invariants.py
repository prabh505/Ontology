"""Ground truth by construction: the fixture knows the answer because it built it.

`CONVENTIONS.md` §14 forbids any test asserting that a causal conclusion is CORRECT -- this
dataset has no causal ground truth. Nothing here does. What these fixtures have is
**structural** ground truth: a graph built so that the earliest node is declared unactionable
and a later one is declared actionable, so that "where did this start?" and "what should we
change?" have different answers by construction. Asserting that both are surfaced is a
statement about the module's output shape, not about the world.

That is exactly prd.md §29's storm example, and it is also the shape the reference pack
actually declares -- the dispatch event is actionable and the delivery event that carries the
measured variance is not. The fixture is not contrived to make the test pass.
"""

from __future__ import annotations

from causalog.causal_engine.propagation_analyzer import (
    GraphStanding,
    PropagationContext,
    TruncationReason,
    analyze_propagation,
)
from causalog.causal_engine.root_cause_analyzer import (
    RootCauseContext,
    RootCauseResult,
    analyze_root_causes,
)
from causalog.causal_engine.root_cause_analyzer.views import ViewName
from causalog.core.types import Event
from fixtures.candidates import RUN_ID, envelope
from fixtures.propagation import (
    LEVER,
    MEASURED,
    ORIGIN,
    actionability,
    cost_classes,
    promoted_graph,
    propagation_context,
    propagation_parameters,
    root_cause_parameters,
    severity_classes,
    storm_shaped_chain,
)


def _storm(
    **parameter_overrides: object,
) -> tuple[tuple[Event, ...], PropagationContext, RootCauseResult]:
    """Build the three-node chain, promote it for real, and rank its final consequence."""
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    propagation = propagation_context(
        events,
        lines,
        graph,
        propagation_parameters(**parameter_overrides),  # type: ignore[arg-type]
    )
    context = RootCauseContext(
        propagation=propagation,
        actionability=actionability(),
        cost_classes=cost_classes(),
        severity_classes=severity_classes(),
        parameters=root_cause_parameters(),
        run_id=RUN_ID,
    )
    return events, propagation, analyze_root_causes(measured.event_id, context, envelope())


def test_the_fixture_actually_promoted_something() -> None:
    """An empty graph would satisfy every assertion below, so emptiness is refused first.

    The DEF-0001 / OQ-014 shape: a check that cannot run must never read as a check that
    passed. Every other test in this file would pass over a graph with no edges.
    """
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    assert len(graph.edges) == 2
    assert not graph.demotions


def test_earliest_and_most_actionable_are_different_events() -> None:
    """prd.md §29's whole point: the two questions have two answers, and both are surfaced."""
    _, _, result = _storm()
    ranking = result.ranking
    assert ranking.earliest_cause is not None
    assert ranking.most_actionable_cause is not None
    assert ranking.earliest_cause.event_type == ORIGIN
    assert ranking.most_actionable_cause.event_type == LEVER
    assert ranking.earliest_cause.event_id != ranking.most_actionable_cause.event_id
    assert not ranking.views_agree


def test_the_earliest_event_is_reported_even_though_nobody_can_act_on_it() -> None:
    """ADR-0008 rejected returning a single ranked list precisely because it drops this."""
    _, _, result = _storm()
    earliest = result.ranking.earliest_cause
    assert earliest is not None
    assert earliest.actionability.is_actionable is False
    assert earliest.event_id not in {
        cause.event_id for cause in result.ranking.actionable_root_causes
    }


def test_the_recommendation_contains_only_actionable_causes() -> None:
    """An unactionable recommendation is not a recommendation (prd.md §29)."""
    _, _, result = _storm()
    recommended = result.ranking.actionable_root_causes
    assert recommended
    assert all(cause.actionability.is_actionable for cause in recommended)
    assert {cause.event_type for cause in recommended} == {LEVER}


def test_a_trade_off_is_emitted_naming_both_sides() -> None:
    """A user who disagrees with the recommendation must be able to see the alternative."""
    _, _, result = _storm()
    records = result.ranking.trade_offs
    assert records
    pairs = {(record.first_view, record.second_view) for record in records}
    assert (ViewName.EARLIEST, ViewName.MOST_ACTIONABLE) in pairs
    for record in records:
        assert record.first_event_id != record.second_event_id
        assert record.first_view.value in record.detail
        assert record.second_view.value in record.detail


def test_the_node_carrying_the_magnitude_is_not_the_actionable_one() -> None:
    """The fixture's third fact, which is what makes the three views genuinely disagree."""
    events, propagation, _ = _storm()
    origin, _, measured = events
    tree = analyze_propagation(origin.event_id, propagation, envelope()).tree
    valued = tuple(node for node in tree.nodes if node.magnitude.reading is not None)
    assert len(valued) == 1
    assert valued[0].event_type == MEASURED
    assert valued[0].is_actionable is False


def test_depth_and_breadth_are_separate_measures() -> None:
    """prd.md §30 lists them as two. A module that averaged them would fail here."""
    events, propagation, _ = _storm()
    origin, _, _ = events
    tree = analyze_propagation(origin.event_id, propagation, envelope()).tree
    assert tree.depth == 2
    assert tree.breadth == 1
    assert tree.depth != tree.breadth


def test_a_declared_depth_of_one_truncates_and_says_so() -> None:
    """Reaching the bound is truncation, never completion (`docs/architecture.md` §2)."""
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    propagation = propagation_context(events, lines, graph, propagation_parameters(maximum_depth=1))
    tree = analyze_propagation(origin.event_id, propagation, envelope()).tree
    assert tree.depth == 1
    assert tree.truncated
    assert {record.reason for record in tree.truncations} == {TruncationReason.DEPTH_BOUND}
    assert measured.event_id in tree.truncations[0].unwalked_event_ids


def test_an_undeclared_depth_reports_not_runnable_rather_than_zero() -> None:
    """ADR-0049: an absent declaration is reported, never defaulted."""
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    propagation = propagation_context(
        events, lines, graph, propagation_parameters(maximum_depth=None)
    )
    result = analyze_propagation(origin.event_id, propagation, envelope())
    assert result.tree.nodes == ()
    assert result.tree.not_runnable_because is not None
    assert "maximum_depth" in result.tree.not_runnable_because
    assert result.report.consequence_count == 0
    gaps = {gap.policy for gap in result.report.policy_gaps}
    assert "propagation_analysis.maximum_depth" in gaps


def test_a_stated_traversal_never_carries_a_diagnostic_standing() -> None:
    """The standing is a required field, and it follows the view rather than the caller."""
    events, propagation, result = _storm()
    assert propagation.view.standing is GraphStanding.STATED
    assert result.ranking.standing is GraphStanding.STATED
    assert result.ranking.standing_notice is None


def test_every_ranked_cause_carries_its_evidence_and_its_whole_vector() -> None:
    """LAW-EVIDENCE: a ranked result with no evidence chain is a bare assertion."""
    _, _, result = _storm()
    assert result.ranking.considered
    for cause in result.ranking.considered:
        assert cause.evidence_item_ids
        assert cause.confidence.components
        assert cause.chain_links
        assert cause.chain.link_scalars
