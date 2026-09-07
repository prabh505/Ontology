"""Every way a proposed change is refused, one test per reason.

An impossible premise is the most dangerous input this module takes, because every check
after it passes. So every gate gets its own assertion, and the enum is checked for
exhaustiveness at the end -- a reason added later without a test fails here on the day it is
written.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from causalog.core.errors import ContractViolationError
from causalog.core.ontology_view import (
    AttributeView,
    LifecycleTransitionView,
    LifecycleView,
    MutabilityView,
    ProcessDefinitionView,
)
from causalog.counterfactual_engine import (
    ChangeAttribute,
    ChangeEntityState,
    InsertEvent,
    Intervention,
    RejectionReason,
    RemoveEvent,
    ShiftTiming,
    admit,
    simulate,
)
from fixtures.candidates import envelope
from fixtures.facts import entity, evidence_record
from fixtures.propagation import MEASURED, ORIGIN
from fixtures.simulation import joint_cause_shape, linear_shape, simulation_context


def _reasons(admission: object) -> set[RejectionReason]:
    """Return the set of reasons a validation pass recorded."""
    return {item.reason for item in admission.rejected}  # type: ignore[attr-defined]


def test_a_change_naming_an_absent_occurrence_is_refused() -> None:
    """`UNKNOWN_TARGET`. A change against nothing would be reported as applied."""
    events, graph = linear_shape()
    admission = admit(
        (Intervention.of(RemoveEvent(target_event_id="evt:nothing"), rationale="absent target"),),
        simulation_context(events, graph),
    )
    assert admission.admitted == ()
    assert _reasons(admission) == {RejectionReason.UNKNOWN_TARGET}
    assert "not an occurrence in the base world" in admission.rejected[0].detail


def test_a_move_that_would_reverse_a_stated_precedence_is_refused() -> None:
    """`WOULD_VIOLATE_LAW_TIME`. A hypothetical is not an exemption from LAW-TIME.

    The consequence sits four hours after its antecedent, so moving the antecedent six
    hours later would put it after its own consequence. The engine refuses rather than
    simulating it and attaching a flag: a world where a cause follows its effect is not one
    this engine can reason about, and every check after the premise would pass on it.
    """
    events, graph = linear_shape()
    antecedent, _ = events
    admission = admit(
        (
            Intervention.of(
                ShiftTiming(
                    target_event_id=antecedent.event_id,
                    shift_seconds=timedelta(hours=6).total_seconds(),
                ),
                rationale="six hours later, past its own consequence",
            ),
        ),
        simulation_context(events, graph),
    )
    assert _reasons(admission) == {RejectionReason.WOULD_VIOLATE_LAW_TIME}
    assert "LAW-TIME" in admission.rejected[0].checked_against


def test_an_attribute_change_with_no_declaration_at_all_is_refused() -> None:
    """`DECLARATION_ABSENT`. The absence refuses; it never permits.

    Distinct from `ATTRIBUTE_NOT_DECLARED_CHANGEABLE`, and the distinction is the point:
    that one says the pack was asked and said no, this one says the pack was never asked.
    Collapsing them would let an unconfigured run read as a validated one.
    """
    events, graph = linear_shape()
    antecedent, _ = events
    admission = admit(
        (
            Intervention.of(
                ChangeAttribute(
                    target_event_id=antecedent.event_id,
                    attribute_name="stage",
                    new_value="OTHER",
                ),
                rationale="nothing declares this",
            ),
        ),
        simulation_context(events, graph),
    )
    assert _reasons(admission) == {RejectionReason.DECLARATION_ABSENT}


def test_an_attribute_the_pack_does_not_mark_changeable_is_refused() -> None:
    """`ATTRIBUTE_NOT_DECLARED_CHANGEABLE`, and the message names the remedy."""
    events, graph = linear_shape()
    antecedent, _ = events
    context = simulation_context(events, graph).model_copy(
        update={
            "mutability": (
                MutabilityView(
                    event_type=ORIGIN,
                    mutable_attributes=(AttributeView(name="lever", type_name="STRING"),),
                ),
            )
        }
    )
    admission = admit(
        (
            Intervention.of(
                ChangeAttribute(
                    target_event_id=antecedent.event_id,
                    attribute_name="stage",
                    new_value="OTHER",
                ),
                rationale="declared, but not this attribute",
            ),
        ),
        context,
    )
    assert _reasons(admission) == {RejectionReason.ATTRIBUTE_NOT_DECLARED_CHANGEABLE}
    assert "mutable: true" in admission.rejected[0].checked_against


def test_a_value_outside_the_declared_bound_is_refused() -> None:
    """`VALUE_OUTSIDE_DECLARED_BOUND`, checked against what the DOMAIN says is possible.

    Not against what the data witnessed -- that is measured separately as a support
    envelope, and the message says so, because a value can be possible and unsupported and
    the two refusals mean different things.
    """
    events, graph = linear_shape()
    antecedent, _ = events
    context = simulation_context(events, graph).model_copy(
        update={
            "mutability": (
                MutabilityView(
                    event_type=ORIGIN,
                    mutable_attributes=(
                        AttributeView(
                            name="lever", type_name="INTEGER", admissible_range=(0.0, 10.0)
                        ),
                    ),
                ),
            )
        }
    )
    admission = admit(
        (
            Intervention.of(
                ChangeAttribute(
                    target_event_id=antecedent.event_id,
                    attribute_name="lever",
                    new_value="99",
                ),
                rationale="outside the declared bound",
            ),
        ),
        context,
    )
    assert _reasons(admission) == {RejectionReason.VALUE_OUTSIDE_DECLARED_BOUND}
    assert "support envelope" in admission.rejected[0].detail


def test_setting_an_attribute_to_the_value_it_already_holds_is_refused() -> None:
    """`CHANGES_NOTHING`. An identical world would read as evidence the lever is inert."""
    events, graph = linear_shape()
    antecedent, _ = events
    context = simulation_context(events, graph).model_copy(
        update={
            "mutability": (
                MutabilityView(
                    event_type=ORIGIN,
                    mutable_attributes=(AttributeView(name="stage", type_name="STRING"),),
                ),
            )
        }
    )
    admission = admit(
        (
            Intervention.of(
                ChangeAttribute(
                    target_event_id=antecedent.event_id,
                    attribute_name="stage",
                    new_value=ORIGIN,
                ),
                rationale="already holds this",
            ),
        ),
        context,
    )
    assert _reasons(admission) == {RejectionReason.CHANGES_NOTHING}


def test_a_transition_the_lifecycle_does_not_declare_is_refused() -> None:
    """`TRANSITION_NOT_DECLARED`, and the message lists the transitions that exist.

    A state machine is exactly the structure that makes "this world is impossible" a
    decidable question rather than a matter of taste.
    """
    events, graph = linear_shape()
    citation = evidence_record("row-linear")
    participant = entity("L", citation=citation)
    context = simulation_context(events, graph).model_copy(
        update={
            "entities": (participant,),
            "lifecycles": (
                LifecycleView(
                    entity_type=participant.entity_type,
                    initial_states=("OPEN",),
                    transitions=(
                        LifecycleTransitionView(
                            from_state="OPEN", to_state="SETTLED", triggered_by=ORIGIN
                        ),
                    ),
                ),
            ),
        }
    )
    admission = admit(
        (
            Intervention.of(
                ChangeEntityState(
                    target_entity_id=participant.entity_id,
                    from_state="SETTLED",
                    to_state="OPEN",
                    at_instant=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                rationale="backwards through the state machine",
            ),
        ),
        context,
    )
    assert _reasons(admission) == {RejectionReason.TRANSITION_NOT_DECLARED}
    assert "OPEN->SETTLED" in admission.rejected[0].detail


def test_an_insertion_no_declared_process_admits_is_refused() -> None:
    """`STEP_NOT_ADMITTED_BY_PROCESS`, checked against sequences, variants and optional steps."""
    events, graph = linear_shape()
    antecedent, _ = events
    context = simulation_context(events, graph).model_copy(
        update={
            "processes": (
                ProcessDefinitionView(
                    id="PROC_FIXTURE",
                    anchor_entity_type="THING",
                    canonical_sequence=(ORIGIN, MEASURED),
                ),
            )
        }
    )
    admission = admit(
        (
            Intervention.of(
                InsertEvent(
                    event_type="STAGE_UNDECLARED",
                    at_instant=datetime(2026, 1, 1, 2, tzinfo=UTC),
                    after_event_id=antecedent.event_id,
                ),
                rationale="no process admits this step",
            ),
        ),
        context,
    )
    assert _reasons(admission) == {RejectionReason.STEP_NOT_ADMITTED_BY_PROCESS}


def test_a_set_holding_one_inadmissible_change_never_partially_executes() -> None:
    """The admitted half still runs, and the refused half is in the ledger, not silent.

    Validation is a separate pass over the whole set, so a caller can always tell which of
    its changes took effect. A world built from three of four changes and described by an
    artifact naming four is a world nobody asked for.
    """
    events, graph, members = joint_cause_shape()
    result = simulate(
        (
            Intervention.of(RemoveEvent(target_event_id=members[0]), rationale="valid"),
            Intervention.of(RemoveEvent(target_event_id="evt:nothing"), rationale="invalid"),
        ),
        simulation_context(events, graph),
        envelope(),
    )
    assert len(result.admission.admitted) == 1
    assert len(result.admission.rejected) == 1
    assert result.report.interventions_proposed == 2
    assert result.report.interventions_admitted == 1


def test_when_every_change_is_refused_no_world_is_published() -> None:
    """An unchanged world would read as "simulated, and it had no effect". It is not one."""
    events, graph = linear_shape()
    result = simulate(
        (Intervention.of(RemoveEvent(target_event_id="evt:nothing"), rationale="invalid"),),
        simulation_context(events, graph),
        envelope(),
    )
    assert result.world is None
    assert result.report.not_runnable_because is not None
    assert "refused before anything was simulated" in result.report.not_runnable_because


def test_every_rejection_reason_has_a_test_in_this_file() -> None:
    """Exhaustiveness. A reason added later without an assertion fails here that day.

    The alternative is a closed enum whose newest member is exercised by nothing, which is
    how a gate comes to exist in the type and not in the behaviour.
    """
    import pathlib

    source = pathlib.Path(__file__).read_text()
    missing = [
        reason.value for reason in RejectionReason if f"RejectionReason.{reason.name}" not in source
    ]
    assert missing == [], f"no test asserts these rejection reasons: {missing}"


def test_simulating_a_diagnostic_graph_is_refused_without_an_explicit_opt_in() -> None:
    """OQ-026, held by the boundary rather than by a convention.

    `propagation_analyzer/view.py` states in fixed text that a diagnostic graph is not an
    input to simulation. The default refuses; the opt-in is a deliberate act at a named call
    site.
    """
    from causalog.causal_engine.propagation_analyzer import GraphStanding

    events, graph = linear_shape()
    context = simulation_context(events, graph)

    class _Disowned:
        """A view claiming a standing the engine does not stand behind."""

        standing = GraphStanding.UNPROMOTED_DIAGNOSTIC
        run_id = context.run_id

        def links_from(self, event_id: str) -> tuple[()]:
            return ()

        def links_into(self, event_id: str) -> tuple[()]:
            return ()

        def link_count(self) -> int:
            return 0

    disowned = context.model_copy(
        update={"propagation": context.propagation.model_copy(update={"view": _Disowned()})}
    )
    antecedent, _ = events
    change = Intervention.of(
        RemoveEvent(target_event_id=antecedent.event_id), rationale="over a disowned graph"
    )

    with pytest.raises(ContractViolationError, match="OQ-026"):
        simulate((change,), disowned, envelope())

    permitted = simulate((change,), disowned, envelope(), accept_unpromoted=True)
    assert permitted.report.disowned_notice is not None
    assert "NOT THE ENGINE'S VIEW" in permitted.report.disowned_notice
