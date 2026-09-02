"""Golden timelines: hand-built cases asserted against exact expected content.

Synthetic and domain-neutral (`CONVENTIONS.md` §14): the process definition and its steps
are named `STAGE_ONE`/`STAGE_TWO`/`STAGE_THREE`, matching `tests/fixtures/facts.py`'s own
vocabulary rather than any real domain.
"""

from __future__ import annotations

from causalog.core.ontology_view import ProcessDefinitionView
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.temporal import Precision
from causalog.core.types import Entity, TimelineEntryKind, TimelineView
from causalog.graph_engine.timeline_builder import TimelineBuilder
from tests.fixtures import facts


def _process_definition() -> ProcessDefinitionView:
    return ProcessDefinitionView(
        id="STAGE_FLOW",
        anchor_entity_type="PARTICIPANT",
        canonical_sequence=("STAGE_ONE", "STAGE_TWO", "STAGE_THREE"),
    )


def _participant() -> Entity:
    return facts.entity("p1", citation=facts.evidence_record("r0"))


def test_the_happy_path_produces_one_conformant_timeline() -> None:
    participant = _participant()
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
    e3 = facts.event(
        "STAGE_THREE",
        facts.interval(2),
        citation=facts.evidence_record("r3"),
        participants=(participant,),
    )

    builder = TimelineBuilder((_process_definition(),), facts.ONTOLOGY_HASH)
    result = builder.build((e1, e2, e3), (participant,), _envelope())

    instance_timelines = [t for t in result.timelines if t.view is TimelineView.PROCESS_INSTANCE]
    assert len(instance_timelines) == 1
    timeline = instance_timelines[0]
    assert [entry.event_id for entry in timeline.entries] == [
        e1.event_id,
        e2.event_id,
        e3.event_id,
    ]
    assert all(entry.kind is TimelineEntryKind.EVENT for entry in timeline.entries)

    report = result.report
    assert report.per_process_definition[0].gap_witnessable == 0
    assert report.per_process_definition[0].gap_unwitnessable == 0
    assert report.per_process_definition[0].sequence_violations == 0
    assert report.per_process_definition[0].unterminated_instances == 0
    assert report.per_process_definition[0].conformance_scores == (1.0,)


def test_a_missing_step_produces_an_explicit_gap_never_bridged() -> None:
    participant = _participant()
    e1 = facts.event(
        "STAGE_ONE",
        facts.interval(0),
        citation=facts.evidence_record("r1"),
        participants=(participant,),
    )
    e3 = facts.event(
        "STAGE_THREE",
        facts.interval(2),
        citation=facts.evidence_record("r3"),
        participants=(participant,),
    )

    builder = TimelineBuilder((_process_definition(),), facts.ONTOLOGY_HASH)
    result = builder.build((e1, e3), (participant,), _envelope())

    instance = next(t for t in result.timelines if t.view is TimelineView.PROCESS_INSTANCE)
    gaps = [entry for entry in instance.entries if entry.kind is TimelineEntryKind.GAP]
    assert len(gaps) == 1
    assert gaps[0].expected_event_type == "STAGE_TWO"
    # Never given a fabricated timestamp.
    assert gaps[0].occurred_at is None
    # STAGE_TWO is produced nowhere in this run's event set -- unwitnessable, not just
    # missing on this instance.
    assert gaps[0].step_witnessable is False
    assert result.report.per_process_definition[0].gap_unwitnessable == 1
    assert result.report.per_process_definition[0].unterminated_instances == 0


