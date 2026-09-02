"""As-of correctness across transition boundaries, and the contradiction guard it relies on.

Synthetic and domain-neutral (`CONVENTIONS.md` §14).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from causalog.core.derivation import current_state
from causalog.core.errors import ContractViolationError
from causalog.core.ontology_view import LifecycleTransitionView, LifecycleView
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.types import Entity, Event, TimelineView
from causalog.graph_engine.state_engine import StateDerivationResult, StateEngine, state_as_of
from causalog.graph_engine.timeline_builder import TimelineBuilder
from tests.fixtures import facts


def _lifecycle() -> LifecycleView:
    return LifecycleView(
        entity_type="PARTICIPANT",
        initial_states=("OPEN",),
        transitions=(
            LifecycleTransitionView(from_state="OPEN", to_state="MIDDLE", triggered_by="STAGE_ONE"),
            LifecycleTransitionView(
                from_state="MIDDLE", to_state="CLOSED", triggered_by="STAGE_TWO"
            ),
        ),
    )


def _envelope() -> OutputEnvelope:
    run_key = RunKey(
        dataset_version=facts.DATASET_VERSION,
        ontology_hash=facts.ONTOLOGY_HASH,
        rule_pack_version="unset",
        engine_version="0.1.0",
        seed=1,
    )
    return OutputEnvelope(
        run_id=run_key.address(),
        ontology_version="1.0.0",
        ontology_hash=facts.ONTOLOGY_HASH,
        dataset_version=facts.DATASET_VERSION,
        rule_pack_version="unset",
        engine_version="0.1.0",
        graph_projection_version="gpv:0000000000000000",
        seed=1,
        execution_id="exec:test",
    )


def _derive() -> tuple[Entity, Event, Event, StateDerivationResult]:
    participant = facts.entity("p1", citation=facts.evidence_record("r0"))
    e1 = facts.event(
        "STAGE_ONE",
        facts.interval(0),
        citation=facts.evidence_record("r1"),
        participants=(participant,),
    )
    e2 = facts.event(
        "STAGE_TWO",
        facts.interval(1),
        citation=facts.evidence_record("r2"),
        participants=(participant,),
    )
    builder = TimelineBuilder((), facts.ONTOLOGY_HASH)
    timelines = tuple(
        t
        for t in builder.build((e1, e2), (participant,), _envelope()).timelines
        if t.view is TimelineView.ENTITY
    )
    engine = StateEngine((_lifecycle(),), (), facts.ONTOLOGY_HASH)
    result = engine.derive(timelines, (participant,), (e1, e2), _envelope())
    return participant, e1, e2, result


def test_as_of_just_before_and_just_after_a_transition_boundary() -> None:
    participant, e1, e2, result = _derive()
    day0 = facts.EPOCH
    day1 = facts.EPOCH + timedelta(days=1)

    before_first = state_as_of(result.states, participant.entity_id, day0 - timedelta(hours=1))
    assert before_first.state.state_name == "OPEN"
    assert before_first.confidence_class.value == "ASSUMED"  # the synthesized bootstrap

    just_after_first = state_as_of(result.states, participant.entity_id, day0 + timedelta(hours=1))
    assert just_after_first.state.state_name == "MIDDLE"
    assert just_after_first.produced_by_event_id == e1.event_id

    just_after_second = state_as_of(result.states, participant.entity_id, day1 + timedelta(hours=1))
    assert just_after_second.state.state_name == "CLOSED"
    assert just_after_second.produced_by_event_id == e2.event_id


def test_current_state_still_raises_on_a_genuine_contradiction() -> None:
    """The widen-on-uncertainty design in `replay.py` must not disable this guard."""
    participant = facts.entity("p1", citation=facts.evidence_record("r0"))
    contradictory = (
        facts.state(
            participant,
            "OPEN",
            facts.interval(0, span_days=2),
            derived_from=_dummy_event(),
            citation=facts.evidence_record("r1"),
        ),
        facts.state(
            participant,
            "MIDDLE",
            facts.interval(1, span_days=2),
            derived_from=_dummy_event(),
            citation=facts.evidence_record("r2"),
        ),
    )
    with pytest.raises(ContractViolationError):
        current_state(
            contradictory, participant.entity_id, facts.EPOCH + timedelta(days=1, hours=12)
        )


def _dummy_event() -> Event:
    participant = facts.entity("p1", citation=facts.evidence_record("r0"))
    return facts.event(
        "STAGE_ONE",
        facts.interval(0),
        citation=facts.evidence_record("rd"),
        participants=(participant,),
    )
