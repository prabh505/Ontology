"""Executing the declared pipeline as a resumable job, and writing its ledger.

`stages.py` says what the pipeline IS. This module runs it, and everything here is about
the three properties a command-line function could not offer: resumption, failure
isolation, and per-stage timing.

**Failure isolation, stated precisely.** A stage that refuses is recorded `FAILED` with
its error taxonomy member. Every stage that transitively `requires` it is recorded
`BLOCKED`, naming the prerequisite. Every other stage still runs. The execution then ends
`PARTIAL` rather than `FAILED`, because six stages' artifacts are on disk and calling that
a failure throws away work that exists and is valid. `FAILED` is reserved for an execution
where nothing succeeded at all -- there, "partial" would be a euphemism.

**Resumption, stated precisely.** `resume_job` folds the ledger into a per-stage status and
re-runs only what has not SUCCEEDED. It re-runs `BLOCKED` and `FAILED` stages, because the
reason either happened may have been repaired between attempts; it never re-runs a
`SUCCEEDED` one. What it does NOT do is carry `PipelineState` across a restart: the
artifacts live in memory, so a resumed execution replays the stages that produced the
inputs its remaining stages need. That is a real cost and it is recorded rather than hidden
-- resumption here saves the work of stages whose outputs nothing further needs, and does
not yet save the work of stages whose outputs do.

**Timing.** Every stage is measured with `time.perf_counter`, and the number goes into the
ledger. `CONVENTIONS.md` §11 excludes performance measurements from determinism
comparisons, so these values never enter a content address and never make two runs of one
Run differ.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Final

from causalog.core.errors import CausaLogError
from causalog.core.ports.clock import Clock
from causalog.core.ports.jobs import (
    JobRecord,
    JobStatus,
    JobStore,
    StageStatus,
    StageTransition,
)
from causalog.orchestration.stages import (
    PIPELINE_STAGES,
    PipelineRequest,
    PipelineState,
    Stage,
)

__all__ = [
    "JobOutcome",
    "current_stage_statuses",
    "new_execution_id",
    "new_job_record",
    "run_job",
    "stages_to_run",
]

_LOGGER: Final[logging.Logger] = logging.getLogger("causalog.orchestration.jobs")


def new_execution_id() -> str:
    """Mint a per-execution identifier.

    `uuid4` is correct here and is the one place in this distribution where randomness is.
    `CONVENTIONS.md` §9 bans random identifiers "anywhere in the reasoning pipeline" and
    then names the two exceptions explicitly: `execution_id` and `correlation_id`, both
    excluded from every determinism comparison. An execution is not content-addressable by
    construction -- two attempts at identical inputs are different attempts and must be
    distinguishable, which is exactly what `run_id` cannot do (ADR-0013).
    """
    return f"exec:{uuid.uuid4().hex}"


@dataclass(frozen=True)
class JobOutcome:
    """What one execution did: its final status, its state, and its per-stage results."""

    execution_id: str
    status: JobStatus
    state: PipelineState
    statuses: dict[str, StageStatus]
    elapsed_seconds: dict[str, float]


def current_stage_statuses(store: JobStore, execution_id: str) -> dict[str, StageStatus]:
    """Fold an execution's transitions into one status per stage.

    Last transition wins, which is why `JobStore.transitions` is specified oldest-first: a
    reversed sequence would report the FIRST transition as current and make a retried stage
    look like it was still running.
    """
    statuses: dict[str, StageStatus] = {}
    for transition in store.transitions(execution_id):
        statuses[transition.stage_id] = transition.status
    return statuses


def stages_to_run(
    already: dict[str, StageStatus], stages: tuple[Stage, ...] = PIPELINE_STAGES
) -> tuple[Stage, ...]:
    """Return the stages a (re)start must execute.

    A `SUCCEEDED` stage is skipped. `FAILED` and `BLOCKED` stages are re-run, because what
    caused either may have been repaired between attempts -- a missing clean layer written,
    a stale pin refreshed. A `NOT_RUNNABLE` stage is never returned: nothing about a
    restart builds a module.
    """
    return tuple(
        stage
        for stage in stages
        if stage.is_runnable and already.get(stage.stage_id) is not StageStatus.SUCCEEDED
    )


def _blocking_prerequisite(
    stage: Stage, statuses: dict[str, StageStatus]
) -> tuple[str, StageStatus] | None:
    """Return the first prerequisite that is not SUCCEEDED, or None.

    Checked against recorded statuses rather than against `PipelineState` fields, so a
    stage cannot run on a half-populated state: the dependency graph is the guarantee that
    `state.events` is non-empty before `timelines` reads it, and a state-field check would
    make an empty-but-successful stage look like a missing one.
    """
    for requirement in stage.requires:
        status = statuses.get(requirement)
        if status is not StageStatus.SUCCEEDED:
            return (requirement, status or StageStatus.PENDING)
    return None


def run_job(
    *,
    store: JobStore,
    clock: Clock,
    request: PipelineRequest,
    execution_id: str,
    state: PipelineState | None = None,
    stages: tuple[Stage, ...] = PIPELINE_STAGES,
) -> JobOutcome:
    """Execute (or resume) one pipeline job, writing every transition to the ledger.

    Never raises for a stage refusal: a refusal is a recorded outcome, not an exception the
    caller has to translate. It does propagate a failure to WRITE the ledger, because an
    execution whose history is not being recorded has lost the only thing that survives the
    container, and continuing would produce artifacts nobody can trace.
    """
    working = state if state is not None else PipelineState()
    statuses = current_stage_statuses(store, execution_id)
    elapsed: dict[str, float] = {}

    # Declared-but-unbuilt stages are recorded once per execution, before anything runs, so
    # a client polling a fresh job sees the full pipeline shape immediately rather than
    # watching stages appear.
    for stage in stages:
        if not stage.is_runnable and stage.stage_id not in statuses:
            statuses[stage.stage_id] = StageStatus.NOT_RUNNABLE
            store.append_transition(
                StageTransition(
                    execution_id=execution_id,
                    stage_id=stage.stage_id,
                    status=StageStatus.NOT_RUNNABLE,
                    recorded_at=clock.now_utc(),
                    detail=stage.not_runnable_because,
                )
            )

    store.set_status(execution_id, JobStatus.RUNNING, run_id=None, at=clock.now_utc())

    for stage in stages_to_run(statuses, stages):
        blocker = _blocking_prerequisite(stage, statuses)
        if blocker is not None:
            requirement, status = blocker
            statuses[stage.stage_id] = StageStatus.BLOCKED
            store.append_transition(
                StageTransition(
                    execution_id=execution_id,
                    stage_id=stage.stage_id,
                    status=StageStatus.BLOCKED,
                    recorded_at=clock.now_utc(),
                    detail=(
                        f"Prerequisite {requirement!r} is {status.value}, so this stage "
                        "never started. Its inputs do not exist; running it would either "
                        "fail on an empty state or, worse, succeed over one."
                    ),
                )
            )
            continue

        store.append_transition(
            StageTransition(
                execution_id=execution_id,
                stage_id=stage.stage_id,
                status=StageStatus.RUNNING,
                recorded_at=clock.now_utc(),
            )
        )
        started = time.perf_counter()
        try:
            stage.run(request, working)
        except CausaLogError as failure:
            duration = time.perf_counter() - started
            elapsed[stage.stage_id] = duration
            statuses[stage.stage_id] = StageStatus.FAILED
            # `type(failure).__name__` is the closed taxonomy member (CONVENTIONS.md §7),
            # and `str(failure)` is the module's own message -- which that section requires
            # to name the offending identifier and the contract violated, and forbids from
            # carrying a raw record. Neither is a traceback: a ledger is read by operators,
            # and a stack trace in it is an internal detail with a long life.
            store.append_transition(
                StageTransition(
                    execution_id=execution_id,
                    stage_id=stage.stage_id,
                    status=StageStatus.FAILED,
                    recorded_at=clock.now_utc(),
                    elapsed_seconds=duration,
                    error_code=type(failure).__name__,
                    detail=str(failure),
                )
            )
            # `exception` rather than `error`: the traceback goes to the LOG, where a
            # developer diagnosing an incident needs it. It goes nowhere else -- not into
            # the ledger's `detail`, which operators read, and not into any response body,
            # which `CONVENTIONS.md` §7 forbids from leaking internals.
            _LOGGER.exception(
                "stage_failed",
                extra={
                    "execution_id": execution_id,
                    "stage_id": stage.stage_id,
                    "error_code": type(failure).__name__,
                },
            )
            continue

        duration = time.perf_counter() - started
        elapsed[stage.stage_id] = duration
        statuses[stage.stage_id] = StageStatus.SUCCEEDED
        _stamp_execution(working, execution_id)
        store.append_transition(
            StageTransition(
                execution_id=execution_id,
                stage_id=stage.stage_id,
                status=StageStatus.SUCCEEDED,
                recorded_at=clock.now_utc(),
                elapsed_seconds=duration,
            )
        )

    outcome = _final_status(statuses, stages)
    run_id = working.envelope.run_id if working.envelope is not None else None
    store.set_status(execution_id, outcome, run_id=run_id, at=clock.now_utc())
    return JobOutcome(
        execution_id=execution_id,
        status=outcome,
        state=working,
        statuses=statuses,
        elapsed_seconds=elapsed,
    )


def _stamp_execution(state: PipelineState, execution_id: str) -> None:
    """Put the real `execution_id` on the envelope, once one exists.

    The `run_identity` stage builds the envelope before it knows which ATTEMPT is running
    -- a stage can legitimately be executed outside a job, and an envelope is required to
    be complete -- so it fills `execution_id` with a value derived from the run. That
    placeholder must not survive into an artifact: `CONVENTIONS.md` §9 makes `execution_id`
    the per-execution identifier, and two attempts at one run sharing it would make their
    artifacts indistinguishable, which is precisely what `run_id` already cannot do
    (ADR-0013).

    `stages.py` claimed this happened from the day it was written and it did not. The
    symptom was benign and misleading in the worst way: the determinism gate PASSED without
    needing its `execution_id` exclusion, because the field was stable when it was supposed
    to be volatile. A gate passing for the wrong reason is the DEF-0001 shape.
    """
    if state.envelope is None or state.envelope.execution_id == execution_id:
        return
    state.envelope = state.envelope.model_copy(update={"execution_id": execution_id})


def _final_status(statuses: dict[str, StageStatus], stages: tuple[Stage, ...]) -> JobStatus:
    """Roll per-stage statuses into the execution's status.

    `NOT_RUNNABLE` stages are excluded from the judgement entirely. Including them would
    make every execution on this repository permanently `PARTIAL` -- three modules are
    unbuilt -- which would say something about the repository while pretending to say
    something about the execution, and would make the field useless for its actual job of
    distinguishing a clean run from a damaged one.
    """
    runnable = [stage.stage_id for stage in stages if stage.is_runnable]
    if not runnable:
        return JobStatus.SUCCEEDED
    observed = [statuses.get(stage_id, StageStatus.PENDING) for stage_id in runnable]
    succeeded = sum(1 for status in observed if status is StageStatus.SUCCEEDED)
    if succeeded == len(runnable):
        return JobStatus.SUCCEEDED
    if succeeded == 0:
        return JobStatus.FAILED
    return JobStatus.PARTIAL


def new_job_record(
    *,
    execution_id: str,
    dataset_id: str,
    requested_by: str,
    correlation_id: str | None,
    idempotency_key: str | None,
    clock: Clock,
) -> JobRecord:
    """Build the ledger row for a newly requested execution.

    `run_id` is None and stays None until the `run_identity` stage resolves one. See
    migration 0017's comment on that column: a placeholder would be an identifier that
    addresses nothing.
    """
    now = clock.now_utc()
    return JobRecord(
        execution_id=execution_id,
        run_id=None,
        dataset_id=dataset_id,
        status=JobStatus.PENDING,
        requested_by=requested_by,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        created_at=now,
        updated_at=now,
    )
