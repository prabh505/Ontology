"""Pattern mining: an empty list is never published without a reason beside it."""

from __future__ import annotations

import pytest

from causalog.causal_engine.pattern_miner import (
    StructuralPatternReport,
    mine_patterns,
    render_markdown,
)
from causalog.causal_engine.propagation_analyzer import PropagationContext
from causalog.core.errors import ContractViolationError
from causalog.rule_engine import PatternMiningSpec
from fixtures.candidates import envelope
from fixtures.propagation import (
    LEVER,
    MEASURED,
    ORIGIN,
    diamond_chain,
    promoted_graph,
    propagation_context,
    storm_shaped_chain,
)


def _context() -> PropagationContext:
    events, lines = storm_shaped_chain()
    origin, lever, measured = events
    graph = promoted_graph(events, lines, ((origin, lever), (lever, measured)))
    return propagation_context(events, lines, graph)


DECLARED = PatternMiningSpec(
    motif_minimum_support=1, motif_maximum_length=4, bottleneck_minimum_degree=1
)


def test_motifs_are_reported_over_the_type_projection() -> None:
    """A claim about instances is unique by construction; a motif is about kinds."""
    report = mine_patterns(_context(), DECLARED, envelope())
    shapes = {(motif.cause_event_type, motif.effect_event_type) for motif in report.motifs}
    assert shapes == {(ORIGIN, LEVER), (LEVER, MEASURED)}
    assert report.motifs_absent_because is None


def test_every_motif_carries_the_instance_span_beside_its_count() -> None:
    """Report the span beside the count, never folded into it.

    One shape repeating inside one instance and the same count across many instances are
    different findings, and one number cannot tell them apart.
    """
    report = mine_patterns(_context(), DECLARED, envelope())
    assert report.motifs
    for motif in report.motifs:
        assert motif.occurrences >= 1
        assert motif.instance_span >= 1
        assert "process instance" in motif.detail


def test_in_degree_and_out_degree_are_never_summed() -> None:
    """Consequence collecting at a type and originating from it are different structures."""
    report = mine_patterns(_context(), DECLARED, envelope())
    by_type = {item.event_type: item for item in report.bottlenecks}
    assert by_type[LEVER].in_degree == 1
    assert by_type[LEVER].out_degree == 1
    assert by_type[ORIGIN].in_degree == 0
    assert by_type[MEASURED].out_degree == 0


def test_an_undeclared_support_threshold_says_nothing_was_looked_for() -> None:
    """ADR-0049. An empty list alone would read as 'there are no patterns'."""
    report = mine_patterns(_context(), PatternMiningSpec(), envelope())
    assert report.motifs == ()
    assert report.motifs_absent_because is not None
    assert "motif_minimum_support" in report.motifs_absent_because
    assert report.bottlenecks == ()
    assert "bottleneck_minimum_degree" in (report.bottlenecks_absent_because or "")
    rendered = render_markdown(report)
    assert "not a finding that there are no patterns" in rendered


def test_an_unreached_threshold_says_so_and_names_the_denominator() -> None:
    """A measured absence, distinguished from an unrun check by naming what was examined."""
    report = mine_patterns(
        _context(),
        PatternMiningSpec(motif_minimum_support=99, bottleneck_minimum_degree=99),
        envelope(),
    )
    assert report.motifs == ()
    reason = report.motifs_absent_because or ""
    assert "reaches the declared support" in reason
    assert "measured absence rather than an unrun check" in reason
    assert report.shapes_examined > 0


def test_the_report_states_the_motif_length_it_actually_enumerates() -> None:
    """Nobody should infer that longer shapes were searched for and not found."""
    report = mine_patterns(_context(), DECLARED, envelope())
    assert report.maximum_motif_length_enumerated == 2
    assert report.declared_motif_maximum_length == 4
    assert "enumerated to length" in render_markdown(report)


def test_a_diamond_makes_one_shape_recur() -> None:
    """The projection collapses two instance-level claims of one shape into one motif."""
    events, lines = diamond_chain()
    origin, left, right, shared = events
    graph = promoted_graph(
        events, lines, ((origin, left), (origin, right), (left, shared), (right, shared))
    )
    report = mine_patterns(propagation_context(events, lines, graph), DECLARED, envelope())
    origin_to_measured = next(
        motif
        for motif in report.motifs
        if motif.cause_event_type == ORIGIN and motif.effect_event_type == MEASURED
    )
    assert origin_to_measured.occurrences == 2


def test_a_report_refuses_an_empty_section_with_no_stated_reason() -> None:
    """The invariant that makes every absence above legible."""
    with pytest.raises(ContractViolationError, match="empty with no stated reason"):
        StructuralPatternReport(
            envelope=envelope(),
            standing=_context().view.standing,
            shapes_examined=0,
            links_examined=0,
            maximum_motif_length_enumerated=2,
        )
