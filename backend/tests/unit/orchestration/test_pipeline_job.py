"""The job runner: dependency correctness, failure isolation, and resumption.

These are unit tests over the stage machinery with synthetic stages, not over the real
pipeline. That is the point: the real pipeline's stages either all succeed or refuse for
reasons about data, and neither exercises what this file is about -- what happens when a
stage in the MIDDLE fails. A synthetic pipeline can plant that failure exactly.
"""

from __future__ import annotations

import pytest

from causalog.core.errors import CausaLogError, ContractViolationError
from causalog.core.ports.jobs import JobStatus, StageStatus
from causalog.orchestration.jobs import (
    current_stage_statuses,
    new_execution_id,
    new_job_record,
    run_job,
    stages_to_run,
)
from causalog.orchestration.stages import (
    PIPELINE_STAGES,
    PipelineRequest,
    PipelineState,
    Stage,
    stage_by_id,
    stage_ids,
)
from causalog.persistence.memory.fakes import FixedClock, InMemoryJobStore


@pytest.fixture
def request_() -> PipelineRequest:
    """A request no synthetic stage reads."""
    from pathlib import Path

    return PipelineRequest(dataset_id="synthetic", repository_root=Path("/nonexistent"))


def _store_with_job(clock: FixedClock) -> tuple[InMemoryJobStore, str]:
    """Return a store holding one PENDING execution."""
    store = InMemoryJobStore()
    execution_id = new_execution_id()
    store.create_job(
        new_job_record(
            execution_id=execution_id,
            dataset_id="synthetic",
            requested_by="tester",
            correlation_id=None,
            idempotency_key=None,
            clock=clock,
        )
    )
    return store, execution_id


def _record(name: str, log: list[str]) -> object:
    """Return a stage body that records that it ran."""

    def execute(request: PipelineRequest, state: PipelineState) -> None:
        del request, state
        log.append(name)

    return execute


def _refuse(message: str) -> object:
    """Return a stage body that refuses with a typed engine error."""

    def execute(request: PipelineRequest, state: PipelineState) -> None:
        del request, state
        raise ContractViolationError(message)

    return execute


# -- the declared pipeline itself -------------------------------------------------------


def test_stage_ids_are_unique() -> None:
    """Two stages sharing an id would collapse into one row in the ledger."""
    assert len(set(stage_ids())) == len(PIPELINE_STAGES)


def test_every_requirement_names_a_declared_stage() -> None:
    """A `requires` naming nothing would block its stage forever, silently."""
    declared = set(stage_ids())
    for stage in PIPELINE_STAGES:
        for requirement in stage.requires:
            assert (
                requirement in declared
            ), f"Stage {stage.stage_id!r} requires {requirement!r}, which is not declared."


def test_the_dependency_graph_is_acyclic_and_topologically_sequenced() -> None:
    """Every stage appears after everything it requires.

    The runner reads `requires` rather than position, so a mis-sequenced list would not
    produce wrong results -- it would produce a stage BLOCKED on a prerequisite that runs
    later, which reads as a data problem. Asserting the sequence keeps the declaration
    honest about its own execution order.
    """
    seen: set[str] = set()
    for stage in PIPELINE_STAGES:
        for requirement in stage.requires:
            assert requirement in seen, (
                f"Stage {stage.stage_id!r} is declared before its prerequisite " f"{requirement!r}."
            )
        seen.add(stage.stage_id)


def test_unrunnable_stages_carry_a_reason_and_no_body() -> None:
    """A declared-but-unbuilt stage names its module and cannot be executed."""
    for stage in PIPELINE_STAGES:
        if stage.is_runnable:
            assert stage.execute is not None
        else:
            assert stage.execute is None
            assert stage.not_runnable_because


def test_running_an_unrunnable_stage_is_refused() -> None:
    """Calling `run` on a declared-but-unbuilt stage raises rather than no-ops."""
    stage = stage_by_id("explanations")
    with pytest.raises(ContractViolationError, match="no implementation"):
        stage.run(
            PipelineRequest(dataset_id="x", repository_root=__import__("pathlib").Path(".")),
            PipelineState(),
        )


