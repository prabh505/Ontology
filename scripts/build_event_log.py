#!/usr/bin/env python3
"""Expand a clean layer into entities and events, and write the two reports.

The counterpart to `import_dataset.py`, and wiring in exactly the same sense: it is the one
place that knows about a clean layer, an ontology pack, a mapping and an output directory at
once, which is the orchestration role, and `causalog.orchestration` does not exist yet
(OQ-014).

It exists because a committed report nobody can regenerate is worse than no report. Module
1's Data Quality Report is reproducible by `make import`; the Reconciliation Report and the
Event Quality Report are reproducible by this.

What it does NOT do
-------------------
It writes nothing to PostgreSQL. Forbidden edge F4 admits only `orchestration` to
`causalog.persistence`, and persisting facts before an orchestration pipeline can scope them
to a `Run` would put artifacts into the system of record with no envelope to verify them
against. The expansion ends at the two reports, and both say so under "What this run did NOT
check".

**Events are streamed, not collected.** The reference expansion does not fit in memory as
models on an 8 GB machine -- measured, in `tests/integration/test_full_expansion_budget.py`.
With `--write-events` each event is written out as it is produced; without it, the events are
counted and discarded and only the reports are written. Neither path holds the log.

Exit codes
----------
    0  the expansion ran and both reports were written
    1  the mapping was refused, the pack was invalid, or the clean layer is missing
    2  the expansion ran and the mapping coverage carries ERROR findings

Two and one are deliberately different, for the reason `import_dataset.py` gives: a refused
mapping is a broken configuration, and findings are a successful measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from causalog import ENGINE_VERSION  # noqa: E402
from causalog.core.errors import CausaLogError  # noqa: E402
from causalog.core.run import OutputEnvelope, RunKey  # noqa: E402
from causalog.core.serialization import to_canonical_json  # noqa: E402
from causalog.extraction.entity_extractor import (  # noqa: E402
    ConflictPolicy,
    EntityExtractor,
)
from causalog.extraction.entity_extractor import (  # noqa: E402
    render_markdown as render_reconciliation,
)
from causalog.extraction.event_generator import (  # noqa: E402
    EventGenerator,
    MissingEventPolicy,
)
from causalog.extraction.event_generator import render_markdown as render_quality  # noqa: E402
from causalog.ingestion.schema_mapper import (  # noqa: E402
    MappedRecordBatch,
    MappingPlan,
    apply_mapping,
    load_mapping,
    mapping_hash,
)
from causalog.ontology_runtime import load_pack  # noqa: E402

DATASET_ID = "dataco"

#: Records per mapped batch. Bounded so peak memory is a function of the batch and of the
#: identity cardinality, never of the record count.
BATCH_SIZE = 20_000

#: `rule_pack_version` is `unset` (`CONTEXT.md` §7) because no rule pack exists. It is
#: carried into the run key as the literal string rather than omitted, so the `run_id` of a
#: run made before rules existed is distinguishable from one made after.
UNSET = "unset"


def _arguments() -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dataset", default=DATASET_ID, help="pack identifier (default: %(default)s)"
    )
    parser.add_argument(
        "--clean-layer",
        type=Path,
        default=REPO_ROOT / "datasets" / "clean",
        help="directory the clean layers live under (default: %(default)s)",
    )
    parser.add_argument(
        "--reports",
        type=Path,
        default=REPO_ROOT / "docs" / "reports",
        help="directory the reports are written under (default: %(default)s)",
    )
    parser.add_argument(
        "--conflict-policy",
        choices=[item.value for item in ConflictPolicy],
        default=ConflictPolicy.FIRST_WINS.value,
        help="how an attribute disagreement is resolved (default: %(default)s)",
    )
    parser.add_argument(
        "--missing-event-policy",
        choices=[item.value for item in MissingEventPolicy],
        default=MissingEventPolicy.RECORD_GAP.value,
        help="what happens at a process step no field supports (default: %(default)s)",
    )
    parser.add_argument(
        "--write-events",
        type=Path,
        default=None,
        help=(
            "write every event as canonical JSONL to this path, streamed. Omitted, the "
            "events are counted and discarded and only the reports are written"
        ),
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="run seed (default: %(default)s)"
    )
    return parser.parse_args()


def _batches(
    layer: Path, plan: MappingPlan, dataset_version: str, ontology_hash: str
) -> Iterator[MappedRecordBatch]:
    """Yield mapped batches from a clean layer, streaming.

    The clean layer already holds the output of the mapping's transform chains, so they are
    not re-applied: a chain containing a parse is not idempotent in its receipts, and
    re-running it would double-count every change against a ledger this script does not own.
    """
    records = []
    index = 0
    with layer.open(encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            records.append(
                apply_mapping(
                    payload["values"],
                    payload["evidence_record_id"],
                    payload["row_number"],
                    plan,
                )
            )
            if len(records) >= BATCH_SIZE:
                yield MappedRecordBatch(
                    dataset_version=dataset_version,
                    ontology_hash=ontology_hash,
                    batch_index=index,
                    records=tuple(records),
                )
                records = []
                index += 1
    if records:
        yield MappedRecordBatch(
            dataset_version=dataset_version,
            ontology_hash=ontology_hash,
            batch_index=index,
            records=tuple(records),
        )


def main() -> int:
    """Wire one expansion together and run it."""
    arguments = _arguments()
    pack_directory = REPO_ROOT / "ontology" / "packs" / arguments.dataset
    pin_path = REPO_ROOT / "datasets" / f"{arguments.dataset}.pin.json"

    try:
        loaded_pack = load_pack(pack_directory / "ontology.yaml")
        loaded_mapping = load_mapping(pack_directory / "mapping.yaml", loaded_pack.pack)
    except CausaLogError as failure:
        print(f"[1/5] pack + mapping     REFUSED\n{failure}", file=sys.stderr)
        return 1
    print(
        f"[1/5] pack + mapping     {loaded_pack.ontology_hash} {loaded_mapping.mapping_hash}"
    )

    if not pin_path.is_file():
        print(f"[2/5] pin                MISSING at {pin_path}", file=sys.stderr)
        print(
            "      run `make import DATASET=%s` first" % arguments.dataset,
            file=sys.stderr,
        )
        return 1
    pin = json.loads(pin_path.read_text(encoding="utf-8"))["payload"]
    dataset_version = pin["dataset_version"]
    if mapping_hash(loaded_mapping.mapping) != pin["mapping_hash"]:
        print(
            f"[2/5] pin                STALE: pinned under {pin['mapping_hash']}, the "
            f"mapping now addresses to {mapping_hash(loaded_mapping.mapping)}.\n"
            "      The mapping participates in dataset_version (ADR-0035); re-run "
            f"`make import DATASET={arguments.dataset}`.",
            file=sys.stderr,
        )
        return 1
    print(f"[2/5] pin                {dataset_version}")

    layer = arguments.clean_layer / dataset_version / "records.jsonl"
    if not layer.is_file():
        print(f"[3/5] clean layer        MISSING at {layer}", file=sys.stderr)
        return 1
    print(f"[3/5] clean layer        {layer.stat().st_size:,} bytes")

    plan = MappingPlan.build(loaded_mapping.mapping)
    key = RunKey(
        dataset_version=dataset_version,
        ontology_hash=loaded_pack.ontology_hash,
        rule_pack_version=UNSET,
        engine_version=ENGINE_VERSION,
        seed=arguments.seed,
    )
    envelope = OutputEnvelope(
        run_id=key.address(),
        ontology_version=loaded_pack.pack.ontology_version,
        ontology_hash=loaded_pack.ontology_hash,
        dataset_version=dataset_version,
        rule_pack_version=UNSET,
        engine_version=ENGINE_VERSION,
        graph_projection_version=UNSET,
        seed=arguments.seed,
        # Random per execution and excluded from every determinism diff (ADR-0013). It is
        # derived from the run identifier here rather than from entropy so that this
        # script's own output stays byte-comparable between runs; a real pipeline mints one.
        execution_id=f"script:{key.address()}",
    )

    conflict_policy = ConflictPolicy(arguments.conflict_policy)
    extractor = EntityExtractor(
        loaded_pack.pack,
        loaded_mapping.mapping,
        loaded_pack.ontology_hash,
        policy=conflict_policy,
    )
    extraction = extractor.extract(
        _batches(layer, plan, dataset_version, loaded_pack.ontology_hash), envelope
    )
    print(
        f"[4/5] entities           {len(extraction.entities):,} from "
        f"{extraction.report.records_read:,} records; "
        f"{extraction.report.conflicts_total:,} conflict(s) under {conflict_policy.value}"
    )

    anchor_types = {
        item.anchor_entity_type for item in loaded_pack.pack.process_definitions
    }
    anchors = frozenset(
        entity.entity_id
        for entity in extraction.entities
        if entity.entity_type in anchor_types
    )
    generator = EventGenerator(
        loaded_pack.pack,
        loaded_mapping.mapping,
        loaded_pack.ontology_hash,
        missing_event_policy=MissingEventPolicy(arguments.missing_event_policy),
    )
    streamed = generator.stream(
        lambda: _batches(layer, plan, dataset_version, loaded_pack.ontology_hash),
        anchors,
        extraction.entity_ids(),
        envelope,
        conflict_policy=conflict_policy.value,
    )
    if arguments.write_events is None:
        for _event in streamed.events:
            pass
    else:
        arguments.write_events.parent.mkdir(parents=True, exist_ok=True)
        with arguments.write_events.open("w", encoding="utf-8") as handle:
            for event in streamed.events:
                handle.write(to_canonical_json(event) + "\n")
    report = streamed.report()
    print(f"[5/5] events             {report.events_total:,}")

    destination = arguments.reports / arguments.dataset / dataset_version
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "reconciliation.md").write_text(
        render_reconciliation(extraction.report), encoding="utf-8"
    )
    (destination / "reconciliation.json").write_text(
        to_canonical_json(extraction.report), encoding="utf-8"
    )
    (destination / "event-quality.md").write_text(
        render_quality(report), encoding="utf-8"
    )
    (destination / "event-quality.json").write_text(
        to_canonical_json(report), encoding="utf-8"
    )
    print(f"      reports            {destination}")
    print(json.dumps({"run_id": envelope.run_id, "events": report.events_total}))
    return 2 if loaded_mapping.coverage.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
