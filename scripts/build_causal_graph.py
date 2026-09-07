#!/usr/bin/env python3
"""Run modules 9 and 10 over a clean layer and write the Confidence Report.

Wiring, in exactly the sense `build_candidate_graph.py` is wiring, and deliberately its
sibling: it reads the same clean layer, mints the same `run_id`, and adds one step. Module
10 needs everything module 9 needed plus module 9's output, so re-running the generation
here is cheaper and more honest than persisting an intermediate nobody would re-derive.

WHY THIS IS BOUNDED BY DEFAULT, and why that is disclosed rather than hidden
----------------------------------------------------------------------------
Identical to `build_candidate_graph.py` and for identical reasons: module 9 is not a
streaming module, and module 10 is less so -- the base rates measure across process
instances and the fusion needs the whole candidate graph in hand. So this reads a BOUNDED
PREFIX of the clean layer and says so, in the report and on stdout. The default matches
`build_candidate_graph.py`'s committed run so the two reports describe one slice; `--rows 0`
removes the bound.

**Every number in the output measures that slice, not the dataset.** Reading them as a
measurement of DataCo would be the overclaiming this project is built to avoid.

Exit codes
----------
    0  the graph was scored and the report was written
    1  the pack, the mapping, the rule pack or the clean layer was refused or is missing
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from causalog import ENGINE_VERSION  # noqa: E402
from causalog.causal_engine.candidate_cause_generator import (  # noqa: E402
    GenerationContext,
    generate_candidates,
)
from causalog.causal_engine.confidence_scorer import (  # noqa: E402
    PairBaseRates,
    ScoringContext,
    render_markdown,
    score_candidates,
)
from causalog.core.errors import CausaLogError  # noqa: E402
from causalog.core.precedence import DerivedPrecedenceIndex  # noqa: E402
from causalog.core.run import OutputEnvelope, RunKey  # noqa: E402
from causalog.core.serialization import (  # noqa: E402
    from_canonical_json,
    to_canonical_json,
)
from causalog.ingestion.data_adapter import (  # noqa: E402
    DataQualityReport,
    derived_precedence_index,
    report_sha256,
)
from causalog.extraction.entity_extractor import ConflictPolicy, EntityExtractor  # noqa: E402
from causalog.extraction.event_generator import EventGenerator, MissingEventPolicy  # noqa: E402
from causalog.causal_engine.causal_graph_builder import (  # noqa: E402
    GraphBuildContext,
    build_causal_graph,
)
from causalog.causal_engine.causal_graph_builder import (  # noqa: E402
    render_markdown as render_graph_quality,
)
from causalog.extraction.ontology_adapters import (  # noqa: E402
    magnitude_measurements_of,
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

#: Matches `build_event_log.py` and `build_candidate_graph.py`. `graph_projection_version`
#: has no value until module 8 exists, and stating so beats minting a plausible-looking one.
UNSET = "unset"

DATASET_ID = "dataco"
BATCH_SIZE = 5_000

#: The default row bound. Matches the committed `build_candidate_graph.py` run, so the
#: candidate-graph report and the confidence report describe the same slice and their
#: numbers can be read against each other. A bound on THIS SCRIPT, not a module parameter.
DEFAULT_ROWS = 150

BOUNDED_NOTICE = (
    "> **BOUNDED RUN.** Built from the first {rows:,} rows of the clean layer, not from\n"
    "> all {total:,}. Neither module 9 nor module 10 is a streaming module -- the base\n"
    "> rates measure across process instances and the fusion needs the whole candidate\n"
    "> graph in hand -- and the full expansion does not fit in memory as models on an 8 GB\n"
    "> machine (`tests/integration/test_full_expansion_budget.py`). **Every number below\n"
    "> measures this slice, not the dataset.** Re-run with `--rows 0` to remove the bound."
)


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
    parser.add_argument(
        "--data-quality-report",
        type=Path,
        default=None,
        help="module 1's report, whose measured derivation checks tell the scorer "
        "which instants this source COMPUTED rather than recorded. Defaults to the "
        "one `make import` wrote for this dataset version. Absent, the run proceeds "
        "and reports the gap; STALE, the run refuses.",
    )
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _batches(
    layer: Path, plan: MappingPlan, dataset_version: str, ontology_hash: str, rows: int
) -> list[MappedRecordBatch]:
    """Return mapped batches from at most `rows` rows of a clean layer."""
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


def _derived_precedence(
    path: Path, dataset_version: str, expected_mapping_hash: str
) -> DerivedPrecedenceIndex | None:
    """Return the measured derivation index, or None when no report was supplied.

    Three outcomes, and the difference between the second and third is the whole point.

    * **The report is there and belongs to this run** -- return its index, possibly empty.
    * **No report** -- return None. The scorer then scores tightness and says on every
      affected edge that nobody looked. A gap, not a failure: a run may legitimately be
      made before the audit exists.
    * **A report that belongs to a DIFFERENT run** -- raise. This one is not a gap and must
      never be softened into one. `run_id` is built from `dataset_version`, the ontology
      hash, the rule pack version, the engine version and the seed. A report from another
      dataset version would change scores while `run_id` stayed put, so two runs bearing
      one identifier would hold different numbers -- ADR-0013's guarantee broken silently,
      which is worse than either a refusal or an honest gap.
    """
    if not path.is_file():
        return None
    report = from_canonical_json(DataQualityReport, path.read_text(encoding="utf-8"))
    if report.dataset_version != dataset_version:
        raise CausaLogError(
            f"{path} reports dataset version {report.dataset_version!r}, and this run is "
            f"{dataset_version!r}. Scoring against another version's measurements would "
            "change every score without changing run_id. Re-run `make import`."
        )
    if report.mapping_hash != expected_mapping_hash:
        raise CausaLogError(
            f"{path} was written under mapping {report.mapping_hash!r} and this run uses "
            f"{expected_mapping_hash!r}. The mapping decides which columns are bound and "
            "at what precision, so its measurements do not transfer. Re-run `make import`."
        )
    digest_path = path.parent / "report.sha256"
    if digest_path.is_file():
        recorded = digest_path.read_text(encoding="utf-8").strip()
        actual = report_sha256(report)
        if recorded != actual:
            raise CausaLogError(
                f"{path} does not match the digest beside it ({recorded} recorded, "
                f"{actual} computed). The report has been edited since it was written, and "
                "an edited measurement is not a measurement."
            )
    return derived_precedence_index(report.derivations)


@dataclass(frozen=True)
class Pipeline:
    """Everything the nine stages produced, for a caller that wants more than the reports.

    Extracted so that `analyze_root_causes.py` runs the SAME nine stages rather than a
    second copy of them. Two copies would drift, and the first symptom would be two reports
    describing one slice while disagreeing about it -- which is the failure this repository's
    report-versus-prose corrections keep recording (DEF-0004).
    """

    pack: object
    rules: object
    envelope: OutputEnvelope
    dataset_version: str
    row_count: int
    events: tuple
    timelines: tuple
    facts: object
    scored: object
    construction: object
    scoring_report: object
    #: Module 1's measurement of which instants the source COMPUTED rather than recorded,
    #: carried on the pipeline so that every consumer reads ONE measurement. Module 13 needs
    #: it to re-time anything downstream of a move at all; recomputing it in that script
    #: would be the second copy this dataclass exists to prevent.
    derived_precedence: object = None


def run_pipeline(arguments: argparse.Namespace) -> Pipeline | None:
    """Run stages 1-9 over a clean layer, printing progress. None means a stage refused."""
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
        print(f"[1/9] packs              REFUSED\n{failure}", file=sys.stderr)
        return None
    print(
        f"[1/9] packs              {loaded_pack.ontology_hash} "
        f"{loaded_mapping.mapping_hash} {loaded_rules.rule_pack_hash}"
    )

    if not pin_path.is_file():
        print(f"[2/9] pin                MISSING at {pin_path}", file=sys.stderr)
        return None
    pin = json.loads(pin_path.read_text(encoding="utf-8"))["payload"]
    dataset_version = pin["dataset_version"]
    if mapping_hash(loaded_mapping.mapping) != pin["mapping_hash"]:
        print("[2/9] pin                STALE; re-run `make import`", file=sys.stderr)
        return None
    print(f"[2/9] pin                {dataset_version}")

    layer = arguments.clean_layer / dataset_version / "records.jsonl"
    if not layer.is_file():
        print(f"[3/9] clean layer        MISSING at {layer}", file=sys.stderr)
        return None
    bound = (
        "unbounded" if arguments.rows == 0 else f"bounded to {arguments.rows:,} rows"
    )
    print(f"[3/9] clean layer        {bound}")

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
    print(f"[4/9] entities           {len(extraction.entities):,}")

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
    print(f"[4/9] events             {len(events):,}")

    builder = TimelineBuilder(
        process_definitions_of(loaded_pack.pack), loaded_pack.ontology_hash
    )
    built = builder.build(events, extraction.entities, envelope)
    print(f"[5/9] timelines          {len(built.timelines):,}")

    facts = FactSet.of(events=events)
    evaluation = evaluate(loaded_rules.pack, facts)
    print(
        f"[5/9] rule firings       {len(evaluation.firings):,} from "
        f"{len(evaluation.fired_rule_ids())} rule(s)"
    )

    generation = generate_candidates(
        GenerationContext(
            facts=facts,
            timelines=built.timelines,
            parameters=loaded_rules.pack.candidate_generation,
            rule_evaluation=evaluation,
            run_id=envelope.run_id,
        ),
        envelope,
    )
    print(f"[6/9] candidates         {len(generation.graph.candidates):,}")

    quality_path = arguments.data_quality_report or (
        arguments.reports / arguments.dataset / dataset_version / "data-quality.json"
    )
    try:
        derived_precedence = _derived_precedence(
            quality_path, dataset_version, pin["mapping_hash"]
        )
    except CausaLogError as failure:
        print(f"[7/9] derivation audit   REFUSED\n{failure}", file=sys.stderr)
        return None
    if derived_precedence is None:
        print(
            f"[7/9] derivation audit   GAP; no report at {quality_path}. Precedence this "
            "source COMPUTED is scored as though observed."
        )
    elif derived_precedence.entries:
        checks = ", ".join(entry.check_id for entry in derived_precedence.entries)
        print(
            f"[7/9] derivation audit   {len(derived_precedence.entries)} confirmed: {checks}"
        )
    else:
        print("[7/9] derivation audit   audited; no declared derivation was confirmed")

    events_by_id = {event.event_id: event for event in events}
    scoring_context = ScoringContext(
        facts=facts,
        timelines=built.timelines,
        base_rates=PairBaseRates.of(built.timelines, events_by_id),
        parameters=loaded_rules.pack.confidence_scoring,
        rule_evaluation=evaluation,
        confounding_flags=generation.confounding_flags,
        # Module 9 refuses a prohibited pair at its gate, so nothing prohibited survives to
        # be scored. Passed anyway: the scorer must not depend on an upstream filter it
        # cannot see, and a pair that DID survive would be a defect worth capping.
        suppressed_pairs=frozenset(),
        derived_precedence=derived_precedence,
        proposed_pairs=frozenset(
            (candidate.source_event_id, candidate.target_event_id)
            for candidate in generation.graph.candidates
        ),
        run_id=envelope.run_id,
    )
    result = score_candidates(generation.graph.candidates, scoring_context, envelope)
    print(
        f"[8/9] scored edges       {len(result.graph.edges):,} "
        f"({result.report.scored_count:,} scored, "
        f"{result.report.insufficient_count:,} insufficient, "
        f"{result.report.promoted_count:,} promoted)"
    )

    construction = build_causal_graph(
        result.graph,
        GraphBuildContext(
            facts=facts,
            timelines=built.timelines,
            candidates=generation.graph.candidates,
            parameters=loaded_rules.pack.graph_construction,
            bands=loaded_rules.pack.confidence_scoring,
            rule_evaluation=evaluation,
            magnitude_measurements=magnitude_measurements_of(loaded_pack.pack),
            run_id=envelope.run_id,
        ),
        envelope,
    )
    print(
        f"[9/9] causal graph       {len(construction.graph.edges):,} promoted, "
        f"{len(construction.graph.demotions):,} rejected; "
        f"{len(construction.loops.loops):,} circuit(s) "
        f"({dict(construction.loops.by_classification()).get('GENUINE', 0)} genuine)"
    )

    return Pipeline(
        pack=loaded_pack,
        rules=loaded_rules,
        envelope=envelope,
        dataset_version=dataset_version,
        row_count=pin["row_count"],
        events=events,
        timelines=built.timelines,
        facts=facts,
        scored=result.graph,
        construction=construction,
        scoring_report=result.report,
        derived_precedence=derived_precedence,
    )


def main() -> int:
    """Wire one candidate generation and one scoring together and run them."""
    arguments = _arguments()
    pipeline = run_pipeline(arguments)
    if pipeline is None:
        return 1
    result_report = pipeline.scoring_report
    construction = pipeline.construction
    pin = {"row_count": pipeline.row_count}

    destination = arguments.reports / arguments.dataset / pipeline.dataset_version
    destination.mkdir(parents=True, exist_ok=True)
    rendered = render_markdown(result_report)
    if arguments.rows:
        rendered = rendered.replace(
            "# Confidence Report",
            "# Confidence Report\n\n"
            + BOUNDED_NOTICE.format(rows=arguments.rows, total=pin["row_count"]),
            1,
        )
    (destination / "confidence.md").write_text(rendered, encoding="utf-8")
    (destination / "confidence.json").write_text(
        to_canonical_json(result_report), encoding="utf-8"
    )
    print(f"      report             {destination / 'confidence.md'}")

    graph_rendered = render_graph_quality(construction.report)
    if arguments.rows:
        graph_rendered = graph_rendered.replace(
            "# Graph Quality Report",
            "# Graph Quality Report\n\n"
            + BOUNDED_NOTICE.format(rows=arguments.rows, total=pin["row_count"]),
            1,
        )
    (destination / "causal-graph.md").write_text(graph_rendered, encoding="utf-8")
    (destination / "causal-graph.json").write_text(
        to_canonical_json(construction.report), encoding="utf-8"
    )
    (destination / "causal-graph-edges.json").write_text(
        to_canonical_json(construction.graph), encoding="utf-8"
    )
    print(f"      report             {destination / 'causal-graph.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
