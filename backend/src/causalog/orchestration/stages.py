"""The pipeline as an explicit, declared, inspectable list of stages.

Before module 16 this pipeline existed only inside `scripts/build_causal_graph.py`, as a
250-line function that printed `[4/9]` as it went and returned `None` when anything
refused. Three sibling scripts imported it. That shape works for a command somebody
watches and fails for everything the API needs: there is no stage identity to report
progress against, no way to resume, no per-stage timing, and a refusal anywhere ends the
whole run even when six later stages had no dependency on it.

So the stages are DATA here, not control flow. Each declares its identity, what it needs,
what it produces, and which prd.md §55 budget (if any) bounds it. That buys four things
the function could not give:

1. **Progress and per-stage timing** -- a client polling a job sees a stage list, not a
   percentage somebody invented.
2. **Resumption** -- a restarted execution folds the ledger and skips what already
   succeeded, because a stage has a name the ledger can hold.
3. **Failure isolation** -- `requires` makes the dependency explicit, so a refusal blocks
   exactly its dependents and nothing else runs that did not need it.
4. **Honesty about what does not exist.** Modules 7, 8 and 15 are `not-started`, and their
   stages are DECLARED here with `NOT_RUNNABLE` and a reason rather than omitted. An
   omitted stage is indistinguishable from a stage that ran and found nothing; a declared
   one says which module is missing and what it would have contributed. This is the same
   ruling every `scripts/check_*.py` already makes with exit code 2 -- a gate that cannot
   run must never look like a gate that passed.

**This module does not run stages.** `jobs.py` executes them and writes the ledger; this
file only says what they are. Keeping the declaration separate from the execution is what
lets a test assert properties of the pipeline -- that its dependencies are acyclic, that
every `requires` names a real stage -- without running anything.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from causalog import ENGINE_VERSION
from causalog.causal_engine.candidate_cause_generator import (
    GenerationContext,
    generate_candidates,
)
from causalog.causal_engine.causal_graph_builder import (
    GraphBuildContext,
    build_causal_graph,
)
from causalog.causal_engine.confidence_scorer import (
    PairBaseRates,
    ScoringContext,
    score_candidates,
)
from causalog.core.errors import CausaLogError, ContractViolationError
from causalog.core.precedence import DerivedPrecedenceIndex
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.serialization import from_canonical_json
from causalog.extraction.entity_extractor import ConflictPolicy, EntityExtractor
from causalog.extraction.event_generator import EventGenerator, MissingEventPolicy
from causalog.extraction.ontology_adapters import (
    duration_measurements_of,
    lifecycles_of,
    magnitude_measurements_of,
    process_definitions_of,
    vocabulary_of,
)
from causalog.graph_engine.state_engine import StateEngine
from causalog.graph_engine.timeline_builder import TimelineBuilder
from causalog.ingestion.data_adapter import (
    DataQualityReport,
    derived_precedence_index,
    report_sha256,
)
from causalog.ingestion.schema_mapper import (
    MappedRecordBatch,
    MappingPlan,
    apply_mapping,
    load_mapping,
    mapping_hash,
)
from causalog.ontology_runtime import load_pack
from causalog.orchestration.timing import BudgetName
from causalog.rule_engine import evaluate, load_rule_pack
from causalog.rule_engine.facts import FactSet

__all__ = [
    "BATCH_SIZE",
    "PIPELINE_STAGES",
    "PipelineRequest",
    "PipelineState",
    "Stage",
    "stage_by_id",
    "stage_ids",
]

#: Matches `scripts/build_causal_graph.py`. Records per mapped batch.
BATCH_SIZE: Final[int] = 5_000

#: `graph_projection_version` has no value until module 8 exists. Stating that beats
#: minting a plausible-looking one, and the three existing wiring scripts already say it
#: this way -- a fourth spelling would let them disagree.
UNSET: Final[str] = "unset"


@dataclass(frozen=True)
class PipelineRequest:
    """Everything one execution needs to know before it starts.

    `rows` bounds the clean layer, and the bound is a property of the REQUEST rather than
    of any module. Neither module 9 nor module 10 streams -- the base rates measure across
    process instances and the fusion needs the whole candidate graph in hand -- so an
    unbounded expansion of this dataset does not fit in memory on an 8 GB machine. `rows=0`
    removes the bound. Every number a bounded execution produces measures that slice and
    not the dataset, and the API says so on every response that carries one.
    """

    dataset_id: str
    repository_root: Path
    rows: int = 150
    seed: int = 0
    clean_layer_root: Path | None = None
    reports_root: Path | None = None

    def pack_directory(self) -> Path:
        """Return the domain pack directory for this request's dataset."""
        return self.repository_root / "ontology" / "packs" / self.dataset_id

    def rules_path(self) -> Path:
        """Return the rule pack path for this request's dataset."""
        return self.repository_root / "rule_engine" / self.dataset_id / "rules.yaml"

    def pin_path(self) -> Path:
        """Return the dataset pin for this request's dataset."""
        return self.repository_root / "datasets" / f"{self.dataset_id}.pin.json"

    def clean_layer(self) -> Path:
        """Return the clean-layer root, defaulting beside the repository."""
        return self.clean_layer_root or (self.repository_root / ".clean")

    def reports(self) -> Path:
        """Return the reports root, defaulting to the committed docs location."""
        return self.reports_root or (self.repository_root / "docs" / "reports")


