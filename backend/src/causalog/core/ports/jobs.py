"""`JobStore` -- the append-only ledger of a pipeline execution and its stages.

A Run (ADR-0013) is a set of INPUTS. It says nothing about the attempt that consumed them:
which stages ran, which refused, how long each took, and where to resume after a restart.
That is an execution, identified by `execution_id`, and it needs somewhere durable to
live.

It lives in PostgreSQL, not Redis. `docs/architecture.md` §3 states the decision rule in
one line -- "if losing it would change an answer, it belongs in PostgreSQL; if losing it
would only change how fast an answer arrives, it belongs in Redis" -- and losing a stage
ledger changes an answer: a resumed job would re-run stages that already committed facts,
or skip stages that never did. ADR-0083 records the ruling.

The ledger is **append-only**, like `audit_log` and every fact table (migration 0004's
`causalog_refuse_mutation()` trigger). A stage's history is the sequence of transitions it
went through; the current status is the newest transition, derived rather than stored. A
mutable status column would make "this stage was retried" unrepresentable, and a retry
that leaves no trace is the failure mode a job ledger exists to prevent.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

__all__ = [
    "JobRecord",
    "JobStatus",
    "JobStore",
    "StageStatus",
    "StageTransition",
]


class JobStatus(Enum):
    """The state of one pipeline execution as a whole.

    `PARTIAL` is the load-bearing member and is not a synonym for `FAILED`. A stage that
    refuses does not abort the execution: its dependents are blocked and every independent
    stage still runs (ADR-0083, failure isolation). An execution that produced six of nine
    stages' artifacts has produced something, and reporting that as `FAILED` would throw
    away work that is on disk and valid.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class StageStatus(Enum):
    """The state of one stage within an execution.

    `NOT_RUNNABLE` is distinct from `FAILED` and from `SKIPPED`, and the distinction is the
    whole point. A stage whose owning module has not been built yet did not fail and was
    not skipped by a policy -- it cannot run, and the reason is a fact about this
    repository rather than about this execution. It mirrors the exit-2 `NOT-YET-RUNNABLE`
    convention every enforcement script in `scripts/` already uses: a gate that cannot run
    must never look like a gate that passed.

    `BLOCKED` is what failure isolation produces: this stage was runnable and its
    prerequisite was not satisfied, so it never started.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NOT_RUNNABLE = "NOT_RUNNABLE"


class StageTransition(BaseModel):
    """One immutable entry in a stage's history.

    `elapsed_seconds` is present only on a terminal transition and is excluded from every
    determinism comparison (`CONVENTIONS.md` §11 excludes performance measurements). It is
    measured, not estimated: per-stage timing is a prd.md §55 obligation and an estimate
    would discharge it in appearance only.

    `detail` carries the human-readable reason for a non-`SUCCEEDED` terminal status --
    which module is missing for `NOT_RUNNABLE`, which prerequisite for `BLOCKED`, which
    error taxonomy member for `FAILED`. It never carries a traceback and never echoes a
    source record (`CONVENTIONS.md` §7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    stage_id: str
    status: StageStatus
    recorded_at: datetime
    elapsed_seconds: float | None = None
    error_code: str | None = None
    detail: str | None = None


class JobRecord(BaseModel):
    """One pipeline execution, as the ledger knows it.

    `run_id` is nullable because it is not known until the packs, the pin and the seed have
    been resolved -- which is stage one's job. An execution that refuses before that point
    has an `execution_id` and no `run_id`, and recording a placeholder would mint an
    identifier that addresses nothing (`CONVENTIONS.md` §9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    run_id: str | None
    dataset_id: str
    status: JobStatus
    requested_by: str
    correlation_id: str | None
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime


@runtime_checkable
class JobStore(Protocol):
    """Durable, append-only storage for executions and their stage histories."""

    def create_job(self, record: JobRecord) -> None:
        """Append a new execution. Re-creating an existing `execution_id` is refused.

        Raises:
            ContractViolationError: an execution with this `execution_id` already exists.
        """
        ...

    def job(self, execution_id: str) -> JobRecord | None:
        """Return one execution, or `None` when no execution has that identifier."""
        ...

    def jobs(self, *, limit: int, dataset_id: str | None = None) -> Iterator[JobRecord]:
        """Yield executions newest first, at most `limit`, optionally one dataset's."""
        ...

    def job_for_idempotency_key(self, key: str) -> JobRecord | None:
        """Return the execution a previous request with this key created, if any.

        This is what makes `POST` safe to retry: the second request with a given key
        returns the first request's execution rather than starting a second one.
        """
        ...

    def set_status(
        self, execution_id: str, status: JobStatus, *, run_id: str | None, at: datetime
    ) -> None:
        """Record an execution's current status, and its `run_id` once one is known."""
        ...

    def append_transition(self, transition: StageTransition) -> None:
        """Append one stage transition. Never updates and never deletes."""
        ...

    def transitions(self, execution_id: str) -> Iterator[StageTransition]:
        """Yield every transition for an execution, oldest first.

        Oldest first because the sequence IS the history: a caller reconstructs the current
        status by folding it, and reversing the sequence would make that fold wrong in a
        way no type could catch.
        """
        ...
