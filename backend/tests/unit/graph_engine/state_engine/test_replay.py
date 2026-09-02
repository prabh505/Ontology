"""State replay: golden happy path, illegal transitions, and mid-lifecycle bootstrap.

Synthetic and domain-neutral (`CONVENTIONS.md` §14), matching `tests/fixtures/facts.py`'s
own vocabulary.
"""

from __future__ import annotations

from causalog.core.ontology_view import LifecycleTransitionView, LifecycleView
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.types import Entity, Event, Timeline, TimelineView
from causalog.graph_engine.state_engine import StateEngine
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


def _timelines_for(events: tuple[Event, ...], participant: Entity) -> tuple[Timeline, ...]:
    builder = TimelineBuilder((), facts.ONTOLOGY_HASH)
    result = builder.build(events, (participant,), _envelope())
    return tuple(t for t in result.timelines if t.view is TimelineView.ENTITY)


def test_the_happy_path_derives_a_bootstrap_and_two_observed_states() -> None:
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

    engine = StateEngine((_lifecycle(),), (), facts.ONTOLOGY_HASH)
    result = engine.derive(
        _timelines_for((e1, e2), participant), (participant,), (e1, e2), _envelope()
    )

    names = [state.state_name for state in result.states]
    assert names == ["OPEN", "MIDDLE", "CLOSED"]
    assert result.states[0].provenance_class is ProvenanceClass.ASSUMED  # bootstrap
    assert result.states[1].provenance_class is ProvenanceClass.OBSERVED
    assert result.states[2].provenance_class is ProvenanceClass.OBSERVED
    assert len(result.transitions) == 2
    assert result.report.illegal_transitions == ()
    assert result.report.assumed_initial_states == 0  # OPEN is the declared initial state


def test_a_mid_lifecycle_first_event_is_counted_as_assumed() -> None:
    """The first observed event is STAGE_TWO -- MIDDLE was never directly witnessed."""
    participant = facts.entity("p1", citation=facts.evidence_record("r0"))
    e2 = facts.event(
        "STAGE_TWO",
        facts.interval(0),
        citation=facts.evidence_record("r2"),
        participants=(participant,),
    )

    engine = StateEngine((_lifecycle(),), (), facts.ONTOLOGY_HASH)
    result = engine.derive(_timelines_for((e2,), participant), (participant,), (e2,), _envelope())

    assert [state.state_name for state in result.states] == ["MIDDLE", "CLOSED"]
    assert result.states[0].provenance_class is ProvenanceClass.ASSUMED
    assert result.report.assumed_initial_states == 1


def test_an_illegal_transition_is_a_hard_error_finding_not_a_crash() -> None:
    """STAGE_ONE fires twice -- the lifecycle has no transition out of MIDDLE for it."""
    participant = facts.entity("p1", citation=facts.evidence_record("r0"))
    e1 = facts.event(
        "STAGE_ONE",
        facts.interval(0),
        citation=facts.evidence_record("r1"),
        participants=(participant,),
    )
    e1_again = facts.event(
        "STAGE_ONE",
        facts.interval(1),
        citation=facts.evidence_record("r1b"),
        participants=(participant,),
    )
    other = facts.entity("p2", citation=facts.evidence_record("r0b"))
    e1_other = facts.event(
        "STAGE_ONE", facts.interval(0), citation=facts.evidence_record("r2"), participants=(other,)
    )

    events = (e1, e1_again, e1_other)
    entities = (participant, other)
    builder = TimelineBuilder((), facts.ONTOLOGY_HASH)
    timelines = tuple(
        t
        for t in builder.build(events, entities, _envelope()).timelines
        if t.view is TimelineView.ENTITY
    )

    engine = StateEngine((_lifecycle(),), (), facts.ONTOLOGY_HASH)
    result = engine.derive(timelines, entities, events, _envelope())

    assert len(result.report.illegal_transitions) == 1
    finding = result.report.illegal_transitions[0]
    assert finding.offending_event_id == e1_again.event_id
    assert finding.attempted_from_state == "MIDDLE"
    assert finding.declared_from_states == ("OPEN",)
    # replay stopped at the offending event -- only the bootstrap + first legal state exist.
    assert [s.entity_id for s in result.states].count(participant.entity_id) == 2
    # The other, legal entity's replay is unaffected by the first entity's illegal event.
    assert any(state.entity_id == other.entity_id for state in result.states)