def test_a_witnessable_gap_is_distinguished_from_an_unwitnessable_one() -> None:
    """STAGE_TWO fires for a different instance in the same run -- it IS producible."""
    p1 = facts.entity("p1", citation=facts.evidence_record("r0"))
    p2 = facts.entity("p2", citation=facts.evidence_record("r0b"))
    e1 = facts.event(
        "STAGE_ONE", facts.interval(0), citation=facts.evidence_record("r1"), participants=(p1,)
    )
    e3 = facts.event(
        "STAGE_THREE", facts.interval(2), citation=facts.evidence_record("r3"), participants=(p1,)
    )
    other_e1 = facts.event(
        "STAGE_ONE", facts.interval(0), citation=facts.evidence_record("r4"), participants=(p2,)
    )
    other_e2 = facts.event(
        "STAGE_TWO", facts.interval(1), citation=facts.evidence_record("r5"), participants=(p2,)
    )

    builder = TimelineBuilder((_process_definition(),), facts.ONTOLOGY_HASH)
    result = builder.build((e1, e3, other_e1, other_e2), (p1, p2), _envelope())

    p1_timeline = next(
        t
        for t in result.timelines
        if t.view is TimelineView.PROCESS_INSTANCE and t.subject_entity_ids == (p1.entity_id,)
    )
    gap = next(entry for entry in p1_timeline.entries if entry.kind is TimelineEntryKind.GAP)
    assert gap.step_witnessable is True


def test_out_of_sequence_events_are_flagged_never_resorted() -> None:
    participant = _participant()
    e1 = facts.event(
        "STAGE_ONE",
        facts.interval(0),
        citation=facts.evidence_record("r1"),
        participants=(participant,),
    )
    # STAGE_THREE observed BEFORE STAGE_TWO.
    e3 = facts.event(
        "STAGE_THREE",
        facts.interval(1),
        citation=facts.evidence_record("r3"),
        participants=(participant,),
    )
    e2 = facts.event(
        "STAGE_TWO",
        facts.interval(2),
        citation=facts.evidence_record("r2"),
        participants=(participant,),
    )

    builder = TimelineBuilder((_process_definition(),), facts.ONTOLOGY_HASH)
    result = builder.build((e1, e2, e3), (participant,), _envelope())

    instance = next(t for t in result.timelines if t.view is TimelineView.PROCESS_INSTANCE)
    # Observed (temporal) order is kept -- e3 sorts before e2, never corrected.
    assert [
        entry.event_id for entry in instance.entries if entry.kind is TimelineEntryKind.EVENT
    ] == [
        e1.event_id,
        e3.event_id,
        e2.event_id,
    ]
    assert len(result.report.violations) == 1
    violation = result.report.violations[0]
    assert violation.earlier_event_id == e3.event_id
    assert violation.later_event_id == e2.event_id


def test_identical_timestamps_are_tie_broken_deterministically_and_marked_assumed() -> None:
    participant = _participant()
    tied_interval = facts.interval(0, precision=Precision.DAY)
    e_a = facts.event(
        "STAGE_ONE",
        tied_interval,
        citation=facts.evidence_record("ra"),
        participants=(participant,),
    )
    e_b = facts.event(
        "STAGE_TWO",
        tied_interval,
        citation=facts.evidence_record("rb"),
        participants=(participant,),
    )

    builder = TimelineBuilder((), facts.ONTOLOGY_HASH)
    result = builder.build((e_a, e_b), (participant,), _envelope())

    entity_timeline = next(t for t in result.timelines if t.view is TimelineView.ENTITY)
    ordered_ids = [entry.event_id for entry in entity_timeline.entries]
    # Deterministic: sorted by event_id, the documented tie-break.
    assert ordered_ids == sorted([e_a.event_id, e_b.event_id])
    second_entry = entity_timeline.entries[1]
    assert second_entry.sequence_provenance is ProvenanceClass.ASSUMED
    assert result.report.uncertain_sequence_timelines == 1

    # Rerunning the same input reaches the same tie-broken order -- determinism.
    result_again = builder.build((e_a, e_b), (participant,), _envelope())
    entity_timeline_again = next(t for t in result_again.timelines if t.view is TimelineView.ENTITY)
    assert [e.event_id for e in entity_timeline_again.entries] == ordered_ids


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
