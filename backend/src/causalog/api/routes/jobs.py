"""Async pipeline execution: start one, poll it, list them (prd.md §55's long operations).

The split between this file and `analysis.py` is the synchronous/asynchronous line the task
of building this API turns on. A root-cause query is bounded by prd.md §55 at three seconds
and is answered in the request. A pipeline execution is not bounded at all -- on the
reference dataset the measured import alone is about 105 seconds -- so it is a job with an
identifier, and the client polls.

**Idempotency is enforced by the database, not by a check here.** `POST /v1/jobs` carries an
`Idempotency-Key`; migration 0017 puts a partial UNIQUE index on
`pipeline_job.idempotency_key`. A read-then-write check in this handler would race two
concurrent retries into two executions of the same request, which is the one failure
idempotency exists to prevent.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from causalog.api.dependencies import AdaptersDep, ClockDep, FacadeDep, requires
from causalog.api.responses import respond_catalog
from causalog.api.schemas.envelope import ApiResponse
from causalog.api.security.authorization import Capability
from causalog.api.security.context import RequestContext
from causalog.orchestration import audit, caching, views
from causalog.orchestration.jobs import (
    current_stage_statuses,
    new_execution_id,
    new_job_record,
    run_job,
)
from causalog.orchestration.stages import PIPELINE_STAGES, PipelineRequest
from causalog.orchestration.timing import TimingMeta
from causalog.orchestration.wiring import Adapters

__all__ = ["router"]

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

ExecuteDep = Annotated[RequestContext, Depends(requires(Capability.EXECUTE_PIPELINE))]
ReadDep = Annotated[RequestContext, Depends(requires(Capability.READ_OBSERVED))]


class StartJobRequest(BaseModel):
    """What a caller supplies to start one pipeline execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    #: `0` removes the bound. The default matches the committed bounded run so that a job
    #: started with no opinion produces numbers comparable with the committed reports.
    rows: int = Field(default=150, ge=0)
    seed: int = 0


def _job_view(adapters: Adapters, execution_id: str) -> views.JobView:
    """Render one execution from the ledger alone.

    From the LEDGER, not from an in-memory job object, which is what makes the job endpoint
    survive a restart: the transitions are in PostgreSQL, so a process that did not run the
    job can still report on it.
    """
    record = adapters.jobs.job(execution_id)
    if record is None:
        raise KeyError(execution_id)
    transitions = list(adapters.jobs.transitions(execution_id))
    statuses = current_stage_statuses(adapters.jobs, execution_id)
    stages: list[views.JobStageView] = []
    for stage in PIPELINE_STAGES:
        mine = [item for item in transitions if item.stage_id == stage.stage_id]
        terminal = mine[-1] if mine else None
        started = next((item for item in mine if item.status.value == "RUNNING"), None)
        stages.append(
            views.JobStageView(
                stage_id=stage.stage_id,
                status=(
                    statuses[stage.stage_id].value if stage.stage_id in statuses else "PENDING"
                ),
                requires=stage.requires,
                started_at=started.recorded_at if started else None,
                finished_at=terminal.recorded_at if terminal else None,
                elapsed_seconds=terminal.elapsed_seconds if terminal else None,
                error_code=terminal.error_code if terminal else None,
                detail=terminal.detail if terminal else None,
            )
        )
    runnable = [stage for stage in PIPELINE_STAGES if stage.is_runnable]
    completed = sum(
        1
        for stage in runnable
        if stage.stage_id in statuses and statuses[stage.stage_id].value == "SUCCEEDED"
    )
    measured = [item.elapsed_seconds for item in transitions if item.elapsed_seconds]
    return views.JobView(
        execution_id=record.execution_id,
        run_id=record.run_id,
        dataset_id=record.dataset_id,
        status=record.status.value,
        requested_by=record.requested_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        stages=tuple(stages),
        runnable_stage_count=len(runnable),
        completed_stage_count=completed,
        not_runnable_stage_count=len(PIPELINE_STAGES) - len(runnable),
        total_elapsed_seconds=sum(measured) if measured else None,
    )


