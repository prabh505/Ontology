"""The whole reference dataset through modules 3 and 4, measured rather than estimated.

Two things this file exists to produce, and neither of them is a pass/fail on quality.

**The measurement.** `prd.md` §55 wants a large dataset loaded inside a budget, and OQ-018
records that nobody has ruled on what "dataset loading" counts -- source records, or the
events they expand into, which differ by more than an order of magnitude. Both readings are
printed on every run, as module 1's own budget test does, so the ruling can be made against
numbers instead of against an argument.

**The honest report.** The counts by type, by provenance class and by timestamp precision
over the real file, and the process-coverage gaps. These bound every causal claim anything
downstream can make, and the point of measuring them here is that they are properties of the
SOURCE, not defects to tune away.

Marked `slow`: it reads a 95 MB file twice and expands it. `make test-fast` skips it.
"""

from __future__ import annotations

import json
import resource
import sys
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest

from causalog.core.temporal import Precision
from causalog.extraction.event_generator import render_markdown as render_quality
from causalog.ingestion.schema_mapper import MappedRecordBatch, apply_mapping, mapping_hash
from extraction_harness import REPO_ROOT, Harness, envelope_for, harness_for

pytestmark = pytest.mark.slow

CLEAN_LAYERS = REPO_ROOT / "datasets" / "clean"

#: Records per mapped batch. Bounded so peak memory is a function of the batch, never of the
#: file; the determinism test separately asserts the size cannot change the output.
BATCH_SIZE = 20_000


