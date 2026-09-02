"""LAW-EVENT: the boundary moves to module 4's output, and this is where it is checked.

`test_no_row_escapes_ingestion.py` bans `RawRecord` above L2. Modules 3 and 4 introduce a
second row-shaped type -- `MappedRecord`, a row re-expressed in ontology vocabulary -- and
it is still a row. `docs/architecture.md` §2 names module 4 THE LAW-EVENT boundary: nothing
above `extraction` may hold either type, and no public signature of `extraction` may return
one.

The type ban is the half a lint cannot do. Forbidden edge F7 bans a tabular IMPORT above
rank 3; a module can hold a record without importing `csv`.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import causalog
from causalog.core.ports.source import RawRecord, RawRecordBatch
from causalog.ingestion.schema_mapper.apply import MappedRecord, MappedRecordBatch, RecordView

pytestmark = pytest.mark.law

PACKAGE_ROOT = Path(causalog.__file__).resolve().parent

#: Packages that may name a mapped record. `ingestion` DECLARES it; `extraction` is its one
#: consumer, and it is the last. `orchestration` is permitted to WIRE the two together, and
#: holds no reasoning of its own.
PERMITTED = ("core", "ingestion", "extraction", "persistence", "orchestration")

FORBIDDEN_NAMES = (
    RawRecord.__name__,
    RawRecordBatch.__name__,
    MappedRecord.__name__,
    MappedRecordBatch.__name__,
    # `RecordView` is a mapped record indexed for lookup. It is still a record, and a name
    # that escaped this list because it was added later is exactly how a boundary erodes.
    RecordView.__name__,
)


def _python_files_above_l3() -> list[Path]:
    found = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path.relative_to(PACKAGE_ROOT).as_posix().split("/")[0] in PERMITTED:
            continue
        found.append(path)
    return found


def test_the_scan_covers_something() -> None:
    """Zero files scanned reads identically to zero violations found (DEF-0001)."""
    assert _python_files_above_l3(), "this law test scanned no file, which reads as passing"


def test_no_package_above_l3_names_a_record_of_any_kind() -> None:
    offenders = []
    for path in _python_files_above_l3():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(PACKAGE_ROOT)}: {name}" for name in FORBIDDEN_NAMES if name in text
        )
    assert not offenders, (
        "LAW-EVENT: below the extraction boundary the engine computes over Event, Entity, "
        f"State, Transition and Relationship -- never over a record. Found: {offenders}"
    )


def test_the_event_generator_returns_no_record_across_its_public_surface() -> None:
    """Module 4's output is events and a report, never the records it read."""
    from causalog.extraction.event_generator import EventGenerator

    annotation = str(inspect.signature(EventGenerator.generate).return_annotation)
    for name in FORBIDDEN_NAMES:
        assert name not in annotation


def test_the_entity_extractor_returns_no_record_across_its_public_surface() -> None:
    from causalog.extraction.entity_extractor import EntityExtractor

    annotation = str(inspect.signature(EntityExtractor.extract).return_annotation)
    for name in FORBIDDEN_NAMES:
        assert name not in annotation


def test_no_emitted_artifact_carries_a_source_column_name() -> None:
    """The output half of the boundary, checked against real output.

    An `Event` or an `Entity` naming a source column would carry the dataset's vocabulary
    past the boundary in DATA rather than in a signature, which no import lint can see.
    """
    from extraction_harness import build_batches, envelope_for, harness_for
    from fixtures.dataco.expansion import GROUND_TRUTH_DATASET_VERSION, rows

    harness = harness_for()
    columns = {binding.column for binding in harness.mapping.column_bindings}
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    generation = harness.generate(batches, extraction, envelope)

    assert generation.events and extraction.entities
    for event in generation.events:
        keys = {name for name, _ in event.changed_attributes} | {name for name, _ in event.metadata}
        assert not keys & columns, f"{event.event_type} carries a source column name"
    for entity in extraction.entities:
        assert not {name for name, _ in entity.attributes} & columns
