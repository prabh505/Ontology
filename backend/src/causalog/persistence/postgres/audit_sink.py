"""The append-only audit trail (`CONVENTIONS.md` §8, prd.md §54).

Separate from logging and durable. Logs are for diagnosis and rotate; this is a record and
does not. The distinction matters because prd.md §54 lists audit logging beside dataset
versioning and immutable event history as a *product* requirement, not an operational one.

THE LAW-EVIDENCE HOOK, which is what makes this table more than a diary: it must be
possible, from an audit record alone, to reconstruct why a confidence number has the value
it has. That is why `record` takes `target` and `target_kind` rather than only a free-text
message: an entry naming `edg:9f2c…` resolves back to the edge, to its components, and to
the evidence records behind each of them. An entry that says "scored an edge" does not,
and the module that wrote it is not done.

`before_state` / `after_state` are canonical pairs rather than free text so a change is
inspectable without re-deriving it. `before_state` is None for a creation -- a meaningful
absence, and deliberately not an empty object, which would read as "it was empty before".
"""

from __future__ import annotations

import json
from typing import Final

from causalog.core.errors import ContractViolationError
from causalog.persistence.postgres import sql
from causalog.persistence.postgres.connection import PostgresConnectionFactory

__all__ = ["AUDITABLE_ACTIONS", "PostgresAuditSink"]

#: The closed action list of `CONVENTIONS.md` §8. Closed rather than free text so a reader
#: can filter the trail without parsing prose, and so a new auditable action is a
#: deliberate addition here rather than a string someone invented at a call site.
AUDITABLE_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "DATASET_IMPORTED",
        "ONTOLOGY_CHANGED",
        "RULE_SET_CHANGED",
        "CAUSAL_EDGE_INFERRED",
        "RECOMMENDATION_PRODUCED",
        "COUNTERFACTUAL_RUN",
        "INFERENCE_ENDPOINT_ACCESSED",
        "STATE_RETRACTED",
        "PROJECTION_REBUILT",
    }
)


class PostgresAuditSink:
    """Appends immutable audit entries. Never updates, never deletes."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        """Bind the sink to a connection source."""
        self._factory = factory

    def record(
        self,
        *,
        run_id: str | None,
        actor: str,
        action: str,
        target: str,
        target_kind: str,
        correlation_id: str | None = None,
        execution_id: str | None = None,
        before_state: tuple[tuple[str, str], ...] | None = None,
        after_state: tuple[tuple[str, str], ...] | None = None,
        payload: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """Append one entry.

        `correlation_id` is what prd.md §54 calls a request id. One concept gets one name
        (`CONTEXT.md` §5), and the synonym is recorded in `docs/data-model.md` rather than
        minted as a second column.
        """
        if action not in AUDITABLE_ACTIONS:
            raise ContractViolationError(
                f"{action!r} is not in the closed auditable-action list "
                f"({sorted(AUDITABLE_ACTIONS)}). An audit trail whose vocabulary anyone "
                "may extend at a call site cannot be filtered or reconciled "
                "(CONVENTIONS.md §8)."
            )
        if not actor.strip():
            raise ContractViolationError(
                "An audit entry with no actor cannot discharge prd.md §54, which requires "
                "role-based access AND audit logging: an unattributed entry records that "
                "something happened and not who did it."
            )
        if not target.strip():
            raise ContractViolationError(
                f"Audit action {action!r} names no target. An entry that cannot be "
                "resolved back to the artifact it describes cannot satisfy the "
                "LAW-EVIDENCE hook (CONVENTIONS.md §8)."
            )

        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.INSERT_AUDIT_ENTRY,
                (
                    run_id,
                    action,
                    action,
                    target,
                    target_kind,
                    actor,
                    correlation_id,
                    execution_id,
                    _canonical_json(before_state),
                    _canonical_json(after_state),
                    _canonical_json(payload) or "{}",
                ),
            )
            connection.commit()


def _canonical_json(pairs: tuple[tuple[str, str], ...] | None) -> str | None:
    """Render name/value pairs as JSON with sorted keys, or None.

    Sorted keys because two audit entries describing the same change must be byte-identical
    (`CONVENTIONS.md` §11); an unsorted object would differ by dict ordering and make a
    determinism diff report a change that did not happen. None passes through as SQL NULL,
    which is the meaningful "there was no before state" rather than an empty object.
    """
    if pairs is None:
        return None
    return json.dumps(dict(pairs), sort_keys=True, separators=(",", ":"))
