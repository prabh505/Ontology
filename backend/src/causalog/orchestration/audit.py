"""Audit call sites for the `CONVENTIONS.md` §8 closed list, in one place.

Every auditable action in this distribution is reached through a named function here
rather than through a bare `AuditSink.record(...)` at a call site. The difference is that
a function can be *found*: "which code paths write an audit entry" is answerable by reading
one module, and the `action` / `target_kind` pairing for each entry is decided once instead
of being re-invented wherever somebody needed to record something.

prd.md §54 requires two distinct things and it is easy to satisfy only the first:

1. **Audit logging of every mutating action** -- a dataset accepted, a mapping submitted, a
   pipeline execution started, inferred artifacts deleted.
2. **Audit logging of every READ of a sensitive result.** `CONVENTIONS.md` §8's table names
   it explicitly: "Access to any endpoint returning inferences -- actor, role, endpoint,
   correlation_id". A read is not a change, so nothing about the data model forces it to be
   recorded; it is recorded because knowing who saw an inference is the point of an access
   audit.

`record_inference_access` is therefore the most important function in this module and the
easiest to forget to call, which is why the API layer calls it from middleware rather than
from each route: a route that forgot would be a silent hole, and middleware cannot forget.
"""

from __future__ import annotations

from causalog.core.ports.identity import Principal
from causalog.core.ports.persistence import AuditSink

__all__ = [
    "record_artifacts_deleted",
    "record_dataset_imported",
    "record_inference_access",
    "record_mapping_submitted",
    "record_pipeline_started",
]


def record_inference_access(
    sink: AuditSink,
    *,
    principal: Principal,
    endpoint: str,
    run_id: str | None,
    correlation_id: str | None,
    execution_id: str | None = None,
) -> None:
    """Record that an actor read a result carrying inference (`CONVENTIONS.md` §8).

    The `role` travels in the payload rather than in `actor`, because the two answer
    different questions and one string cannot answer both: `actor` is who, and it must stay
    stable across a role change so a person's history remains one history; `role` is the
    authority under which this particular read happened, and it is a property of the read.
    """
    sink.record(
        run_id=run_id,
        actor=principal.actor,
        action="INFERENCE_ENDPOINT_ACCESSED",
        target=endpoint,
        target_kind="endpoint",
        correlation_id=correlation_id,
        execution_id=execution_id,
        before_state=None,
        after_state=None,
        payload=(("role", principal.role.value),),
    )


def record_pipeline_started(
    sink: AuditSink,
    *,
    principal: Principal,
    execution_id: str,
    dataset_id: str,
    correlation_id: str | None,
    idempotency_key: str | None,
) -> None:
    """Record that an execution was requested. `run_id` is not yet known (see 0017)."""
    sink.record(
        run_id=None,
        actor=principal.actor,
        action="PIPELINE_EXECUTION_STARTED",
        target=execution_id,
        target_kind="execution",
        correlation_id=correlation_id,
        execution_id=execution_id,
        before_state=None,
        after_state=(("status", "PENDING"),),
        payload=(
            ("role", principal.role.value),
            ("dataset_id", dataset_id),
            ("idempotency_key", idempotency_key or ""),
        ),
    )


def record_dataset_imported(
    sink: AuditSink,
    *,
    principal: Principal,
    dataset_version: str,
    correlation_id: str | None,
    source_digest: str,
    record_count: int,
    reject_count: int,
) -> None:
    """Record a dataset import with the counts `CONVENTIONS.md` §8 requires.

    The reject count is not optional and not cosmetic: `CONVENTIONS.md` §7 says a malformed
    record is rejected and COUNTED, and an import whose audit entry omits that count cannot
    answer "what did this dataset version not contain" without re-running the import.
    """
    sink.record(
        run_id=None,
        actor=principal.actor,
        action="DATASET_IMPORTED",
        target=dataset_version,
        target_kind="dataset_version",
        correlation_id=correlation_id,
        execution_id=None,
        before_state=None,
        after_state=(("dataset_version", dataset_version),),
        payload=(
            ("role", principal.role.value),
            ("source_digest", source_digest),
            ("record_count", str(record_count)),
            ("reject_count", str(reject_count)),
        ),
    )


def record_mapping_submitted(
    sink: AuditSink,
    *,
    principal: Principal,
    dataset_version: str,
    mapping_hash: str,
    correlation_id: str | None,
) -> None:
    """Record a mapping submission against a dataset version."""
    sink.record(
        run_id=None,
        actor=principal.actor,
        action="DATASET_MAPPING_SUBMITTED",
        target=dataset_version,
        target_kind="dataset_version",
        correlation_id=correlation_id,
        execution_id=None,
        before_state=None,
        after_state=(("mapping_hash", mapping_hash),),
        payload=(("role", principal.role.value),),
    )


def record_artifacts_deleted(
    sink: AuditSink,
    *,
    principal: Principal,
    run_id: str,
    correlation_id: str | None,
    edges_removed: int,
    projection_nodes_removed: int,
    cache_entries_removed: int,
) -> None:
    """Record the deletion of a run's inferred artifacts, with what went.

    `before_state` carries the counts and `after_state` carries zeros, so the entry is
    inspectable without re-deriving it -- migration 0014's stated reason for adding the
    pair. This is the one destructive operation the API exposes, and it is destructive only
    of INFERENCE: observed facts are dataset-scoped and are not reachable from here
    (ADR-0013's scoping asymmetry), which is what makes the operation safe to offer at all.
    """
    sink.record(
        run_id=run_id,
        actor=principal.actor,
        action="INFERRED_ARTIFACTS_DELETED",
        target=run_id,
        target_kind="run",
        correlation_id=correlation_id,
        execution_id=None,
        before_state=(
            ("causal_edges", str(edges_removed)),
            ("projection_nodes", str(projection_nodes_removed)),
            ("cache_entries", str(cache_entries_removed)),
        ),
        after_state=(
            ("causal_edges", "0"),
            ("projection_nodes", "0"),
            ("cache_entries", "0"),
        ),
        payload=(("role", principal.role.value),),
    )