@router.post("", response_model=ApiResponse[views.JobView], status_code=202)
def start_job(
    body: StartJobRequest,
    background: BackgroundTasks,
    adapters: AdaptersDep,
    facade: FacadeDep,
    clock: ClockDep,
    context: ExecuteDep,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> ApiResponse[views.JobView]:
    """Accept a pipeline execution and return 202 with its identifier.

    202, not 201: nothing is created yet that the caller can read in full. The execution
    exists and has an identifier; its artifacts do not.

    A repeated `Idempotency-Key` returns the ORIGINAL execution rather than starting a
    second one, and the lookup happens before anything is written.
    """
    if idempotency_key:
        existing = adapters.jobs.job_for_idempotency_key(idempotency_key)
        if existing is not None:
            return respond_catalog(
                _job_view(adapters, existing.execution_id),
                clock=clock,
                timing=TimingMeta.measured(operation="start_job", elapsed_seconds=0.0, budget=None),
                provenance=views.provenance_summary(()),
            )

    execution_id = new_execution_id()
    adapters.jobs.create_job(
        new_job_record(
            execution_id=execution_id,
            dataset_id=body.dataset_id,
            requested_by=context.principal.actor,
            correlation_id=context.correlation_id,
            idempotency_key=idempotency_key,
            clock=adapters.clock,
        )
    )
    audit.record_pipeline_started(
        adapters.audit,
        principal=context.principal,
        execution_id=execution_id,
        dataset_id=body.dataset_id,
        correlation_id=context.correlation_id,
        idempotency_key=idempotency_key,
    )

    def execute() -> None:
        """Run the pipeline and file its artifacts, then invalidate the run's cache."""
        request = PipelineRequest(
            dataset_id=body.dataset_id,
            repository_root=adapters.repository_root,
            rows=body.rows,
            seed=body.seed,
        )
        outcome = run_job(
            store=adapters.jobs,
            clock=adapters.clock,
            request=request,
            execution_id=execution_id,
        )
        if outcome.state.envelope is not None:
            run_id = facade.remember(outcome.state, at=adapters.clock.now_utc())
            # A new execution against an existing run recomputes everything downstream, so
            # any cached answer for that run predates it. One of `caching.invalidate_run`'s
            # three declared triggers.
            caching.invalidate_run(adapters.cache, run_id)

    background.add_task(execute)
    return respond_catalog(
        _job_view(adapters, execution_id),
        clock=clock,
        timing=TimingMeta.measured(operation="start_job", elapsed_seconds=0.0, budget=None),
        provenance=views.provenance_summary(()),
    )


@router.get("", response_model=ApiResponse[tuple[views.JobView, ...]])
def list_jobs(
    adapters: AdaptersDep, clock: ClockDep, context: ReadDep, limit: int = 20
) -> ApiResponse[tuple[views.JobView, ...]]:
    """List recent executions, newest first."""
    del context
    rendered = tuple(
        _job_view(adapters, record.execution_id) for record in adapters.jobs.jobs(limit=limit)
    )
    return respond_catalog(
        rendered,
        clock=clock,
        timing=TimingMeta.measured(operation="list_jobs", elapsed_seconds=0.0, budget=None),
        provenance=views.provenance_summary(()),
    )


@router.get("/{execution_id}", response_model=ApiResponse[views.JobView])
def read_job(
    execution_id: str, adapters: AdaptersDep, clock: ClockDep, context: ReadDep
) -> ApiResponse[views.JobView]:
    """Return one execution's stage-by-stage progress and timing."""
    del context
    return respond_catalog(
        _job_view(adapters, execution_id),
        clock=clock,
        timing=TimingMeta.measured(operation="read_job", elapsed_seconds=0.0, budget=None),
        provenance=views.provenance_summary(()),
    )