@dataclass
class PipelineState:
    """What the stages have produced so far.

    Mutable and deliberately untyped in its artifact fields (`Any`). The artifacts are
    `draft` types owned by ten different packages; naming each one here would make this
    module import all ten into its signature and would couple the execution model to
    contracts that are still moving. A stage reads what it declared it `requires` and the
    dependency check in `jobs.py` guarantees the field is populated before it runs -- so
    the typing that matters is enforced by the dependency graph, not by these annotations.
    """

    envelope: OutputEnvelope | None = None
    dataset_version: str | None = None
    row_count: int = 0
    pack: Any = None
    mapping: Any = None
    rules: Any = None
    batches: tuple[Any, ...] = ()
    entities: tuple[Any, ...] = ()
    events: tuple[Any, ...] = ()
    timelines: tuple[Any, ...] = ()
    states: tuple[Any, ...] = ()
    transitions: tuple[Any, ...] = ()
    facts: Any = None
    rule_evaluation: Any = None
    candidates: Any = None
    derived_precedence: DerivedPrecedenceIndex | None = None
    scored: Any = None
    scoring_report: Any = None
    construction: Any = None
    #: Free-form per-stage counts, rendered into the job view. Counts only -- never an
    #: artifact and never a source record.
    measurements: dict[str, int] = field(default_factory=dict)

    def require_envelope(self) -> OutputEnvelope:
        """Return the envelope, refusing if `run_identity` has not run.

        The dependency graph in `PIPELINE_STAGES` already guarantees this -- every stage
        reaching for an envelope transitively requires `run_identity` -- so this raise is
        unreachable through the job runner. It exists because the guarantee lives in data
        that a future edit could get wrong, and a stage silently building an artifact with
        no `run_id` would produce something ADR-0013 says cannot exist.
        """
        if self.envelope is None:
            raise ContractViolationError(
                "This stage reached for the output envelope before `run_identity` "
                "produced one. An artifact with no run_id is unscoped, and ADR-0013 "
                "scopes every inferred artifact to a run."
            )
        return self.envelope

    def require_dataset_version(self) -> str:
        """Return the dataset version, refusing if `run_identity` has not run."""
        if self.dataset_version is None:
            raise ContractViolationError(
                "This stage reached for the dataset version before `run_identity` "
                "resolved the pin."
            )
        return self.dataset_version


@dataclass(frozen=True)
class Stage:
    """One declared step of the pipeline.

    `not_runnable_because` is the load-bearing field. When it is set the stage is declared,
    reported, and never executed, and the string names the module that would have to exist.
    A stage that simply vanished from the list when its module was missing would make
    "nothing was produced" and "nothing could be produced" look identical.
    """

    stage_id: str
    summary: str
    requires: tuple[str, ...] = ()
    budget: BudgetName | None = None
    not_runnable_because: str | None = None
    execute: Callable[[PipelineRequest, PipelineState], None] | None = None

    @property
    def is_runnable(self) -> bool:
        """Return whether this stage has an implementation behind it today."""
        return self.not_runnable_because is None

    def run(self, request: PipelineRequest, state: PipelineState) -> None:
        """Execute the stage, or refuse if it has no implementation."""
        if self.execute is None:
            raise ContractViolationError(
                f"Stage {self.stage_id!r} has no implementation and must never be "
                f"executed: {self.not_runnable_because}"
            )
        self.execute(request, state)


