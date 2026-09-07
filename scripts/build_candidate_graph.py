#!/usr/bin/env python3
"""Run module 9 over a clean layer and write the Candidate Graph Report.

Wiring, in exactly the sense `build_event_log.py` is wiring: it is the one place that knows
about a clean layer, an ontology pack, a mapping, a rule pack and an output directory at
once, which is the orchestration role, and `causalog.orchestration` does not exist yet
(OQ-014). It exists because a committed report nobody can regenerate is worse than no report.

WHY THIS IS BOUNDED BY DEFAULT, and why that is disclosed rather than hidden
----------------------------------------------------------------------------
The reference expansion is ~3.8 million events and does not fit in memory as models on an
8 GB machine -- measured, in `tests/integration/test_full_expansion_budget.py`. Module 9 is
not a streaming module: the historical-frequency and statistical-association generators
measure across process instances, so they need the instance set in hand, and the confounder
walk needs the candidate graph in hand.

So this script reads a BOUNDED PREFIX of the clean layer and says so, in the report and on
stdout. `--rows 0` removes the bound for anyone with the memory for it. A truncated run is
labelled a truncated run; the numbers below are a measurement of a slice, and reading them
as a measurement of the dataset would be the overclaiming this whole project is built to
avoid.

Exit codes
----------
    0  the graph was built and the report was written
    1  the pack, the mapping, the rule pack or the clean layer was refused or is missing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from causalog import ENGINE_VERSION  # noqa: E402
from causalog.causal_engine.candidate_cause_generator import (  # noqa: E402
    GenerationContext,
    generate_candidates,
    render_markdown,
)
from causalog.core.errors import CausaLogError  # noqa: E402
from causalog.core.run import OutputEnvelope, RunKey  # noqa: E402
from causalog.core.serialization import to_canonical_json  # noqa: E402
from causalog.extraction.entity_extractor import ConflictPolicy, EntityExtractor  # noqa: E402
from causalog.extraction.event_generator import EventGenerator, MissingEventPolicy  # noqa: E402
from causalog.extraction.ontology_adapters import (  # noqa: E402
    process_definitions_of,
    vocabulary_of,
)
from causalog.graph_engine.timeline_builder import TimelineBuilder  # noqa: E402
from causalog.ingestion.schema_mapper import (  # noqa: E402
    MappedRecordBatch,
    MappingPlan,
    apply_mapping,
    load_mapping,
    mapping_hash,
)
from causalog.ontology_runtime import load_pack  # noqa: E402
from causalog.rule_engine import evaluate, load_rule_pack  # noqa: E402
from causalog.rule_engine.facts import FactSet  # noqa: E402

#: Matches `build_event_log.py`. `graph_projection_version` has no value until module 8
#: exists, and stating so is better than minting a plausible-looking one.
UNSET = "unset"

DATASET_ID = "dataco"
BATCH_SIZE = 5_000

#: The default row bound. Chosen so the run completes in minutes on a developer machine and
#: still spans thousands of process instances, which is what the two counting generators
#: need to measure anything. It is a bound on THIS SCRIPT, not a parameter of the module.
DEFAULT_ROWS = 20_000


def _arguments() -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default=DATASET_ID, help="pack identifier")
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help="bound the clean layer to this many rows; 0 removes the bound "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--clean-layer", type=Path, default=REPO_ROOT / "datasets" / "clean"
    )
    parser.add_argument("--reports", type=Path, default=REPO_ROOT / "docs" / "reports")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _batches(
    layer: Path, plan: MappingPlan, dataset_version: str, ontology_hash: str, rows: int
) -> list[MappedRecordBatch]:
    """Return mapped batches from at most `rows` rows of a clean layer.

    Collected rather than streamed, deliberately and unlike `build_event_log.py`: module 9
    is not a streaming module, so the bound is what makes the run finite rather than the
    streaming is. Pretending to stream into a module that collects would hide where the
    memory actually goes.
    """
    batches: list[MappedRecordBatch] = []
    records = []
    index = 0
    with layer.open(encoding="utf-8") as handle:
        for count, line in enumerate(handle):
            if rows and count >= rows:
                break
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
                batches.append(
                    MappedRecordBatch(
                        dataset_version=dataset_version,
                        ontology_hash=ontology_hash,
                        batch_index=index,
                        records=tuple(records),
                    )
                )
                records = []
                index += 1
    if records:
        batches.append(
            MappedRecordBatch(
                dataset_version=dataset_version,
                ontology_hash=ontology_hash,
                batch_index=index,
                records=tuple(records),
            )
        )
    return batches


def main() -> int:
    """Wire one candidate generation together and run it."""
    arguments = _arguments()
    pack_directory = REPO_ROOT / "ontology" / "packs" / arguments.dataset
    rules_path = REPO_ROOT / "rule_engine" / arguments.dataset / "rules.yaml"
    pin_path = REPO_ROOT / "datasets" / f"{arguments.dataset}.pin.json"

    try:
        loaded_pack = load_pack(pack_directory / "ontology.yaml")
        loaded_mapping = load_mapping(pack_directory / "mapping.yaml", loaded_pack.pack)
        loaded_rules = load_rule_pack(
            rules_path, vocabulary=vocabulary_of(loaded_pack.pack)
        )
    except CausaLogError as failure:
        print(f"[1/6] packs              REFUSED\n{failure}", file=sys.stderr)
        return 1
    print(
        f"[1/6] packs              {loaded_pack.ontology_hash} "
        f"{loaded_mapping.mapping_hash} {loaded_rules.rule_pack_hash}"
    )

    if not pin_path.is_file():
        print(f"[2/6] pin                MISSING at {pin_path}", file=sys.stderr)
        return 1
    pin = json.loads(pin_path.read_text(encoding="utf-8"))["payload"]
    dataset_version = pin["dataset_version"]
    if mapping_hash(loaded_mapping.mapping) != pin["mapping_hash"]:
        print("[2/6] pin                STALE; re-run `make import`", file=sys.stderr)
        return 1
    print(f"[2/6] pin                {dataset_version}")

    layer = arguments.clean_layer / dataset_version / "records.jsonl"
    if not layer.is_file():
        print(f"[3/6] clean layer        MISSING at {layer}", file=sys.stderr)
        return 1
    bound = (
        "unbounded" if arguments.rows == 0 else f"bounded to {arguments.rows:,} rows"
    )
    print(f"[3/6] clean layer        {bound}")

    plan = MappingPlan.build(loaded_mapping.mapping)
    key = RunKey(
        dataset_version=dataset_version,
        ontology_hash=loaded_pack.ontology_hash,
        rule_pack_version=loaded_rules.rule_pack_version,
        engine_version=ENGINE_VERSION,
        seed=arguments.seed,
    )
    envelope = OutputEnvelope(
        run_id=key.address(),
        ontology_version=loaded_pack.pack.ontology_version,
        ontology_hash=loaded_pack.ontology_hash,
        dataset_version=dataset_version,
        rule_pack_version=loaded_rules.rule_pack_version,
        engine_version=ENGINE_VERSION,
        graph_projection_version=UNSET,
        seed=arguments.seed,
        execution_id=f"script:{key.address()}",
    )

    batches = _batches(
        layer, plan, dataset_version, loaded_pack.ontology_hash, arguments.rows
    )
    extractor = EntityExtractor(
        loaded_pack.pack,
        loaded_mapping.mapping,
        loaded_pack.ontology_hash,
        policy=ConflictPolicy.FIRST_WINS,
    )
    extraction = extractor.extract(iter(batches), envelope)
    print(f"[4/6] entities           {len(extraction.entities):,}")

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
        missing_event_policy=MissingEventPolicy.RECORD_GAP,
    )
    streamed = generator.stream(
        lambda: iter(batches),
        anchors,
        extraction.entity_ids(),
        envelope,
        conflict_policy=ConflictPolicy.FIRST_WINS.value,
    )
    events = tuple(streamed.events)
    print(f"[4/6] events             {len(events):,}")

    builder = TimelineBuilder(
        process_definitions_of(loaded_pack.pack), loaded_pack.ontology_hash
    )
    built = builder.build(events, extraction.entities, envelope)
    print(f"[5/6] timelines          {len(built.timelines):,}")

    facts = FactSet.of(events=events)
    evaluation = evaluate(loaded_rules.pack, facts)
    print(
        f"[5/6] rule firings       {len(evaluation.firings):,} from "
        f"{len(evaluation.fired_rule_ids())} rule(s)"
    )

    context = GenerationContext(
        facts=facts,
        timelines=built.timelines,
        parameters=loaded_rules.pack.candidate_generation,
        rule_evaluation=evaluation,
        run_id=envelope.run_id,
    )
    result = generate_candidates(context, envelope)
    print(f"[6/6] candidates         {len(result.graph.candidates):,}")

    destination = arguments.reports / arguments.dataset / dataset_version
    destination.mkdir(parents=True, exist_ok=True)
    rendered = render_markdown(result.report)
    if arguments.rows:
        rendered = rendered.replace(
            "# Candidate Graph Report",
            "# Candidate Graph Report\n\n"
            f"> **BOUNDED RUN.** Built from the first {arguments.rows:,} rows of the clean\n"
            f"> layer, not from all {pin['row_count']:,}. Module 9 is not a streaming\n"
            "> module -- the two counting generators measure across process instances and\n"
            "> the confounder walk needs the graph in hand -- and the full expansion does\n"
            "> not fit in memory as models on an 8 GB machine\n"
            "> (`tests/integration/test_full_expansion_budget.py`). **Every number below\n"
            "> measures this slice, not the dataset.** Re-run with `--rows 0` to remove\n"
            "> the bound.",
            1,
        )
    (destination / "candidate-graph.md").write_text(rendered, encoding="utf-8")
    (destination / "candidate-graph.json").write_text(
        to_canonical_json(result.report), encoding="utf-8"
    )
    print(f"      report             {destination / 'candidate-graph.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
