"""The five edge kinds propagate differently, and the differences are asserted by hand.

Every expected figure below is computed in the test's own prose from the fixture's declared
shares and magnitudes, not read back out of the implementation. That is the whole point: an
assertion that restates what the code does passes whatever the code does.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from causalog.causal_engine.causal_graph_builder.graph import PromotedGraph
from causalog.core.types import Event
from causalog.core.types.causal_edge import CausalEdgePayload
from causalog.counterfactual_engine import (
    ChangeAttribute,
    DeltaKind,
    Intervention,
    RemoveEvent,
    ShiftTiming,
    simulate,
)
from fixtures.candidates import envelope
from fixtures.facts import entity, evidence_record
from fixtures.propagation import MEASURED, ORIGIN, valued_event
from fixtures.simulation import (
    amplifying,
    conditional,
    derived_precedence_between,
    direct,
    inhibiting,
    instant,
    joint_cause_shape,
    linear_shape,
    promoted,
    simulation_context,
)


def _consequence(result: object) -> object:
    """Return the one delta describing the measured consequence."""
    deltas = [
        delta
        for delta in result.world.diff.deltas  # type: ignore[attr-defined]
        if delta.event_type == MEASURED
    ]
    assert len(deltas) == 1, "the fixture holds exactly one measured consequence"
    return deltas[0]


def _remove(event_id: str) -> Intervention:
    """Return a removal of one occurrence."""
    return Intervention.of(RemoveEvent(target_event_id=event_id), rationale="asserted by this test")


# ---------------------------------------------------------------------------
# The analytically known scenario.
# ---------------------------------------------------------------------------


def test_a_direct_link_removed_eliminates_its_consequence() -> None:
    """One antecedent, one consequence, one DIRECT link: removing the antecedent ends it.

    The base case, and the only case in this file where "prevented" is the right answer.
    Nothing else transmits into the consequence, so nothing holds it up.
    """
    events, graph = linear_shape(magnitude=90.0)
    antecedent, consequence = events
    result = simulate(
        (_remove(antecedent.event_id),), simulation_context(events, graph), envelope()
    )

    delta = _consequence(result)
    assert DeltaKind.ELIMINATED in delta.kinds
    assert delta.present_in_simulated is False
    assert delta.simulated_magnitude is None, (
        "an occurrence that does not happen carries no magnitude; a value for something "
        "that did not occur has no referent"
    )
    assert consequence.event_id in result.world.diff.eliminated_event_ids
    assert result.world.diff.reduced_event_ids == ()


# ---------------------------------------------------------------------------
# THE DIFFERENTIATOR. Read the assertion, not the implementation.
# ---------------------------------------------------------------------------


def test_removing_one_of_several_contributing_causes_does_not_eliminate_the_outcome() -> None:
    """Four joint causes at an equal 0.25 share; remove one and 0.75 of 90.0 remains.

    **The single most common counterfactual error, asserted against a hand-computed
    constant.** 90.0 x (1 - 0.25) = 67.5. The consequence STILL HAPPENS: the other three
    members hold it up, exactly as `GLOSSARY.md`'s Joint Cause Group entry says they must.

    A simulator that answered "prevented" here would report the same thing an independent
    edge's removal reports, and every downstream check would pass on it.
    """
    events, graph, members = joint_cause_shape(magnitude=90.0, members=4)
    result = simulate((_remove(members[0]),), simulation_context(events, graph), envelope())

    delta = _consequence(result)
    assert (
        delta.present_in_simulated is True
    ), "the consequence still occurs: three of its four joint causes survive the removal"
    assert DeltaKind.MAGNITUDE_REDUCED in delta.kinds
    assert DeltaKind.ELIMINATED not in delta.kinds
    assert delta.simulated_magnitude == pytest.approx(
        67.5
    ), "90.0 scaled by the 0.75 that survives one 0.25 share being removed"
    assert delta.event_id not in result.world.diff.eliminated_event_ids
    assert delta.event_id in result.world.diff.reduced_event_ids


def test_reduced_and_eliminated_are_never_the_same_collection() -> None:
    """A consequence that got smaller is never reported among those that stopped.

    The counts are held apart by the type rather than by the caller's care, so a renderer
    cannot add them into one headline.
    """
    events, graph, members = joint_cause_shape(magnitude=90.0, members=4)
    result = simulate((_remove(members[0]),), simulation_context(events, graph), envelope())
    diff = result.world.diff
    assert not set(diff.reduced_event_ids) & set(diff.eliminated_event_ids)


def test_removing_every_member_of_a_joint_group_does_eliminate_the_outcome() -> None:
    """The other half of the same rule: nothing left to hold it up, so it stops.

    Asserted beside the partial case deliberately. A simulator that never eliminates is as
    wrong as one that always does, and only the pair distinguishes correct behaviour from a
    hard-coded answer.
    """
    events, graph, members = joint_cause_shape(magnitude=90.0, members=4)
    result = simulate(
        tuple(_remove(member) for member in members),
        simulation_context(events, graph),
        envelope(),
    )
    delta = _consequence(result)
    assert DeltaKind.ELIMINATED in delta.kinds
    assert delta.present_in_simulated is False


# ---------------------------------------------------------------------------
# Conditional links.
# ---------------------------------------------------------------------------


def _conditional_shape(
    expression: str, *, holds: bool = True
) -> tuple[tuple[Event, ...], PromotedGraph, Event, Event]:
    """Return a two-occurrence shape joined by one CONDITIONAL link."""
    citation = evidence_record("row-conditional")
    participant = entity("C", citation=citation)
    antecedent = valued_event(ORIGIN, instant(0), citation=citation, participants=(participant,))
    consequence = valued_event(
        MEASURED, instant(4), citation=citation, participants=(participant,), magnitude=40.0
    )
    events = (antecedent, consequence)
    from fixtures.simulation import _graph  # the fixture's own assembler

    graph = _graph((promoted(antecedent, consequence, conditional(expression, holds=holds)),))
    return events, graph, antecedent, consequence


def test_a_conditional_link_stops_transmitting_when_its_condition_is_invalidated() -> None:
    """Change an attribute the recorded condition names, and the link stops carrying.

    The condition is re-checked by asking whether its recorded expression NAMES anything the
    change touched. Here it does, so the link stops and the consequence is eliminated -- not
    because its antecedent went away, but because the qualification no longer holds.
    """
    events, graph, antecedent, consequence = _conditional_shape(
        "SUBJECT.tier == 'HELD' and SUBJECT.magnitude > 0"
    )
    from causalog.core.ontology_view import AttributeView, MutabilityView

    context = simulation_context(events, graph).model_copy(
        update={
            "mutability": (
                MutabilityView(
                    event_type=ORIGIN,
                    mutable_attributes=(AttributeView(name="tier", type_name="STRING"),),
                ),
            )
        }
    )
    change = Intervention.of(
        ChangeAttribute(
            target_event_id=antecedent.event_id, attribute_name="tier", new_value="RELEASED"
        ),
        rationale="the condition names this attribute",
    )
    result = simulate((change,), context, envelope())

    assert result.admission.rejected == (), "the attribute is declared changeable"
    delta = _consequence(result)
    assert DeltaKind.CONDITION_INVALIDATED in delta.kinds
    assert DeltaKind.ELIMINATED in delta.kinds
    assert delta.present_in_simulated is False


def test_a_conditional_link_keeps_transmitting_when_the_change_names_nothing_it_holds() -> None:
    """A change touching an attribute the condition does not name leaves the link alone.

    The other half of the test above. Without it, a simulator that invalidated EVERY
    conditional link would pass the first assertion and be entirely wrong.
    """
    events, graph, antecedent, consequence = _conditional_shape("SUBJECT.tier == 'HELD'")
    from causalog.core.ontology_view import AttributeView, MutabilityView

    context = simulation_context(events, graph).model_copy(
        update={
            "mutability": (
                MutabilityView(
                    event_type=ORIGIN,
                    mutable_attributes=(AttributeView(name="unrelated", type_name="STRING"),),
                ),
            )
        }
    )
    change = Intervention.of(
        ChangeAttribute(
            target_event_id=antecedent.event_id,
            attribute_name="unrelated",
            new_value="SOMETHING",
        ),
        rationale="the condition names nothing this change touches",
    )
    result = simulate((change,), context, envelope())

    # The consequence is UNCHANGED, so it produces no delta at all -- it is counted in
    # `unchanged_count` instead. That is the assertion: a delta here would mean the change
    # reached it, and it did not.
    assert not [
        delta for delta in result.world.diff.deltas if delta.event_type == MEASURED
    ], "the condition still holds, so the link still carries and nothing about it changed"
    assert consequence.event_id not in result.world.diff.eliminated_event_ids
    assert result.world.diff.unchanged_count >= 1


def test_a_condition_that_never_held_carries_nothing_to_begin_with() -> None:
    """A link that never held carries nothing, so removing its antecedent ends nothing.

    The consequence has no surviving basis and no lost basis: it was never carried by this
    link at all, so the change leaves it exactly where it was.
    """
    events, graph, antecedent, consequence = _conditional_shape(
        "SUBJECT.tier == 'HELD'", holds=False
    )
    result = simulate(
        (_remove(antecedent.event_id),), simulation_context(events, graph), envelope()
    )
    measured = [delta for delta in result.world.diff.deltas if delta.event_type == MEASURED]
    assert measured == [] or DeltaKind.ELIMINATED not in measured[0].kinds


# ---------------------------------------------------------------------------
# Modifiers.
# ---------------------------------------------------------------------------


def _modified_shape(
    payload_factory: Callable[[float], CausalEdgePayload],
    multiplier: float,
    magnitude: float,
) -> tuple[tuple[Event, ...], PromotedGraph, Event]:
    """Return a shape whose consequence is both carried and modified."""
    citation = evidence_record("row-modifier")
    participant = entity("M", citation=citation)
    carrier = valued_event(ORIGIN, instant(0), citation=citation, participants=(participant,))
    modifier = valued_event(ORIGIN, instant(1), citation=citation, participants=(participant,))
    consequence = valued_event(
        MEASURED,
        instant(6),
        citation=citation,
        participants=(participant,),
        magnitude=magnitude,
    )
    from fixtures.simulation import _graph

    graph = _graph(
        (
            promoted(carrier, consequence, direct()),
            promoted(modifier, consequence, payload_factory(multiplier), weight=1.0),
        )
    )
    return (carrier, modifier, consequence), graph, modifier


def test_removing_an_amplifier_makes_the_consequence_smaller_and_never_absent() -> None:
    """An amplifier removed undoes its multiply: 90.0 recorded under x1.5 was 60.0 without.

    `AmplifyingCause` is not a cause of the consequence's existence, only of its size, so
    the consequence still happens. A measured magnitude already CONTAINS the amplification,
    which is why removing the amplifier divides rather than multiplies.
    """
    events, graph, modifier = _modified_shape(amplifying, 1.5, 90.0)
    result = simulate((_remove(modifier.event_id),), simulation_context(events, graph), envelope())
    delta = _consequence(result)
    assert delta.present_in_simulated is True
    assert DeltaKind.MAGNITUDE_SCALED in delta.kinds
    assert DeltaKind.ELIMINATED not in delta.kinds
    assert delta.simulated_magnitude == pytest.approx(60.0), "90.0 / 1.5"


def test_removing_an_inhibitor_makes_the_consequence_larger() -> None:
    """The same arithmetic in the other direction: 40.0 recorded under x0.5 was 80.0 without.

    An inhibitor is a positive, recorded occurrence, so taking it away makes the consequence
    bigger. Both kinds ride one scale precisely so this needs no separate branch.
    """
    events, graph, modifier = _modified_shape(inhibiting, 0.5, 40.0)
    result = simulate((_remove(modifier.event_id),), simulation_context(events, graph), envelope())
    delta = _consequence(result)
    assert delta.present_in_simulated is True
    assert delta.simulated_magnitude == pytest.approx(80.0), "40.0 / 0.5"


# ---------------------------------------------------------------------------
# Timing.
# ---------------------------------------------------------------------------


def test_a_consequence_is_retimed_only_when_the_source_computed_its_instant() -> None:
    """With the derivation measured, a move carries downstream by the same amount."""
    events, graph = linear_shape(magnitude=90.0)
    antecedent, consequence = events
    context = simulation_context(
        events, graph, derived_precedence=derived_precedence_between(antecedent, consequence)
    )
    move = Intervention.of(
        ShiftTiming(target_event_id=antecedent.event_id, shift_seconds=-1800.0),
        rationale="half an hour earlier",
    )
    result = simulate((move,), context, envelope())
    delta = _consequence(result)
    assert DeltaKind.RETIMED in delta.kinds
    assert delta.shifted_by_seconds == pytest.approx(-1800.0)


def test_without_the_measurement_nothing_downstream_moves_and_the_report_says_so() -> None:
    """No derivation measured, so no transfer function, so no downstream instant moves.

    The absence is REPORTED as `NOT_RETIMED` rather than left silent. An unstated absence
    would let a reader conclude that the timing was checked and found unaffected.
    """
    events, graph = linear_shape(magnitude=90.0)
    antecedent, _ = events
    result = simulate(
        (
            Intervention.of(
                ShiftTiming(target_event_id=antecedent.event_id, shift_seconds=-1800.0),
                rationale="half an hour earlier",
            ),
        ),
        simulation_context(events, graph),
        envelope(),
    )
    delta = _consequence(result)
    assert DeltaKind.NOT_RETIMED in delta.kinds
    assert DeltaKind.RETIMED not in delta.kinds
    gaps = [gap for gap in result.report.policy_gaps if gap.policy == "downstream re-timing"]
    assert gaps, "the absent measurement is reported as a policy gap, never defaulted"