# ---------------------------------------------------------------------------
# Stage bodies. Each one raises `CausaLogError` on refusal; none of them prints.
# ---------------------------------------------------------------------------


def _load_packs(request: PipelineRequest, state: PipelineState) -> None:
    """Load the ontology pack, the schema mapping, and the rule pack."""
    directory = request.pack_directory()
    loaded_pack = load_pack(directory / "ontology.yaml")
    loaded_mapping = load_mapping(directory / "mapping.yaml", loaded_pack.pack)
    loaded_rules = load_rule_pack(request.rules_path(), vocabulary=vocabulary_of(loaded_pack.pack))
    state.pack = loaded_pack
    state.mapping = loaded_mapping
    state.rules = loaded_rules


def _resolve_run(request: PipelineRequest, state: PipelineState) -> None:
    """Read the dataset pin, verify it against the mapping, and mint the `run_id`.

    This is the stage that gives the execution a `run_id`, which is why `pipeline_job.run_id`
    is nullable: before this stage there is no run to name, and minting a placeholder would
    create an identifier that addresses nothing (`CONVENTIONS.md` §9).

    A pin whose mapping hash disagrees with the loaded mapping is REFUSED rather than
    tolerated. The mapping participates in `dataset_version` and therefore in `run_id`
    (ADR-0035), so proceeding would produce artifacts stamped with a run whose inputs they
    were not built from -- ADR-0013's guarantee broken silently, which is worse than a stop.
    """
    pin_path = request.pin_path()
    if not pin_path.is_file():
        raise CausaLogError(
            f"No dataset pin at {pin_path}. A run is identified by its inputs (ADR-0013) "
            "and an unpinned source is not an input anybody can name. Run the dataset "
            "import first."
        )
    pin = json.loads(pin_path.read_text(encoding="utf-8"))["payload"]
    if mapping_hash(state.mapping.mapping) != pin["mapping_hash"]:
        raise CausaLogError(
            f"The dataset pin records mapping {pin['mapping_hash']!r} and the loaded "
            f"mapping addresses to {mapping_hash(state.mapping.mapping)!r}. The mapping "
            "participates in dataset_version and therefore in run_id (ADR-0035), so "
            "continuing would stamp artifacts with a run whose inputs they were not built "
            "from. Re-run the dataset import."
        )
    dataset_version = pin["dataset_version"]
    key = RunKey(
        dataset_version=dataset_version,
        ontology_hash=state.pack.ontology_hash,
        rule_pack_version=state.rules.rule_pack_version,
        engine_version=ENGINE_VERSION,
        seed=request.seed,
    )
    state.dataset_version = dataset_version
    state.row_count = int(pin["row_count"])
    state.envelope = OutputEnvelope(
        run_id=key.address(),
        ontology_version=state.pack.pack.ontology_version,
        ontology_hash=state.pack.ontology_hash,
        dataset_version=dataset_version,
        rule_pack_version=state.rules.rule_pack_version,
        engine_version=ENGINE_VERSION,
        graph_projection_version=UNSET,
        seed=request.seed,
        # A placeholder, replaced by `jobs.py._stamp_execution` with the real execution
        # id as soon as this stage succeeds. Present at all because an envelope is
        # required to be complete and a stage may legitimately run outside a job; derived
        # from the run rather than random so that path stays deterministic.
        execution_id=f"stage:{key.address()}",
    )


def _read_clean_layer(request: PipelineRequest, state: PipelineState) -> None:
    """Map a bounded prefix of the clean layer into `MappedRecordBatch` values."""
    dataset_version = state.require_dataset_version()
    layer = request.clean_layer() / dataset_version / "records.jsonl"
    if not layer.is_file():
        raise CausaLogError(
            f"No clean layer at {layer}. The clean layer is the ingestion output every "
            "later stage reads; without it there are no records to expand, and inventing "
            "one would be inventing data."
        )
    plan = MappingPlan.build(state.mapping.mapping)
    batches: list[MappedRecordBatch] = []
    records: list[Any] = []
    index = 0
    with layer.open(encoding="utf-8") as handle:
        for count, line in enumerate(handle):
            if request.rows and count >= request.rows:
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
                        ontology_hash=state.pack.ontology_hash,
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
                ontology_hash=state.pack.ontology_hash,
                batch_index=index,
                records=tuple(records),
            )
        )
    state.batches = tuple(batches)
    state.measurements["mapped_records"] = sum(len(batch.records) for batch in state.batches)


