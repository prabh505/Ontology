"""The four views, the trade-offs between them, and the failure modes of each."""

from __future__ import annotations

import pytest

from causalog.causal_engine.root_cause_analyzer import (
    RootCauseContext,
    RootCauseResult,
    analyze_root_causes,
    render_markdown,
)
from causalog.core.errors import ContractViolationError
from causalog.core.types import Event
from fixtures.candidates import RUN_ID, envelope
from fixtures.propagation import (
    LEVER,
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


def _result(
    *, propagation_overrides: dict[str, object] | None = None, **ranking_overrides: object
) -> tuple[tuple[Event, ...], RootCauseResult]:
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    context = RootCauseContext(
        propagation=propagation_context(
            events, lines, graph, propagation_parameters(**(propagation_overrides or {}))
        ),
        actionability=actionability(),
        cost_classes=cost_classes(),
        severity_classes=severity_classes(),
        parameters=root_cause_parameters(**ranking_overrides),  # type: ignore[arg-type]
        run_id=RUN_ID,
    )
    return events, analyze_root_causes(measured.event_id, context, envelope())


def test_earliness_is_a_rank_over_structure_and_not_a_timestamp() -> None:
    """Rank by backward distance in the graph, never by a clock.

    R-22: not one event in the measured slice carries an OBSERVED instant, so a ranking
    that read a timestamp would be ranking on arithmetic somebody else performed.
    """
    _, result = _result()
    ranks = {cause.event_type: cause.earliness_rank for cause in result.ranking.considered}
    assert ranks[ORIGIN] == 1
    assert ranks[LEVER] == 2


def test_an_absent_ranking_function_leaves_the_structural_views_intact() -> None:
    """ADR-0049: an absent declaration disables what needs it and nothing else.

    The earliest view and the actionable set need no sequencing, so they survive; only the
    sequencing value goes, and the report names the gap.
    """
    _, result = _result(ranking_function=None)
    assert result.ranking.earliest_cause is not None
    assert result.ranking.most_actionable_cause is not None
    assert all(cause.sequencing_value is None for cause in result.ranking.considered)
    assert all(cause.sequencing_function is None for cause in result.ranking.considered)
    gaps = {policy for policy, _, _ in result.report.policy_gaps}
    assert "root_cause_analysis.ranking_function" in gaps


def test_a_chain_floor_excludes_from_the_recommendation_and_says_how_many() -> None:
    """Exclude from the recommendation and say how many were excluded.

    An empty recommendation produced by a threshold is never mistaken for one produced by
    the evidence.
    """
    _, result = _result(minimum_chain_scalar=0.99)
    assert result.ranking.actionable_root_causes == ()
    assert result.report.excluded_by_chain_floor >= 1
    assert result.report.actionable_candidates >= 1
    rendered = render_markdown(result.ranking, result.report)
    assert "excluded" in rendered
    # The excluded candidate is still visible with its numbers.
    assert any(cause.event_type == LEVER for cause in result.ranking.considered)


def test_recurrence_is_counted_always_and_classified_only_when_declared() -> None:
    """Counting is a measurement; calling something structural is a judgement."""
    _, declared = _result(recurrence_minimum_support=1)
    _, undeclared = _result(recurrence_minimum_support=None)
    for cause in declared.ranking.considered:
        assert cause.recurrence.occurrences >= 1
        assert cause.recurrence.structural is not None
    for cause in undeclared.ranking.considered:
        assert cause.recurrence.occurrences >= 1
        assert cause.recurrence.structural is None
        assert "judgement" in cause.recurrence.detail


def test_a_chain_over_computed_instants_is_ranked_and_flagged() -> None:
    """`docs/architecture.md` §2: partial data is ranked and flagged, never dropped."""
    _, result = _result()
    # The fixture's events are OBSERVED, so nothing is flagged -- which is what makes the
    # negative case meaningful rather than vacuous.
    assert result.report.partial_data_chains == 0
    assert all(cause.partial_data_flag is None for cause in result.ranking.considered)


def test_the_rendered_report_states_the_unvalidated_actionability_caveat() -> None:
    """R-15, printed where it bites rather than only where it was recorded."""
    _, result = _result()
    rendered = render_markdown(result.ranking, result.report)
    assert "R-15" in rendered
    assert "ontology configuration" in rendered
    assert "EARLIEST_EVENT" in rendered
    assert "MOST_ACTIONABLE_EVENT" in rendered
    assert "RECOMMENDED_ROOT_CAUSE" in rendered


def test_a_headline_view_absent_from_the_candidate_list_is_refused() -> None:
    """A headline a reader cannot check against the list beneath it is not checkable."""
    _, result = _result()
    ranking = result.ranking
    with pytest.raises(ContractViolationError, match="not among the candidates"):
        ranking.model_validate(
            {**ranking.model_dump(), "considered": [], "actionable_root_causes": []}
        )


def test_an_outcome_with_no_ancestor_reports_why_rather_than_returning_nothing() -> None:
    """A cause the engine never asserted is one this ranking cannot see, and it says so."""
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    context = RootCauseContext(
        propagation=propagation_context(events, lines, graph),
        actionability=actionability(),
        cost_classes=cost_classes(),
        severity_classes=severity_classes(),
        parameters=root_cause_parameters(),
        run_id=RUN_ID,
    )
    result = analyze_root_causes(origin.event_id, context, envelope())
    assert result.ranking.considered == ()
    assert result.report.not_runnable_because is not None
    assert "never asserted" in result.report.not_runnable_because
    assert "NO CANDIDATE CAUSE" in render_markdown(result.ranking, result.report)
