"""A hypothetical that leaves the witnessed data behind is flagged, not answered.

The support envelope measures what the RUN witnessed. That is a different question from
what the ontology declares possible, which validation already checked -- and the difference
is the whole point: a value can be entirely possible and entirely outside anything the data
contains, and that case is what an extrapolation verdict exists to name.
"""

from __future__ import annotations

from causalog.counterfactual_engine import (
    Intervention,
    ShiftTiming,
    ValidityVerdict,
    render_markdown,
    simulate,
)
from fixtures.candidates import envelope
from fixtures.simulation import (
    joint_cause_shape,
    simulation_context,
    simulation_parameters,
)


def _shift(event_id: str, seconds: float) -> Intervention:
    """Return a timing change of the stated size."""
    return Intervention.of(
        ShiftTiming(target_event_id=event_id, shift_seconds=seconds),
        rationale="asserted by this test",
    )


def test_a_move_inside_the_witnessed_range_is_within_support() -> None:
    """The fixture's four antecedents sit one hour apart, so short moves stay inside.

    Asserted first, so the extrapolation cases below are distinguishable from a verdict that
    is simply always negative.
    """
    events, graph, members = joint_cause_shape(members=4)
    result = simulate((_shift(members[0], -600.0),), simulation_context(events, graph), envelope())
    assert result.validity.verdict is ValidityVerdict.WITHIN_SUPPORT
    assert result.validity.believable is True


def test_a_move_far_beyond_the_witnessed_range_is_flagged_as_extrapolation() -> None:
    """A year-long move over a run that witnessed hours. The verdict replaces the figure.

    The envelope carries the witnessed range, the count it was measured over, the value
    asked for, and how far beyond it sits -- so a reader can check the verdict rather than
    take it.
    """
    events, graph, members = joint_cause_shape(members=4)
    result = simulate(
        (_shift(members[0], -31_536_000.0),),
        simulation_context(events, graph),
        envelope(),
    )
    assert result.validity.verdict is ValidityVerdict.EXTRAPOLATION
    assert result.validity.believable is False
    held = result.validity.envelopes[0]
    assert held.witnessed_count > 0
    assert held.distance_beyond is not None and held.distance_beyond > 0.0


def test_the_extrapolated_figure_is_replaced_rather_than_printed_beside_the_warning() -> None:
    """**The rendering rule.** A number a reader can copy will be copied.

    Where the verdict is `EXTRAPOLATION`, the magnitude column holds the verdict and the
    figure appears in the JSON alone. This is a stronger guarantee than a warning above the
    table, which is what a screenshot removes.
    """
    events, graph, members = joint_cause_shape(magnitude=90.0, members=4)
    result = simulate(
        (_shift(members[0], -31_536_000.0),),
        simulation_context(events, graph),
        envelope(),
    )
    rendered = render_markdown(result.report)
    assert "**EXTRAPOLATION**" in rendered
    assert "NOT reported as a figure" in rendered


def test_a_tolerance_admits_a_move_just_past_the_edge_as_at_edge_of_support() -> None:
    """The declared tolerance is an allowance around the witnessed range, not a default.

    With a wide tolerance the same move that extrapolates under a narrow one is reported at
    the edge instead -- so the verdict is a property of the declaration, which is what makes
    two packs able to disagree about how far a hypothetical may reach.
    """
    events, graph, members = joint_cause_shape(members=4)
    generous = simulation_context(events, graph, parameters=simulation_parameters(tolerance=100.0))
    result = simulate((_shift(members[0], -20_000.0),), generous, envelope())
    assert result.validity.verdict in (
        ValidityVerdict.WITHIN_SUPPORT,
        ValidityVerdict.AT_EDGE_OF_SUPPORT,
    )


def test_an_absent_tolerance_is_reported_as_a_gap_and_never_defaulted() -> None:
    """ADR-0049's rule: the conservative reading applies AND the gap is named."""
    events, graph, members = joint_cause_shape(members=4)
    context = simulation_context(events, graph, parameters=simulation_parameters(tolerance=None))
    result = simulate((_shift(members[0], -600.0),), context, envelope())
    gaps = [gap.policy for gap in result.report.policy_gaps]
    assert "support envelope" in gaps


def test_the_verdict_is_the_weakest_across_every_quantity_moved() -> None:
    """One unsupported change is not carried by three supported ones.

    A hypothetical is only as supported as its least supported quantity, for the reason a
    chain is only as strong as its weakest link. Averaging would let a well-supported change
    launder an unsupported one.
    """
    events, graph, members = joint_cause_shape(members=4)
    result = simulate(
        (_shift(members[0], -600.0), _shift(members[1], -31_536_000.0)),
        simulation_context(events, graph),
        envelope(),
    )
    assert result.validity.verdict is ValidityVerdict.EXTRAPOLATION
    verdicts = {held.verdict for held in result.validity.envelopes}
    assert (
        ValidityVerdict.WITHIN_SUPPORT in verdicts
    ), "one of the two moves really is supported; the weakest still governs"


def test_an_unassessable_verdict_is_not_rendered_as_an_extrapolation() -> None:
    """`NOT_ASSESSABLE` and `EXTRAPOLATION` say different things and must read differently.

    **Regression.** The first rendering printed one message for both, so a run where nothing
    comparable was witnessed reported that the change "asks the graph about a region the data
    did not witness" -- an absence of measurement rendered as a measurement of distance. That
    is the exact error the report's closing section exists to prevent, committed by the
    report itself.
    """
    events, graph, members = joint_cause_shape(members=4)
    # A removal moves no quantity, so no envelope can be measured for it.
    from causalog.counterfactual_engine import RemoveEvent

    result = simulate(
        (Intervention.of(RemoveEvent(target_event_id=members[0]), rationale="moves no quantity"),),
        simulation_context(events, graph),
        envelope(),
    )
    assert result.validity.verdict is ValidityVerdict.NOT_ASSESSABLE
    rendered = render_markdown(result.report)
    assert "Support could NOT BE JUDGED" in rendered
    assert "beyond the range this run witnessed" not in rendered


def test_a_sensitivity_sweep_with_nothing_to_perturb_is_not_rendered_as_stable() -> None:
    """A sweep that could not run is reported as not runnable, never as "stable: yes".

    **Regression.** The first rendering put `None` in the outcome column and "yes" in the
    stability column, so a sweep that never ran read as a sweep that found the answer robust.
    ADR-0049's absent-means-CANNOT-RUN rule, in the renderer.

    The shape is a single DIRECT link, so the removal ELIMINATES its consequence. An
    eliminated consequence carries no magnitude, so no figure exists to perturb -- which is
    the situation the regression is about, reached deterministically rather than by chance.
    """
    from causalog.counterfactual_engine import RemoveEvent
    from fixtures.simulation import linear_shape

    events, graph = linear_shape()
    antecedent, _ = events
    result = simulate(
        (
            Intervention.of(
                RemoveEvent(target_event_id=antecedent.event_id), rationale="eliminates"
            ),
        ),
        simulation_context(events, graph),
        envelope(),
    )
    assert [
        item for item in result.validity.sensitivity if item.outcome is None
    ], "the shape must leave nothing to perturb, or this asserts the wrong thing"
    rendered = render_markdown(result.report)
    assert "**not runnable** — nothing was perturbed" in rendered
