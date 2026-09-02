"""`CONVENTIONS.md` §11: same input, same seed, same ontology hash => byte-identical output.

A Definition-of-Done item for every module. Covers `Timeline`, `State`, `Transition`, and
both quality reports (models and rendered markdown, not just the models -- a report that
reordered a table between runs would be a determinism defect a model-level comparison alone
would not see).
"""

from __future__ import annotations

import pytest

from causalog.core.ontology_view import (
    LifecycleTransitionView,
    LifecycleView,
    ProcessDefinitionView,
)
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.serialization import to_canonical_json
from causalog.core.types import TimelineView
from causalog.graph_engine.state_engine import StateEngine
from causalog.graph_engine.state_engine import render_markdown as render_state_quality
from causalog.graph_engine.timeline_builder import TimelineBuilder
from causalog.graph_engine.timeline_builder import render_markdown as render_timeline_quality
from tests.fixtures import facts

pytestmark = pytest.mark.determinism


def _process_definition() -> ProcessDefinitionView:
    return ProcessDefinitionView(
        id="STAGE_FLOW",
        anchor_entity_type="PARTICIPANT",
        canonical_sequence=("STAGE_ONE", "STAGE_TWO", "STAGE_THREE"),
    )


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


def _run() -> dict[str, object]:
    p1 = facts.entity("p1", citation=facts.evidence_record("r0a"))
    p2 = facts.entity("p2", citation=facts.evidence_record("r0b"))
    tied = facts.interval(0)  # p2's two events tie -- exercises the ASSUMED tie-break path
    events = (
        facts.event(
            "STAGE_ONE", facts.interval(0), citation=facts.evidence_record("r1"), participants=(p1,)
        ),
        facts.event(
            "STAGE_TWO", facts.interval(1), citation=facts.evidence_record("r2"), participants=(p1,)
        ),
        facts.event(
            "STAGE_THREE",
            facts.interval(2),
            citation=facts.evidence_record("r3"),
            participants=(p1,),
        ),
        facts.event("STAGE_ONE", tied, citation=facts.evidence_record("r4"), participants=(p2,)),
        facts.event("STAGE_TWO", tied, citation=facts.evidence_record("r5"), participants=(p2,)),
    )
    entities = (p1, p2)
    envelope = _envelope()

    timeline_builder = TimelineBuilder((_process_definition(),), facts.ONTOLOGY_HASH)
    timeline_result = timeline_builder.build(events, entities, envelope)

    state_engine = StateEngine((_lifecycle(),), (), facts.ONTOLOGY_HASH)
    entity_timelines = tuple(t for t in timeline_result.timelines if t.view is TimelineView.ENTITY)
    state_result = state_engine.derive(entity_timelines, entities, events, envelope)

    return {
        "timelines": tuple(to_canonical_json(item) for item in timeline_result.timelines),
        "timeline_quality": to_canonical_json(timeline_result.report),
        "timeline_quality_markdown": render_timeline_quality(timeline_result.report),
        "states": tuple(to_canonical_json(item) for item in state_result.states),
        "transitions": tuple(to_canonical_json(item) for item in state_result.transitions),
        "state_quality": to_canonical_json(state_result.report),
        "state_quality_markdown": render_state_quality(state_result.report),
    }


def test_two_runs_over_one_input_produce_identical_artifacts() -> None:
    first = _run()
    second = _run()
    assert first == second


def test_the_rendered_reports_are_free_of_anything_ambient() -> None:
    result = _run()
    for rendered in (result["timeline_quality_markdown"], result["state_quality_markdown"]):
        assert "/Users/" not in rendered
        assert "/home/" not in rendered