def test_stage_by_id_names_the_alternatives() -> None:
    """An unknown stage id is refused with the declared set, not a bare KeyError."""
    with pytest.raises(ContractViolationError, match="Declared stages"):
        stage_by_id("no-such-stage")


# -- execution --------------------------------------------------------------------------


def test_a_clean_run_succeeds_and_records_every_stage(request_: PipelineRequest) -> None:
    """Every stage succeeds, the execution is SUCCEEDED, and timing is recorded."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    log: list[str] = []
    stages = (
        Stage(stage_id="a", summary="first", execute=_record("a", log)),
        Stage(stage_id="b", summary="second", requires=("a",), execute=_record("b", log)),
    )
    outcome = run_job(
        store=store, clock=clock, request=request_, execution_id=execution_id, stages=stages
    )
    assert outcome.status is JobStatus.SUCCEEDED
    assert log == ["a", "b"]
    assert set(outcome.elapsed_seconds) == {"a", "b"}
    assert store.job(execution_id).status is JobStatus.SUCCEEDED


def test_a_failure_blocks_dependents_and_spares_independents(
    request_: PipelineRequest,
) -> None:
    """Failure isolation, which is the whole reason the pipeline is a graph.

    `b` depends on the failing `a` and is BLOCKED. `c` does not and still runs. The
    execution is PARTIAL rather than FAILED, because `c`'s work exists and is valid.
    """
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    log: list[str] = []
    stages = (
        Stage(stage_id="a", summary="fails", execute=_refuse("planted refusal")),
        Stage(stage_id="b", summary="depends on a", requires=("a",), execute=_record("b", log)),
        Stage(stage_id="c", summary="independent", execute=_record("c", log)),
    )
    outcome = run_job(
        store=store, clock=clock, request=request_, execution_id=execution_id, stages=stages
    )

    assert outcome.statuses["a"] is StageStatus.FAILED
    assert outcome.statuses["b"] is StageStatus.BLOCKED
    assert outcome.statuses["c"] is StageStatus.SUCCEEDED
    assert log == ["c"], "A blocked stage ran anyway, over inputs that do not exist."
    assert outcome.status is JobStatus.PARTIAL, (
        "An execution that produced some artifacts reported FAILED, discarding work that "
        "is on disk and valid."
    )


def test_a_total_failure_is_failed_not_partial(request_: PipelineRequest) -> None:
    """`PARTIAL` would be a euphemism when nothing succeeded."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    stages = (Stage(stage_id="a", summary="fails", execute=_refuse("planted")),)
    outcome = run_job(
        store=store, clock=clock, request=request_, execution_id=execution_id, stages=stages
    )
    assert outcome.status is JobStatus.FAILED


def test_a_failed_stage_records_its_taxonomy_member_and_no_traceback(
    request_: PipelineRequest,
) -> None:
    """The ledger names the error class and the message, never a stack trace."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    stages = (Stage(stage_id="a", summary="fails", execute=_refuse("planted refusal")),)
    run_job(store=store, clock=clock, request=request_, execution_id=execution_id, stages=stages)
    terminal = [t for t in store.transitions(execution_id) if t.status is StageStatus.FAILED]
    assert len(terminal) == 1
    assert terminal[0].error_code == "ContractViolationError"
    assert terminal[0].detail == "planted refusal"
    assert "Traceback" not in (terminal[0].detail or "")


def test_unrunnable_stages_are_recorded_before_anything_runs(
    request_: PipelineRequest,
) -> None:
    """A client polling a fresh job sees the whole pipeline shape immediately."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    stages = (
        Stage(
            stage_id="missing", summary="unbuilt", not_runnable_because="Module N is not-started."
        ),
        Stage(stage_id="a", summary="runs", execute=_record("a", [])),
    )
    outcome = run_job(
        store=store, clock=clock, request=request_, execution_id=execution_id, stages=stages
    )
    assert outcome.statuses["missing"] is StageStatus.NOT_RUNNABLE
    assert outcome.status is JobStatus.SUCCEEDED, (
        "An unbuilt module made the execution look damaged. NOT_RUNNABLE stages are "
        "excluded from the judgement, or every execution here would be permanently PARTIAL."
    )


