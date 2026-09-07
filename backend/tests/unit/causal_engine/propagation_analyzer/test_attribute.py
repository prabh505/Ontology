"""Attribution: every failure mode names what was missing, and none of them is a zero."""

from __future__ import annotations

import pytest

from causalog.causal_engine.causal_graph_builder.graph import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE as BUILDER_NOTICE,
)
from causalog.causal_engine.propagation_analyzer import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE,
    ConsequenceSet,
    MagnitudeShare,
    PropagationContext,
    analyze_propagation,
    consequence_set,
    share_for,
)
from causalog.core.errors import ContractViolationError
from causalog.core.types import Event
from fixtures.candidates import envelope
from fixtures.propagation import (
    MEASUREMENT_ID,
    promoted_graph,
    propagation_context,
    propagation_parameters,
    storm_shaped_chain,
)


def _context(**overrides: object) -> tuple[tuple[Event, ...], PropagationContext]:
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    return events, propagation_context(
        events,
        lines,
        graph,
        propagation_parameters(**overrides),  # type: ignore[arg-type]
    )


def test_the_attribution_notice_is_the_builders_and_not_a_second_copy() -> None:
    """One sentence, one definition -- asserted by identity, not by equality.

    An earlier draft of this module wrote its own copy "so it is fixed here too", and the
    two had already drifted by the time this test was written: a reader would have seen a
    softer caveat depending on which report they opened. Identity rather than equality,
    because equality would pass again the moment somebody reintroduced a duplicate that
    happened to match on the day they wrote it.
    """
    assert ATTRIBUTION_NOT_MEASUREMENT_NOTICE is BUILDER_NOTICE


def test_a_share_carries_the_notice_as_a_property_not_a_field() -> None:
    """A stored artifact must not be able to carry a reworded caveat."""
    events, context = _context()
    share = share_for(events[2].event_id, 1.0, context)
    assert share.notice == ATTRIBUTION_NOT_MEASUREMENT_NOTICE
    assert "notice" not in MagnitudeShare.model_fields


def test_an_unknown_consequence_names_itself_rather_than_reporting_zero() -> None:
    _, context = _context()
    share = share_for("evt:nothing-here", 1.0, context)
    assert share.reading is None
    assert share.attributed is None
    assert share.unavailable_because is not None
    assert "not in this run's fact set" in share.unavailable_because


def test_an_undeclared_attribution_names_the_type_that_lost_its_magnitude() -> None:
    """A type with no `magnitude_attributions` entry has nothing nominated to apportion."""
    events, context = _context()
    origin = events[0]
    share = share_for(origin.event_id, 1.0, context)
    assert share.reading is None
    assert "magnitude_attributions" in (share.unavailable_because or "")
    assert origin.event_type in (share.unavailable_because or "")


def test_an_undeclared_combination_yields_no_total_and_says_why() -> None:
    """ADR-0049: whether two readings add is domain policy, never an engine default."""
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    context = propagation_context(events, lines, graph)
    bare = context.model_copy(
        update={"parameters": context.parameters.model_copy(update={"impact_aggregation": ()})}
    )
    result = analyze_propagation(origin.event_id, bare, envelope())
    assert result.tree.consequences.combined is None
    reason = result.tree.consequences.combination_absent_because or ""
    assert "impact_aggregation" in reason
    assert "domain policy" in reason
    assert result.report.combined_magnitude is None


def test_a_repeated_consequence_is_refused_rather_than_double_counted() -> None:
    """The guarantee is asserted at the boundary, not trusted at the call site."""
    _, context = _context()
    share = MagnitudeShare(
        event_id="evt:same",
        measurement_id=MEASUREMENT_ID,
        unit="UNITS",
        reading=1.0,
        weight=1.0,
        attributed=1.0,
    )
    with pytest.raises(ContractViolationError, match="two shares for consequence"):
        consequence_set((share, share), context)


def test_a_set_mixing_two_measurements_is_refused() -> None:
    """A total over two units is a figure whose name nobody could write down."""
    _, context = _context()
    first = MagnitudeShare(
        event_id="evt:one", measurement_id="ONE", unit="A", reading=1.0, weight=1.0, attributed=1.0
    )
    second = MagnitudeShare(
        event_id="evt:two", measurement_id="TWO", unit="B", reading=2.0, weight=1.0, attributed=2.0
    )
    with pytest.raises(ContractViolationError, match="naming measurements"):
        consequence_set((first, second), context)


def test_a_share_must_be_either_a_reading_or_a_stated_absence() -> None:
    """Neither is how a zero gets into a total; both is a contradiction."""
    with pytest.raises(ContractViolationError, match="exactly one of"):
        MagnitudeShare(event_id="evt:x", weight=1.0)
    with pytest.raises(ContractViolationError, match="exactly one of"):
        MagnitudeShare(
            event_id="evt:x",
            weight=1.0,
            reading=1.0,
            attributed=1.0,
            unavailable_because="both",
        )


def test_an_empty_set_reports_an_absence_rather_than_a_total_of_zero() -> None:
    _, context = _context()
    empty = consequence_set((), context)
    assert empty.combined is None
    assert empty.combination_absent_because is not None
    assert "not a total of zero" in empty.combination_absent_because


def test_a_consequence_set_refuses_an_unexplained_absence() -> None:
    """An absence with no reason is read as a zero by the next person to look at it."""
    with pytest.raises(ContractViolationError, match="no stated reason"):
        ConsequenceSet(event_ids=("evt:a",))