def _extract_entities(request: PipelineRequest, state: PipelineState) -> None:
    """Module 3. Reconcile records into entities under a declared conflict policy."""
    del request
    extractor = EntityExtractor(
        state.pack.pack,
        state.mapping.mapping,
        state.pack.ontology_hash,
        policy=ConflictPolicy.FIRST_WINS,
    )
    extraction = extractor.extract(iter(state.batches), state.require_envelope())
    state.entities = extraction.entities
    state.measurements["entities"] = len(extraction.entities)


def _generate_events(request: PipelineRequest, state: PipelineState) -> None:
    """Module 4. Expand records into events, recording gaps rather than fabricating."""
    del request
    anchor_types = {item.anchor_entity_type for item in state.pack.pack.process_definitions}
    anchors = frozenset(
        entity.entity_id for entity in state.entities if entity.entity_type in anchor_types
    )
    known = frozenset(entity.entity_id for entity in state.entities)
    generator = EventGenerator(
        state.pack.pack,
        state.mapping.mapping,
        state.pack.ontology_hash,
        missing_event_policy=MissingEventPolicy.RECORD_GAP,
    )
    streamed = generator.stream(
        lambda: iter(state.batches),
        anchors,
        known,
        state.require_envelope(),
        conflict_policy=ConflictPolicy.FIRST_WINS.value,
    )
    state.events = tuple(streamed.events)
    state.facts = FactSet.of(events=state.events)
    state.measurements["events"] = len(state.events)


def _build_timelines(request: PipelineRequest, state: PipelineState) -> None:
    """Module 5. Group events into process and entity timelines, marking gaps."""
    del request
    builder = TimelineBuilder(process_definitions_of(state.pack.pack), state.pack.ontology_hash)
    built = builder.build(state.events, state.entities, state.require_envelope())
    state.timelines = built.timelines
    state.measurements["timelines"] = len(built.timelines)


def _derive_states(request: PipelineRequest, state: PipelineState) -> None:
    """Module 6. Replay entity timelines into states and transitions.

    `scripts/build_causal_graph.py` does not run this stage -- nothing downstream of it in
    that script reads a `State`. It is run here because the API exposes state, because
    `FactSet` can carry states to the rule engine, and because a pipeline that silently
    omits a built module reports a smaller run than it performed.
    """
    del request
    engine = StateEngine(
        lifecycles_of(state.pack.pack),
        duration_measurements_of(state.pack.pack),
        state.pack.ontology_hash,
    )
    derivation = engine.derive(
        state.timelines, state.entities, state.events, state.require_envelope()
    )
    state.states = derivation.states
    state.transitions = derivation.transitions
    state.facts = FactSet.of(events=state.events, states=state.states)
    state.measurements["states"] = len(derivation.states)
    state.measurements["transitions"] = len(derivation.transitions)


def _evaluate_rules(request: PipelineRequest, state: PipelineState) -> None:
    """L5. Evaluate the rule pack against the facts assembled so far."""
    del request
    evaluation = evaluate(state.rules.pack, state.facts)
    state.rule_evaluation = evaluation
    state.measurements["rule_firings"] = len(evaluation.firings)
    state.measurements["rules_fired"] = len(evaluation.fired_rule_ids())


