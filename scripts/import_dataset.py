#!/usr/bin/env python3
"""Run a dataset import: pin the source, validate the mapping, measure, clean, report.

This is the wiring, and wiring is all it is. It belongs in `scripts/` rather than in a
reasoning package because it is the only place that knows about all of a file path, an
ontology pack, a mapping, and an output directory at once -- which is the orchestration
role, and `causalog.orchestration` does not exist yet (OQ-014).

What it does NOT do
-------------------
It writes nothing to PostgreSQL. Module 4 (Event Generator) does not exist, so there are no
`Event` values to persist, and inventing a persistence path for records that are not yet
facts would put rows into the system of record with no evidence chain behind them --
forbidden by `datasets/README.md` and unsatisfiable under LAW-EVIDENCE. The import ends at
the clean layer and the report, and the report says so under "What this report did not
check".

Exit codes
----------
    0  the import ran and the report was written
    1  the mapping was refused, the source could not be read, or the row count did not
       reconcile
    2  the import ran but the report carries ERROR findings

Two and one are deliberately different. A refused mapping is a broken configuration; ERROR
findings are a successful measurement of bad data, and a run that measured bad data has
done its job. Collapsing them would make "the adapter is misconfigured" and "the dataset has
defects" indistinguishable at the exit code, which is where CI reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from causalog import ENGINE_VERSION  # noqa: E402
from causalog.core.errors import CausaLogError  # noqa: E402
from causalog.core.serialization import to_canonical_json  # noqa: E402
from causalog.ingestion.data_adapter import (  # noqa: E402
    import_dataset,
    render_markdown,
    report_sha256,
)
from causalog.ingestion.data_adapter.profile import Profiler  # noqa: E402
from causalog.ingestion.schema_mapper import (  # noqa: E402
    load_mapping,
    render_proposal_yaml,
    suggest_mapping,
)
from causalog.ontology_runtime import load_pack  # noqa: E402
from causalog.ontology_runtime.diagnostics import Severity  # noqa: E402
from causalog.persistence.sources.dataco import (  # noqa: E402
    DATASET_ID,
    ENCODING_CANDIDATES,
    SOURCE_URL,
    default_pin_path,
    default_source_path,
)
from causalog.persistence.sources.delimited import (  # noqa: E402
    DelimitedTextSource,
    compose_dataset_version,
    probe_source,
)
from causalog.persistence.sources.pin import DatasetPin, write_pin  # noqa: E402


def _arguments() -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dataset", default=DATASET_ID, help="pack identifier (default: %(default)s)"
    )
    parser.add_argument(
        "--source", type=Path, default=None, help="override the source file"
    )
    parser.add_argument(
        "--reports",
        type=Path,
        default=REPO_ROOT / "docs" / "reports",
        help="directory the report is written under (default: %(default)s)",
    )
    parser.add_argument(
        "--clean-layer",
        type=Path,
        default=REPO_ROOT / "datasets" / "clean",
        help="directory the clean layer is written under (default: %(default)s)",
    )
    parser.add_argument(
        "--no-clean-layer",
        action="store_true",
        help="profile and validate without materialising the clean layer",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help=(
            "also write a mapping.proposal.yaml beside the report. The proposal carries "
            "status PROPOSED_UNCONFIRMED and cannot be loaded"
        ),
    )
    return parser.parse_args()


def _verify_manifest(pack_directory: Path, header: tuple[str, ...]) -> tuple[bool, str]:
    """Compare the pack's column manifest with the header actually read.

    Returns `(matches, message)`. A mismatch is REPORTED, not repaired: the manifest is a
    checked-in claim about a file, and quietly rewriting it to match whatever was on disk
    would delete the only evidence that the claim was ever wrong.
    """
    manifest_path = pack_directory / "columns.manifest.yaml"
    if not manifest_path.is_file():
        return (False, f"no column manifest at {manifest_path}")
    import yaml  # noqa: PLC0415 -- only this one branch needs it

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    declared = list(manifest.get("columns") or [])
    missing = [name for name in declared if name not in header]
    extra = [name for name in header if name not in declared]
    if missing or extra:
        return (
            False,
            f"manifest disagrees with the file: {len(missing)} declared column(s) absent "
            f"{missing}, {len(extra)} file column(s) undeclared {extra}",
        )
    return (
        True,
        f"all {len(declared)} declared columns are present in the file header",
    )


def main() -> int:
    """Wire one import together and run it."""
    arguments = _arguments()
    pack_directory = REPO_ROOT / "ontology" / "packs" / arguments.dataset
    source_path = arguments.source or default_source_path(REPO_ROOT)

    print(f"[1/6] loading ontology pack  {pack_directory / 'ontology.yaml'}")
    pack = load_pack(pack_directory / "ontology.yaml")
    print(
        f"      ontology_hash={pack.ontology_hash}  version={pack.pack.ontology_version}"
    )

    print(f"[2/6] probing source         {source_path}")
    probe = probe_source(source_path, encoding_candidates=ENCODING_CANDIDATES)
    print(
        f"      {probe.byte_count:,} bytes  sha256={probe.content_sha256}\n"
        f"      encoding={probe.encoding.chosen!r} rejected={list(probe.encoding.rejected)}"
        f"  delimiter={probe.dialect.delimiter!r} sniffed={probe.dialect.sniffed}"
        f"  columns={len(probe.header)}"
    )

    print(
        "[3/6] loading mapping        (a PROPOSED_UNCONFIRMED document is refused here)"
    )
    loaded = load_mapping(
        pack_directory / "mapping.yaml", pack.pack, header=probe.header
    )
    print(
        f"      mapping_hash={loaded.mapping_hash}  version={loaded.mapping.mapping_version}"
        f"  coverage: {len(loaded.coverage.errors)} error(s), "
        f"{len(loaded.coverage.warnings)} warning(s), "
        f"{len(loaded.coverage.not_runnable)} not-runnable"
    )

    dataset_version = compose_dataset_version(
        arguments.dataset, probe.content_sha256, loaded.mapping_hash
    )
    print(f"      dataset_version={dataset_version}")

    clean_layer = (
        None if arguments.no_clean_layer else arguments.clean_layer / dataset_version
    )
    source = DelimitedTextSource(source_path, dataset_version, probe=probe)

    print("[4/6] importing              two streaming passes over the source")
    result = import_dataset(
        source,
        loaded.mapping,
        pack.pack,
        loaded.coverage,
        dataset_id=arguments.dataset,
        source_url=SOURCE_URL,
        mapping_hash=loaded.mapping_hash,
        ontology_hash=pack.ontology_hash,
        engine_version=ENGINE_VERSION,
        clean_layer=clean_layer,
    )
    report = result.report
    print(
        f"      rows read={report.rows.rows_read:,} clean={report.rows.rows_clean:,} "
        f"quarantined={report.rows.rows_quarantined:,} "
        f"reconciles={report.rows.reconciles}"
    )

    matches, message = _verify_manifest(pack_directory, probe.header)
    print(
        f"[5/6] column manifest        {'VERIFIED' if matches else 'MISMATCH'}: {message}"
    )

    report_directory = arguments.reports / arguments.dataset / dataset_version
    report_directory.mkdir(parents=True, exist_ok=True)
    digest = report_sha256(report)
    (report_directory / "data-quality.json").write_text(
        to_canonical_json(report) + "\n", encoding="utf-8"
    )
    (report_directory / "data-quality.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    (report_directory / "report.sha256").write_text(digest + "\n", encoding="utf-8")

    if arguments.propose:
        profiler = Profiler(probe.header)
        for batch in source.read():
            for record in batch.records:
                profiler.observe_first(record.fields)
        proposal = suggest_mapping(profiler.result(), pack.pack)
        (report_directory / "mapping.proposal.yaml").write_text(
            render_proposal_yaml(
                proposal,
                mapping_id=arguments.dataset,
                mapping_version=loaded.mapping.mapping_version,
                header=probe.header,
            ),
            encoding="utf-8",
        )
        print(
            f"      proposal written with {len(proposal.bindings)} suggested binding(s)"
        )

    write_pin(
        default_pin_path(REPO_ROOT),
        DatasetPin(
            dataset_id=arguments.dataset,
            dataset_version=dataset_version,
            source_file=source_path.name,
            source_url=SOURCE_URL,
            byte_count=probe.byte_count,
            content_sha256=probe.content_sha256,
            row_count=report.rows.rows_read,
            header=probe.header,
            encoding_chosen=probe.encoding.chosen,
            encoding_rejected=probe.encoding.rejected,
            delimiter=probe.dialect.delimiter,
            mapping_id=loaded.mapping.mapping_id,
            mapping_version=loaded.mapping.mapping_version,
            mapping_hash=loaded.mapping_hash,
            ontology_pack=pack.pack.pack_id,
            ontology_version=pack.pack.ontology_version,
            ontology_hash=pack.ontology_hash,
        ),
    )

    errors = report.count_by_severity(Severity.ERROR)
    print(f"[6/6] report                 {report_directory}")
    print(f"      report_sha256={digest}")
    print(
        f"      findings: {errors} ERROR, "
        f"{report.count_by_severity(Severity.WARNING)} WARNING, "
        f"{report.count_by_severity(Severity.NOT_RUNNABLE)} NOT_RUNNABLE"
    )
    for constraint in report.headline_constraints:
        print(
            f"\n  !! {constraint.code}\n     {constraint.statement}\n     measured: {constraint.measurement}"
        )
    if not matches:
        print(
            "\nFAILED: the column manifest does not describe this file. Not flipping it."
        )
        return 1
    print(json.dumps({"dataset_version": dataset_version, "report_sha256": digest}))
    return 2 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CausaLogError as failure:
        print(f"\nIMPORT REFUSED: {failure}", file=sys.stderr)
        raise SystemExit(1) from failure
