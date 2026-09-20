"""The `JobStore` adapter over the system of record (ADR-0083, migration 0017).

Two tables with two different immutability rules, and the asymmetry is deliberate:
`pipeline_stage` is append-only at the database (the 0004 trigger), while `pipeline_job`
carries a derived roll-up that legitimately changes. The roll-up is reconstructible from
the transitions, so letting it change loses nothing; making the transitions mutable would
lose the one thing the ledger exists to keep.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from causalog.core.errors import ContractViolationError
from causalog.core.ports.jobs import JobRecord, JobStatus, StageStatus, StageTransition
from causalog.persistence.postgres import sql
from causalog.persistence.postgres.connection import PostgresConnectionFactory

__all__ = ["PostgresJobStore"]


def _job_from_row(row: tuple[Any, ...]) -> JobRecord:
    """Build a `JobRecord` from `sql._PIPELINE_JOB_COLUMNS` in declared sequence."""
    return JobRecord(
        execution_id=row[0],
        run_id=row[1],
        dataset_id=row[2],
        status=JobStatus(row[3]),
        requested_by=row[4],
        correlation_id=row[5],
        idempotency_key=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


def _transition_from_row(row: tuple[Any, ...]) -> StageTransition:
    """Build a `StageTransition` from `SELECT_PIPELINE_STAGES` in declared sequence."""
    return StageTransition(
        execution_id=row[0],
        stage_id=row[1],
        status=StageStatus(row[2]),
        recorded_at=row[3],
        elapsed_seconds=row[4],
        error_code=row[5],
        detail=row[6],
    )


class PostgresJobStore:
    """Durable execution ledger. Stage transitions are appended and never revised."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        """Bind the store to a connection source."""
        self._factory = factory

    def create_job(self, record: JobRecord) -> None:
        """Append a new execution, refusing a duplicate `execution_id`.

        The statement carries `ON CONFLICT DO NOTHING` and this method then checks the
        affected row count, rather than letting the driver raise on the primary key. The
        difference is the error a caller sees: a typed `ContractViolationError` naming the
        execution, instead of a `psycopg.UniqueViolation` carrying a constraint name --
        which `CONVENTIONS.md` §7 forbids crossing a module boundary.
        """
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.INSERT_PIPELINE_JOB,
                (
                    record.execution_id,
                    record.run_id,
                    record.dataset_id,
                    record.status.value,
                    record.requested_by,
                    record.correlation_id,
                    record.idempotency_key,
                    record.created_at,
                    record.updated_at,
                ),
            )
            written = cursor.rowcount
            connection.commit()
        if written == 0:
            raise ContractViolationError(
                f"An execution already exists with execution_id "
                f"{record.execution_id!r}. An execution identifier is minted once per "
                "attempt and never reused; reusing one would merge two attempts' stage "
                "histories into a ledger that describes neither (ADR-0083)."
            )

    def job(self, execution_id: str) -> JobRecord | None:
        """Return one execution, or None when no execution has that identifier."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_PIPELINE_JOB, (execution_id,))
            row = cursor.fetchone()
        return None if row is None else _job_from_row(row)

    def jobs(self, *, limit: int, dataset_id: str | None = None) -> Iterator[JobRecord]:
        """Yield executions newest first, at most `limit`, optionally one dataset's."""
        statement = (
            sql.SELECT_PIPELINE_JOBS if dataset_id is None else sql.SELECT_PIPELINE_JOBS_FOR_DATASET
        )
        parameters: tuple[Any, ...] = (limit,) if dataset_id is None else (dataset_id, limit)
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            rows = cursor.fetchall()
        for row in rows:
            yield _job_from_row(row)

    def job_for_idempotency_key(self, key: str) -> JobRecord | None:
        """Return the execution a previous request with this key created, if any."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_PIPELINE_JOB_BY_IDEMPOTENCY_KEY, (key,))
            row = cursor.fetchone()
        return None if row is None else _job_from_row(row)

    def set_status(
        self, execution_id: str, status: JobStatus, *, run_id: str | None, at: datetime
    ) -> None:
        """Record an execution's current status, and its `run_id` once one is known."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.UPDATE_PIPELINE_JOB_STATUS,
                (status.value, run_id, at, execution_id),
            )
            written = cursor.rowcount
            connection.commit()
        if written == 0:
            raise ContractViolationError(
                f"No execution {execution_id!r} to set status on. A status recorded "
                "against an execution that was never created would leave the ledger "
                "describing an attempt with no beginning."
            )

    def append_transition(self, transition: StageTransition) -> None:
        """Append one stage transition. Never updates and never deletes."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.APPEND_PIPELINE_STAGE,
                (
                    transition.execution_id,
                    transition.stage_id,
                    transition.status.value,
                    transition.recorded_at,
                    transition.elapsed_seconds,
                    transition.error_code,
                    transition.detail,
                ),
            )
            connection.commit()

    def transitions(self, execution_id: str) -> Iterator[StageTransition]:
        """Yield every transition for an execution, oldest first."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_PIPELINE_STAGES, (execution_id,))
            rows = cursor.fetchall()
        for row in rows:
            yield _transition_from_row(row)

    def remember_response(
        self,
        *,
        idempotency_key: str,
        endpoint: str,
        actor: str,
        request_digest: str,
        response_status: int,
        response_body: str,
        correlation_id: str | None,
    ) -> None:
        """Store what a mutating request already returned, so a retry replays it."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.INSERT_IDEMPOTENCY_RECORD,
                (
                    idempotency_key,
                    endpoint,
                    actor,
                    request_digest,
                    response_status,
                    response_body,
                    correlation_id,
                ),
            )
            connection.commit()

    def remembered_response(
        self, *, idempotency_key: str, endpoint: str, actor: str
    ) -> tuple[str, int, str] | None:
        """Return `(request_digest, status, body)` a key already produced, or None."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_IDEMPOTENCY_RECORD, (idempotency_key, endpoint, actor))
            row = cursor.fetchone()
        if row is None:
            return None
        return (row[0], row[1], json.dumps(row[2], sort_keys=True, separators=(",", ":")))