def test_resumption_skips_succeeded_stages_and_retries_the_rest(
    request_: PipelineRequest,
) -> None:
    """A resumed execution re-runs what failed and leaves what succeeded alone."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    log: list[str] = []

    failing = (
        Stage(stage_id="a", summary="ok", execute=_record("a", log)),
        Stage(stage_id="b", summary="fails", requires=("a",), execute=_refuse("planted")),
    )
    run_job(store=store, clock=clock, request=request_, execution_id=execution_id, stages=failing)
    assert log == ["a"]

    repaired = (
        Stage(stage_id="a", summary="ok", execute=_record("a", log)),
        Stage(stage_id="b", summary="now ok", requires=("a",), execute=_record("b", log)),
    )
    outcome = run_job(
        store=store, clock=clock, request=request_, execution_id=execution_id, stages=repaired
    )
    assert log == [
        "a",
        "b",
    ], "Resumption re-ran a SUCCEEDED stage, or failed to retry the FAILED one."
    assert outcome.status is JobStatus.SUCCEEDED


def test_stages_to_run_skips_only_succeeded() -> None:
    """A BLOCKED or FAILED stage is retried; a NOT_RUNNABLE one never is."""
    stages = (
        Stage(stage_id="ok", summary="", execute=_record("ok", [])),
        Stage(stage_id="bad", summary="", execute=_record("bad", [])),
        Stage(stage_id="unbuilt", summary="", not_runnable_because="Module N is not-started."),
    )
    chosen = stages_to_run({"ok": StageStatus.SUCCEEDED, "bad": StageStatus.FAILED}, stages)
    assert [stage.stage_id for stage in chosen] == ["bad"]


def test_the_ledger_folds_to_the_latest_transition(request_: PipelineRequest) -> None:
    """Current status is the newest transition, so a retry is visible as history."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    stages = (Stage(stage_id="a", summary="fails", execute=_refuse("planted")),)
    run_job(store=store, clock=clock, request=request_, execution_id=execution_id, stages=stages)
    repaired = (Stage(stage_id="a", summary="ok", execute=_record("a", [])),)
    run_job(store=store, clock=clock, request=request_, execution_id=execution_id, stages=repaired)

    statuses = current_stage_statuses(store, execution_id)
    assert statuses["a"] is StageStatus.SUCCEEDED
    history = [t.status for t in store.transitions(execution_id) if t.stage_id == "a"]
    assert StageStatus.FAILED in history, (
        "The retry overwrote the failure. A retry that leaves no trace is what the "
        "append-only ledger exists to prevent."
    )


def test_a_stage_refusal_never_escapes_the_runner(request_: PipelineRequest) -> None:
    """A refusal is a recorded outcome, not an exception the caller must translate."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    stages = (Stage(stage_id="a", summary="fails", execute=_refuse("planted")),)
    try:
        run_job(
            store=store, clock=clock, request=request_, execution_id=execution_id, stages=stages
        )
    except CausaLogError as failure:  # pragma: no cover -- the assertion is the point
        pytest.fail(f"A stage refusal escaped the runner: {failure}")


def test_duplicate_execution_ids_are_refused() -> None:
    """Two attempts must never share a ledger."""
    clock = FixedClock()
    store, execution_id = _store_with_job(clock)
    with pytest.raises(ContractViolationError, match="already exists"):
        store.create_job(
            new_job_record(
                execution_id=execution_id,
                dataset_id="synthetic",
                requested_by="tester",
                correlation_id=None,
                idempotency_key=None,
                clock=clock,
            )
        )
