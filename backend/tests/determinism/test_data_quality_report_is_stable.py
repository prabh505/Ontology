"""Determinism (`CONVENTIONS.md` §11): same input, same seed, same ontology hash => same bytes.

Module 1's Definition-of-Done determinism test. It asserts three separate things, because
they can fail independently:

  * the report's canonical JSON is byte-identical across two imports;
  * `report_sha256` is therefore identical;
  * the clean layer and the quarantine are byte-identical too.

The third matters most. A report that is stable while the data layer beneath it is not would
be a determinism guarantee that holds exactly where it is being measured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from causalog import ENGINE_VERSION
from causalog.core.serialization import to_canonical_json
from causalog.ingestion.data_adapter import (
    CLEAN_LAYER_FILES,
    import_dataset,
    render_markdown,
    report_sha256,
)
from causalog.persistence.sources.delimited import DelimitedTextSource
from tests.fixtures.dataco import SAMPLE_CSV

pytestmark = pytest.mark.determinism

DATASET_VERSION = "sample@0000000000000000+map0000000000000000"


def _import(
    sample_probe: Any,
    mapping: Any,
    pack: Any,
    coverage: Any,
    clean_layer: Any,
) -> Any:
    source = DelimitedTextSource(SAMPLE_CSV, DATASET_VERSION, probe=sample_probe, batch_size=64)
    return import_dataset(
        source,
        mapping,
        pack,
        coverage,
        dataset_id="sample",
        source_url="fixture",
        mapping_hash="map:0000000000000000",
        ontology_hash="ont:0000000000000000",
        engine_version=ENGINE_VERSION,
        clean_layer=clean_layer,
    )


def test_two_imports_of_one_file_produce_identical_bytes(
    sample_probe: Any,
    dataco_mapping: Any,
    dataco_pack: Any,
    dataco_coverage: Any,
    tmp_path: Path,
) -> None:
    first = _import(sample_probe, dataco_mapping, dataco_pack, dataco_coverage, tmp_path / "a")
    second = _import(sample_probe, dataco_mapping, dataco_pack, dataco_coverage, tmp_path / "b")

    assert to_canonical_json(first.report) == to_canonical_json(second.report)
    assert report_sha256(first.report) == report_sha256(second.report)
    assert render_markdown(first.report) == render_markdown(second.report)

    for name in CLEAN_LAYER_FILES:
        left = (tmp_path / "a" / name).read_bytes()
        right = (tmp_path / "b" / name).read_bytes()
        assert left == right, f"{name} differs between two imports of one file"


def test_a_different_batch_size_does_not_change_the_answer(
    sample_probe: Any, dataco_mapping: Any, dataco_pack: Any, dataco_coverage: Any
) -> None:
    """Batching is a memory decision. It must not be an output decision."""
    reports = []
    for batch_size in (7, 64, 100_000):
        source = DelimitedTextSource(
            SAMPLE_CSV, DATASET_VERSION, probe=sample_probe, batch_size=batch_size
        )
        reports.append(
            report_sha256(
                import_dataset(
                    source,
                    dataco_mapping,
                    dataco_pack,
                    dataco_coverage,
                    dataset_id="sample",
                    source_url="fixture",
                    mapping_hash="map:0000000000000000",
                    ontology_hash="ont:0000000000000000",
                    engine_version=ENGINE_VERSION,
                ).report
            )
        )
    assert len(set(reports)) == 1, f"batch size changed the report: {reports}"


def test_the_evidence_record_id_is_a_function_of_the_pin_and_the_row(sample_probe: Any) -> None:
    """Content addressing: the same row of the same pinned file always cites identically."""
    left = DelimitedTextSource(SAMPLE_CSV, DATASET_VERSION, probe=sample_probe)
    right = DelimitedTextSource(SAMPLE_CSV, DATASET_VERSION, probe=sample_probe, batch_size=3)
    assert left.evidence_record_id(42) == right.evidence_record_id(42)
    assert left.evidence_record_id(42) != left.evidence_record_id(43)

    other_pin = DelimitedTextSource(SAMPLE_CSV, "other@1111111111111111+map1", probe=sample_probe)
    assert other_pin.evidence_record_id(42) != left.evidence_record_id(42)
