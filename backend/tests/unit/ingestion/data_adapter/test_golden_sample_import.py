"""Golden-file test: the full import over the committed sample, against a pinned report.

The sample is the head of the real distribution plus seven hand-planted defect rows, kept in
`cp1252` so the encoding probe is exercised rather than assumed. The assertions are on the
report's SHAPE and its counts, and on the digest of its canonical bytes -- which is what
makes an unintended change to any measurement a test failure rather than a discovery.

When this test fails after a deliberate change, regenerate the golden with
`python -m tests.unit.ingestion.data_adapter.test_golden_sample_import --write` and read the
diff before committing it. A golden updated without reading the diff is a golden that
asserts whatever the code now does.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from causalog import ENGINE_VERSION
from causalog.core.serialization import to_canonical_json
from causalog.ingestion.data_adapter import import_dataset, render_markdown, report_sha256
from causalog.ingestion.schema_mapper import SchemaMappingSpec
from causalog.ingestion.schema_mapper.coverage import CoverageReport
from causalog.ontology_runtime.diagnostics import Severity
from causalog.ontology_runtime.dsl import ResolvedPack
from causalog.persistence.sources.delimited import DelimitedTextSource
from tests.fixtures.dataco import PLANTED_DEFECT_ROWS, SAMPLE_ROW_COUNT

GOLDEN = Path(__file__).resolve().parent / "golden_sample_report.json"

SAMPLE_DATASET_VERSION = "sample@0000000000000000+map0000000000000000"


def _run(
    source: DelimitedTextSource,
    mapping: SchemaMappingSpec,
    pack: ResolvedPack,
    coverage: CoverageReport,
    clean_layer: Path | None = None,
) -> object:
    """Import the sample under a fixed dataset_version so the golden is stable."""
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


def _sample_source(sample_probe: object) -> DelimitedTextSource:
    from tests.fixtures.dataco import SAMPLE_CSV

    return DelimitedTextSource(
        SAMPLE_CSV, SAMPLE_DATASET_VERSION, probe=sample_probe, batch_size=64
    )


def test_the_sample_import_matches_the_golden_report(
    sample_probe: Any, dataco_mapping: Any, dataco_pack: Any, dataco_coverage: Any
) -> None:
    result = _run(_sample_source(sample_probe), dataco_mapping, dataco_pack, dataco_coverage)
    actual = json.loads(to_canonical_json(result.report))
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert actual == expected, (
        "The sample import no longer produces the golden report. Read the diff, decide "
        "whether the change is intended, and regenerate with --write if it is."
    )


def test_the_probe_detects_the_single_byte_encoding_rather_than_assuming_it(
    sample_probe: Any,
) -> None:
    assert sample_probe.encoding.chosen == "cp1252"
    assert "utf-8" in sample_probe.encoding.rejected
    assert sample_probe.encoding.first_undecodable_byte_offset is not None


def test_every_row_is_accounted_for(
    sample_probe: Any, dataco_mapping: Any, dataco_pack: Any, dataco_coverage: Any
) -> None:
    report = _run(_sample_source(sample_probe), dataco_mapping, dataco_pack, dataco_coverage).report
    assert report.rows.rows_read == SAMPLE_ROW_COUNT
    assert report.rows.reconciles


def test_each_planted_defect_fires_its_rule(
    sample_probe: Any, dataco_mapping: Any, dataco_pack: Any, dataco_coverage: Any
) -> None:
    """The fixture's whole purpose. A planted defect nothing catches is a rule that is off."""
    report = _run(_sample_source(sample_probe), dataco_mapping, dataco_pack, dataco_coverage).report
    fired = {finding.code for finding in report.findings}
    missing = sorted(set(PLANTED_DEFECT_ROWS) - fired)
    assert not missing, f"planted defects that no rule caught: {missing}"


def test_every_planted_defect_row_is_quarantined_and_none_is_lost(
    sample_probe: Any, dataco_mapping: Any, dataco_pack: Any, dataco_coverage: Any, tmp_path: Path
) -> None:
    result = _run(
        _sample_source(sample_probe),
        dataco_mapping,
        dataco_pack,
        dataco_coverage,
        clean_layer=tmp_path,
    )
    quarantined = set(result.quarantined_row_numbers)
    # The duplicate-identity rule does not quarantine -- it is a WARNING, because which of
    # two conflicting readings is right is not something this layer can know.
    must_quarantine = {
        row for code, row in PLANTED_DEFECT_ROWS.items() if code != "DQ-REF-DUPLICATE-IDENTITY"
    }
    assert must_quarantine <= quarantined

    clean_lines = (tmp_path / "records.jsonl").read_text(encoding="utf-8").splitlines()
    quarantine_lines = (tmp_path / "quarantine.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(clean_lines) + len(quarantine_lines) == SAMPLE_ROW_COUNT
    for line in quarantine_lines:
        payload = json.loads(line)
        assert payload["reasons"], "a quarantined row must carry the codes that put it there"


def test_the_report_names_what_it_did_not_check(
    sample_probe: Any, dataco_mapping: Any, dataco_pack: Any, dataco_coverage: Any
) -> None:
    report = _run(_sample_source(sample_probe), dataco_mapping, dataco_pack, dataco_coverage).report
    assert report.not_checked, (
        "A report that lists only what it looked at reads as a report that looked at "
        "everything (DEF-0001, OQ-014)."
    )
    assert any(finding.severity is Severity.NOT_RUNNABLE for finding in report.coverage.findings)


def test_the_markdown_renders_the_headline_before_the_tables(
    sample_probe: Any, dataco_mapping: Any, dataco_pack: Any, dataco_coverage: Any
) -> None:
    report = _run(_sample_source(sample_probe), dataco_mapping, dataco_pack, dataco_coverage).report
    markdown = render_markdown(report)
    assert markdown.index("## Headline constraints") < markdown.index("## Column profile")
    assert markdown.index("## Headline constraints") < markdown.index("## Findings")


def _write_golden() -> None:
    """Regenerate the golden. Run with `--write`, then READ THE DIFF."""
    from causalog.ingestion.schema_mapper import inspect_mapping
    from causalog.ontology_runtime import load_pack
    from causalog.persistence.sources.delimited import probe_source
    from tests.fixtures.dataco import SAMPLE_CSV

    repo_root = next(
        candidate
        for candidate in Path(__file__).resolve().parents
        if (candidate / "ontology" / "packs").is_dir()
    )
    pack_directory = repo_root / "ontology" / "packs" / "dataco"
    pack = load_pack(pack_directory / "ontology.yaml").pack
    probe = probe_source(SAMPLE_CSV)
    mapping, coverage = inspect_mapping(pack_directory / "mapping.yaml", pack, header=probe.header)
    source = DelimitedTextSource(SAMPLE_CSV, SAMPLE_DATASET_VERSION, probe=probe, batch_size=64)
    report = _run(source, mapping, pack, coverage).report
    GOLDEN.write_text(to_canonical_json(report) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}\nreport_sha256={report_sha256(report)}")


if __name__ == "__main__":
    if "--write" in sys.argv:
        _write_golden()
    else:
        print(__doc__)
