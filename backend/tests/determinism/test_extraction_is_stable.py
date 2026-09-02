"""`CONVENTIONS.md` §11: same input, same seed, same ontology hash => byte-identical output.

A Definition-of-Done item for every module, and for these two it covers four artifacts --
the entities, their attribute history, the events, and both reports. Byte-identical means
the rendered markdown as well as the models: a report that reordered a table between runs
would be a determinism defect that a model-level comparison would not see.

Batch size is varied deliberately. Batching is a partitioning of the input and must never be
a change to it; an accumulator that depended on where a batch boundary fell would produce
identical models and a different citation sequence, which is the shape of defect this
repository has already hit once in a bulk loader (risk R-18).
"""

from __future__ import annotations

import pytest

from causalog.core.serialization import to_canonical_json
from causalog.extraction.entity_extractor import render_markdown as render_reconciliation
from causalog.extraction.event_generator import MissingEventPolicy
from causalog.extraction.event_generator import render_markdown as render_quality
from extraction_harness import build_batches, envelope_for, harness_for
from fixtures.dataco.expansion import GROUND_TRUTH_DATASET_VERSION, rows

pytestmark = pytest.mark.determinism


def _run(
    batch_size: int, policy: MissingEventPolicy = MissingEventPolicy.RECORD_GAP
) -> dict[str, object]:
    harness = harness_for()
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION, batch_size=batch_size)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    generation = harness.generate(batches, extraction, envelope, policy=policy)
    return {
        "entities": tuple(to_canonical_json(item) for item in extraction.entities),
        "histories": tuple(to_canonical_json(item) for item in extraction.histories),
        "events": tuple(to_canonical_json(item) for item in generation.events),
        "reconciliation": render_reconciliation(extraction.report),
        "quality": render_quality(generation.report),
    }


def test_two_runs_over_one_input_produce_identical_artifacts() -> None:
    first = _run(batch_size=1000)
    second = _run(batch_size=1000)
    assert first == second


@pytest.mark.parametrize("batch_size", [1, 3, 7, 1000])
def test_batching_partitions_the_input_and_never_changes_it(batch_size: int) -> None:
    assert _run(batch_size=batch_size) == _run(batch_size=1000)


def test_the_rendered_reports_are_free_of_anything_ambient() -> None:
    """No wall clock, no host name, no absolute path: all three would diff between runs."""
    rendered = _run(batch_size=1000)
    for text in (rendered["reconciliation"], rendered["quality"]):
        assert "/Users/" not in text
        assert "/home/" not in text
        assert "20" + "26-" not in text, "a rendered report must carry no wall-clock date"


def test_the_missing_event_policy_changes_the_output_and_says_so() -> None:
    """Determinism is per-configuration. Two policies must differ, and both must be stable."""
    gaps = _run(batch_size=1000, policy=MissingEventPolicy.RECORD_GAP)
    markers = _run(batch_size=1000, policy=MissingEventPolicy.EMIT_GAP_MARKER)
    assert gaps["events"] != markers["events"]
    assert gaps == _run(batch_size=1000, policy=MissingEventPolicy.RECORD_GAP)
    assert markers == _run(batch_size=1000, policy=MissingEventPolicy.EMIT_GAP_MARKER)


def test_events_are_emitted_in_the_canonical_sequence() -> None:
    """`(t_earliest, t_latest, event_id)`. A rendering sequence, never a precedence claim."""
    harness = harness_for()
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    generation = harness.generate(batches, extraction, envelope)
    keys = [(*event.occurred_at.sort_key(), event.event_id) for event in generation.events]
    assert keys == sorted(keys)


def test_entities_are_emitted_sequenced_by_identifier() -> None:
    harness = harness_for()
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    identifiers = [entity.entity_id for entity in extraction.entities]
    assert identifiers == sorted(identifiers)
