"""LAW-TIME for adjacency: a timeline may never claim `OBSERVED` where verdict says `UNDETERMINED`.

`sequence_provenance` on a `TimelineEntry` is Timeline Builder's own adjacency claim, not a
property `causalog.core.temporal.verdict` decides for it -- so this law is checked by
re-deriving the verdict for every adjacent pair and comparing, over a spread of synthetic
cases, rather than by scanning source text (the earlier boundaries in this repository are
import-shaped; this one is a correctness property of running code, so it is checked by
running it).
"""

from __future__ import annotations

import pytest

from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.temporal import TemporalVerdict, verdict
from causalog.core.types import TimelineEntryKind
from causalog.graph_engine.timeline_builder import TimelineBuilder
from tests.fixtures import facts

pytestmark = pytest.mark.law


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


_CASES = (
    # (offset_days, span_days) pairs for two events, and whether they are expected to
    # produce a verdict of CERTAIN between them.
    ((0, 0), (1, 0)),  # clearly separated
    ((0, 0), (0, 0)),  # identical instants -- tie
    ((0, 2), (1, 2)),  # overlapping spans
    ((0, 0), (5, 0)),  # widely separated
)


@pytest.mark.parametrize("first, second", _CASES)
def test_sequence_provenance_never_exceeds_what_verdict_supports(
    first: tuple[int, int], second: tuple[int, int]
) -> None:
    participant = facts.entity("p1", citation=facts.evidence_record("r0"))
    e1 = facts.event(
        "STAGE_ONE",
        facts.interval(first[0], span_days=first[1]),
        citation=facts.evidence_record("r1"),
        participants=(participant,),
    )
    e2 = facts.event(
        "STAGE_TWO",
        facts.interval(second[0], span_days=second[1]),
        citation=facts.evidence_record("r2"),
        participants=(participant,),
    )

    builder = TimelineBuilder((), facts.ONTOLOGY_HASH)
    result = builder.build((e1, e2), (participant,), _envelope())
    timeline = result.timelines[0]
    event_entries = [entry for entry in timeline.entries if entry.kind is TimelineEntryKind.EVENT]
    assert len(event_entries) == 2

    events_by_id = {e1.event_id: e1, e2.event_id: e2}
    earlier = events_by_id[event_entries[0].event_id]
    later = events_by_id[event_entries[1].event_id]
    real_verdict = verdict(earlier.occurred_at, later.occurred_at)

    claimed = event_entries[1].sequence_provenance
    if real_verdict is not TemporalVerdict.CERTAIN:
        assert claimed is ProvenanceClass.ASSUMED, (
            f"verdict={real_verdict} but sequence_provenance={claimed}: the timeline "
            "claimed more certainty about adjacency than the data supports."
        )