def _audit_derivation(request: PipelineRequest, state: PipelineState) -> None:
    """Module 1's measurement of which instants the source COMPUTED rather than recorded.

    Three outcomes, and the difference between the second and third is the whole point.
    A report that belongs to this run gives its index. No report at all is a GAP -- the
    scorer then says on every affected edge that nobody looked, which is a true statement.
    A report belonging to a DIFFERENT run raises, and must never be softened into a gap: it
    would change every score while `run_id` stayed put, so two runs bearing one identifier
    would hold different numbers.
    """
    dataset_version = state.require_dataset_version()
    path = request.reports() / request.dataset_id / dataset_version / "data-quality.json"
    if not path.is_file():
        state.derived_precedence = None
        state.measurements["derivations_confirmed"] = 0
        return
    report = from_canonical_json(DataQualityReport, path.read_text(encoding="utf-8"))
    if report.dataset_version != dataset_version:
        raise CausaLogError(
            f"{path} reports dataset version {report.dataset_version!r} and this run is "
            f"{dataset_version!r}. Scoring against another version's measurements "
            "would change every score without changing run_id."
        )
    if report.mapping_hash != mapping_hash(state.mapping.mapping):
        raise CausaLogError(
            f"{path} was written under mapping {report.mapping_hash!r} and this run uses "
            f"{mapping_hash(state.mapping.mapping)!r}. The mapping decides which columns "
            "are bound and at what precision, so its measurements do not transfer."
        )
    digest_path = path.parent / "report.sha256"
    if digest_path.is_file():
        recorded = digest_path.read_text(encoding="utf-8").strip()
        actual = report_sha256(report)
        if recorded != actual:
            raise CausaLogError(
                f"{path} does not match the digest beside it ({recorded} recorded, "
                f"{actual} computed). An edited measurement is not a measurement."
            )
    state.derived_precedence = derived_precedence_index(report.derivations)
    state.measurements["derivations_confirmed"] = len(
        state.derived_precedence.entries if state.derived_precedence else ()
    )


def _generate_candidates(request: PipelineRequest, state: PipelineState) -> None:
    """Module 9. Propose candidate causes; the LAW-TIME gate runs inside."""
    del request
    generation = generate_candidates(
        GenerationContext(
            facts=state.facts,
            timelines=state.timelines,
            parameters=state.rules.pack.candidate_generation,
            rule_evaluation=state.rule_evaluation,
            run_id=state.require_envelope().run_id,
        ),
        state.require_envelope(),
    )
    state.candidates = generation
    state.measurements["candidates"] = len(generation.graph.candidates)


def _score_candidates(request: PipelineRequest, state: PipelineState) -> None:
    """Module 10. Score every candidate into a `ConfidenceVector` with named components."""
    del request
    events_by_id = {event.event_id: event for event in state.events}
    result = score_candidates(
        state.candidates.graph.candidates,
        ScoringContext(
            facts=state.facts,
            timelines=state.timelines,
            base_rates=PairBaseRates.of(state.timelines, events_by_id),
            parameters=state.rules.pack.confidence_scoring,
            rule_evaluation=state.rule_evaluation,
            confounding_flags=state.candidates.confounding_flags,
            # Module 9 refuses a prohibited pair at its gate, so nothing prohibited
            # survives to be scored. Passed empty anyway: the scorer must not depend on an
            # upstream filter it cannot see.
            suppressed_pairs=frozenset(),
            derived_precedence=state.derived_precedence,
            proposed_pairs=frozenset(
                (candidate.source_event_id, candidate.target_event_id)
                for candidate in state.candidates.graph.candidates
            ),
            run_id=state.require_envelope().run_id,
        ),
        state.require_envelope(),
    )
    state.scored = result.graph
    state.scoring_report = result.report
    state.measurements["scored_edges"] = len(result.graph.edges)
    state.measurements["insufficient_evidence"] = result.report.insufficient_count


def _build_graph(request: PipelineRequest, state: PipelineState) -> None:
    """The Causal Graph Builder. The one place `INFERRED` is assigned (ADR-0054)."""
    del request
    construction = build_causal_graph(
        state.scored,
        GraphBuildContext(
            facts=state.facts,
            timelines=state.timelines,
            candidates=state.candidates.graph.candidates,
            parameters=state.rules.pack.graph_construction,
            bands=state.rules.pack.confidence_scoring,
            rule_evaluation=state.rule_evaluation,
            magnitude_measurements=magnitude_measurements_of(state.pack.pack),
            run_id=state.require_envelope().run_id,
        ),
        state.require_envelope(),
    )
    state.construction = construction
    state.measurements["promoted_edges"] = len(construction.graph.edges)
    state.measurements["rejected_claims"] = len(construction.graph.demotions)


