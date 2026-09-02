"""Uncertain-timestamp handling: a tied boundary is widened and flagged, never fabricated.

Synthetic and domain-neutral (`CONVENTIONS.md` §14).
"""

from __future__ import annotations

from causalog.core.ontology_view import LifecycleTransitionView, LifecycleView
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.temporal import Precision
from causalog.core.types import TimelineView
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


def test_a_tied_boundary_widens_the_state_and_is_flagged_assumed_not_fabricated() -> None:
    participant = facts.entity("p1", citation=facts.evidence_record("r0"))
    tied = facts.interval(0, precision=Precision.DAY)  # both events land on the same day
    e1 = facts.event(
        "STAGE_ONE", tied, citation=facts.evidence_record("r1"), participants=(participant,)
    )
    e2 = facts.event(
        "STAGE_TWO", tied, citation=facts.evidence_record("r2"), participants=(participant,)
    )

    builder = TimelineBuilder((), facts.ONTOLOGY_HASH)
    timelines = tuple(
        t
        for t in builder.build((e1, e2), (participant,), _envelope()).timelines
        if t.view is TimelineView.ENTITY
    )
    engine = StateEngine((_lifecycle(),), (), facts.ONTOLOGY_HASH)
    result = engine.derive(timelines, (participant,), (e1, e2), _envelope())

    # The MIDDLE state's outer boundary is uncertain -- e1 and e2 tie, so which of them
    # truly happened first (and therefore exactly when MIDDLE stopped holding) is not
    # something the data can answer.
    middle_states = [s for s in result.states if s.state_name == "MIDDLE"]
    assert len(middle_states) == 1
    assert middle_states[0].held_over.provenance is ProvenanceClass.ASSUMED
    # The state's own existence is still OBSERVED -- only the boundary timing is uncertain.
    assert middle_states[0].provenance_class is ProvenanceClass.OBSERVED
    assert result.report.uncertain_boundary_states == 1