def _peak_megabytes() -> float:
    """Return this process's peak resident set, in megabytes.

    Reported because it is the binding constraint, not the wall clock. `ru_maxrss` is bytes
    on Darwin and kilobytes on Linux; the two are distinguished rather than assumed, because
    a figure that is wrong by 1024 in a committed measurement is worse than no figure.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return peak / divisor


def _clean_layer(dataset_version: str) -> Path:
    return CLEAN_LAYERS / dataset_version / "records.jsonl"


def _read_batches(
    path: Path, harness: Harness, dataset_version: str
) -> Iterator[MappedRecordBatch]:
    """Yield mapped batches straight from module 1's clean layer.

    The clean layer already holds the output of the transform chains, so they are NOT
    re-applied here: a chain containing a parse is not idempotent in its receipts, and
    re-running it would double-count changes against a ledger this module does not own.
    """
    records = []
    index = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            records.append(
                apply_mapping(
                    payload["values"],
                    payload["evidence_record_id"],
                    payload["row_number"],
                    harness.plan,
                )
            )
            if len(records) >= BATCH_SIZE:
                yield MappedRecordBatch(
                    dataset_version=dataset_version,
                    ontology_hash=harness.ontology_hash,
                    batch_index=index,
                    records=tuple(records),
                )
                records = []
                index += 1
    if records:
        yield MappedRecordBatch(
            dataset_version=dataset_version,
            ontology_hash=harness.ontology_hash,
            batch_index=index,
            records=tuple(records),
        )


def test_the_full_reference_expansion_is_measured_and_reported() -> None:
    harness = harness_for()
    pin = json.loads((REPO_ROOT / "datasets" / "dataco.pin.json").read_text(encoding="utf-8"))
    dataset_version = pin["payload"]["dataset_version"]
    assert mapping_hash(harness.mapping) == pin["payload"]["mapping_hash"], (
        "the pin was written under a different mapping. Re-run `make import DATASET=dataco` "
        "-- the mapping participates in dataset_version (ADR-0035) and a stale pin would "
        "make this measurement describe a run nobody can reproduce."
    )
    layer = _clean_layer(dataset_version)
    if not layer.exists():
        pytest.skip(
            f"no clean layer at {layer}; run `make import DATASET=dataco` first. This is a "
            "measurement of the reference file, and it is skipped rather than faked."
        )

    envelope = envelope_for(harness, dataset_version)

    started = time.monotonic()
    extraction = harness.extract(_read_batches(layer, harness, dataset_version), envelope)
    extraction_seconds = time.monotonic() - started

    anchor_types = {item.anchor_entity_type for item in harness.pack.process_definitions}
    anchors = frozenset(
        entity.entity_id for entity in extraction.entities if entity.entity_type in anchor_types
    )
    from causalog.extraction.event_generator import EventGenerator

    generator = EventGenerator(harness.pack, harness.mapping, harness.ontology_hash)
    started = time.monotonic()
    streamed = generator.stream(
        lambda: _read_batches(layer, harness, dataset_version),
        anchors,
        extraction.entity_ids(),
        envelope,
        conflict_policy=extraction.report.conflict_policy.value,
    )
    # STREAMED, not collected, and that is the measurement rather than an optimisation.
    # Collecting the reference expansion as `Event` models exhausted an 8 GB machine and
    # drove it into swap; the run was still going after fifty minutes with six minutes of
    # CPU behind it. Holding the log is affordable exactly where a report about it is least
    # needed. What is counted here is folded as the events go past.
    counted: Counter[str] = Counter()
    unique_identifiers: set[str] = set()
    for event in streamed.events:
        counted[event.event_type] += 1
        unique_identifiers.add(event.event_id)
    report = streamed.report()
    generation_seconds = time.monotonic() - started
    precision = dict(report.by_precision)
    print()
    print("=" * 78)
    print("FULL REFERENCE EXPANSION -- MEASURED, NOT ESTIMATED")
    print("=" * 78)
    print(f"dataset_version      : {dataset_version}")
    print(f"ontology_hash        : {harness.ontology_hash}")
    print()
    print("OQ-018: the two readings of what 'dataset loading' counts, both reported.")
    print(f"  source records     : {report.records_read:,}")
    print(f"  materialised events: {report.events_total:,}")
    print(f"  entities           : {len(extraction.entities):,}")
    print(f"  expansion factor   : {report.events_total / max(report.records_read, 1):.2f}x")
    print()
    print(f"  peak resident set  : {_peak_megabytes():8.0f} MB")
    print()
    print(f"  entity extraction  : {extraction_seconds:8.1f}s")
    print(f"  event generation   : {generation_seconds:8.1f}s  (two passes, streamed)")
    print(f"  total              : {extraction_seconds + generation_seconds:8.1f}s")
    print()
    print("Events by provenance class:")
    for name, count in report.by_provenance_class:
        print(f"  {name:<12} {count:>10,}  {count / report.events_total:7.2%}")
    print()
    print("Events by timestamp precision:")
    for name, count in report.by_precision:
        print(f"  {name:<12} {count:>10,}  {count / report.events_total:7.2%}")
    print()
    print("Events by type:")
    for tally in report.by_event_type:
        print(
            f"  {tally.event_type:<30} {tally.events:>10,}  "
            f"{tally.records_witnessing:>10,} records  "
            f"{'rule' if tally.has_emission_rule else 'NO RULE':>7}"
        )
    print()
    for coverage in report.process_coverage:
        print(f"Process coverage -- {coverage.process_id} ({coverage.anchors:,} instances):")
        for step in coverage.steps:
            marker = "  SYSTEMATIC" if step.systematically_missing else ""
            print(
                f"  {step.event_type:<30} expecting {step.anchors_expecting:>8,}  "
                f"missing {step.anchors_missing:>8,}  {step.miss_rate:7.2%}{marker}"
            )
    print("=" * 78)

    # Assertions are about SHAPE, never about quality: there is no causal ground truth in
    # this dataset (CONVENTIONS.md §14) and no test here may claim otherwise.
    assert report.records_read == pin["payload"]["row_count"]
    assert report.events_total > 0
    assert sum(count for _name, count in report.by_provenance_class) == report.events_total
    assert sum(count for _name, count in report.by_precision) == report.events_total
    assert (
        precision.get(Precision.EXACT.value, 0) == 0
    ), "no emitted interval may claim EXACT precision (CONVENTIONS.md §10)"
    assert sum(counted.values()) == report.events_total
    assert len(unique_identifiers) == report.events_total, (
        "two events shared a content address, which means two different claims about what "
        "happened were merged into one (CONVENTIONS.md §9)"
    )
    rendered = render_quality(report)
    assert "Event Quality Report" in rendered