#: The declared pipeline. Sequence is the execution sequence; `requires` is the truth about
#: dependency, and `jobs.py` reads `requires` rather than position so that a stage refusing
#: blocks exactly its dependents.
PIPELINE_STAGES: Final[tuple[Stage, ...]] = (
    Stage(
        stage_id="packs",
        summary="Load the ontology pack, the schema mapping and the rule pack.",
        execute=_load_packs,
    ),
    Stage(
        stage_id="run_identity",
        summary="Read the dataset pin and mint the run_id (ADR-0013).",
        requires=("packs",),
        execute=_resolve_run,
    ),
    Stage(
        stage_id="clean_layer",
        summary="Map a bounded prefix of the clean layer into records.",
        requires=("run_identity",),
        budget=BudgetName.DATASET_LOADING,
        execute=_read_clean_layer,
    ),
    Stage(
        stage_id="entities",
        summary="Module 3 -- reconcile records into entities.",
        requires=("clean_layer",),
        execute=_extract_entities,
    ),
    Stage(
        stage_id="events",
        summary="Module 4 -- expand records into events, recording gaps.",
        requires=("entities",),
        execute=_generate_events,
    ),
    Stage(
        stage_id="timelines",
        summary="Module 5 -- group events into timelines.",
        requires=("events",),
        execute=_build_timelines,
    ),
    Stage(
        stage_id="states",
        summary="Module 6 -- replay entity timelines into states and transitions.",
        requires=("timelines",),
        execute=_derive_states,
    ),
    Stage(
        stage_id="relationships",
        summary="Module 7 -- resolve structural relationships between entities.",
        requires=("states",),
        not_runnable_because=(
            "Module 7 (Relationship Resolver) is not-started. It would supply the "
            "structural Relationship values module 9's structural-path generator walks; "
            "without it that generator reports zero over zero relationships and module "
            "10's graph_connectivity component is MISSING on every edge, which costs "
            "every score rather than being renormalized away."
        ),
    ),
    Stage(
        stage_id="temporal_graph",
        summary="Module 8 -- project the temporal property graph (PRECEDES only).",
        requires=("relationships",),
        budget=BudgetName.GRAPH_GENERATION,
        not_runnable_because=(
            "Module 8 (Temporal Graph Builder) is not-started. It would write the "
            "PRECEDES projection and set graph_projection_version, which is why every "
            "envelope this pipeline produces carries 'unset' for that field rather than a "
            "plausible-looking value."
        ),
    ),
    Stage(
        stage_id="rule_evaluation",
        summary="Extension seam 4 -- evaluate the rule pack against the facts.",
        requires=("states",),
        execute=_evaluate_rules,
    ),
    Stage(
        stage_id="derivation_audit",
        summary="Module 1 -- which instants the source computed rather than recorded.",
        requires=("run_identity",),
        execute=_audit_derivation,
    ),
    Stage(
        stage_id="candidates",
        summary="Module 9 -- propose candidate causes behind the LAW-TIME gate.",
        requires=("timelines", "rule_evaluation"),
        execute=_generate_candidates,
    ),
    Stage(
        stage_id="scoring",
        summary="Module 10 -- score candidates into decomposed confidence vectors.",
        requires=("candidates", "derivation_audit"),
        execute=_score_candidates,
    ),
    Stage(
        stage_id="causal_graph",
        summary="Causal Graph Builder -- promote, or record why not (ADR-0054).",
        requires=("scoring",),
        execute=_build_graph,
    ),
    Stage(
        stage_id="explanations",
        summary="Module 15 -- render graph evidence into language.",
        requires=("causal_graph",),
        not_runnable_because=(
            "Module 15 (Explanation Generator) is not-started. It would render each "
            "assertion into sentences that cite their evidence ids, which is what the "
            "report endpoints serve; until it exists those endpoints return their "
            "envelope and say this."
        ),
    ),
)


def stage_ids() -> tuple[str, ...]:
    """Return every declared stage identifier, in execution sequence."""
    return tuple(stage.stage_id for stage in PIPELINE_STAGES)


def stage_by_id(stage_id: str) -> Stage:
    """Return one declared stage.

    Raises:
        ContractViolationError: no stage carries that identifier.
    """
    for stage in PIPELINE_STAGES:
        if stage.stage_id == stage_id:
            return stage
    raise ContractViolationError(
        f"No pipeline stage {stage_id!r}. Declared stages are {list(stage_ids())}."
    )
