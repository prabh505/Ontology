"""Typed, actionable errors that never leak internals.

Three requirements meet here and they pull in different directions:

* `CONVENTIONS.md` §7 wants an error to "name the offending identifier, the module, and the
  contract violated" -- rich, specific, diagnosable.
* prd.md §54's hardening wants no stack traces in production responses.
* `CONVENTIONS.md` §7 also forbids any message from carrying a raw source record.

The resolution is that the engine's messages are already written to satisfy the first and
the third: a `CausaLogError` names identifiers and contracts and cites evidence ids rather
than reproducing records. So those messages are safe to return **outside** production, and
in production they are replaced -- not truncated, not sanitized by pattern-matching, which
is a game nobody wins -- by a fixed sentence per taxonomy member. `is_production()`
defaults to True precisely so that a deployment nobody configured gets the quiet behaviour.

**The mapping is closed and total.** Every member of `core.errors`'s taxonomy has exactly
one status here. A new error class with no entry raises at import time rather than
defaulting to 500: a default would mean the first caller to hit a new failure mode learns
about it as an opaque server error, which is the opposite of actionable.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.errors import (
    CausaLogError,
    ContractViolationError,
    DataQualityError,
    LawViolationError,
    OntologyMappingError,
    ProjectionStaleError,
    RuleConflictError,
)
from causalog.orchestration.facade import RunNotAvailableError

__all__ = [
    "ERROR_STATUS",
    "PUBLIC_MESSAGES",
    "ApiError",
    "ErrorCode",
    "error_for",
    "status_for",
    "transport_error",
]

#: The closed error vocabulary a client may branch on. String-valued and stable: a client
#: that switches on `error_code` must not have to parse prose, and prose is the one part of
#: an error this API reserves the right to change.
ErrorCode = str

#: `CausaLogError` subclass -> HTTP status. Total over the taxonomy; see `status_for`.
#:
#: The two choices worth defending:
#:
#: * `ProjectionStaleError` is **409**, not 503. `docs/architecture.md` §6.2 shows it as a
#:   409 "naming the version requested", and the distinction is real: the store is up and
#:   answering, and what is wrong is that the caller asked for a version it is not serving.
#:   A 503 would tell a client to retry the identical request, which cannot succeed.
#: * `LawViolationError` is **500**, and it is the only member that is. A law violation is
#:   a programming error in this engine (`CONVENTIONS.md` §7 calls these "CRITICAL"), never
#:   something the caller did. Returning 4xx would blame the client for our defect.
ERROR_STATUS: Final[dict[type[CausaLogError], int]] = {
    ContractViolationError: 422,
    OntologyMappingError: 422,
    DataQualityError: 422,
    RuleConflictError: 409,
    ProjectionStaleError: 409,
    RunNotAvailableError: 404,
    LawViolationError: 500,
}

#: What a production response says instead of the engine's own message. One sentence per
#: taxonomy member, each actionable on its own: a client reading only this should know
#: whether to fix the request, wait, or report a bug.
PUBLIC_MESSAGES: Final[dict[type[CausaLogError], str]] = {
    ContractViolationError: (
        "The request violates an interface contract. Check the request against the "
        "published schema; the same request will not succeed on retry."
    ),
    OntologyMappingError: (
        "A value in this request or dataset has no concept in the active ontology. The "
        "ontology is never defaulted or guessed, so the value must be declared before it "
        "can be processed."
    ),
    DataQualityError: (
        "The data behind this request did not meet a stated quality requirement. Consult "
        "the run's data quality report."
    ),
    RuleConflictError: (
        "The active rule pack contradicts itself and was refused at load time. A rule set "
        "that contradicts itself is never resolved by a runtime coin-flip."
    ),
    ProjectionStaleError: (
        "The graph projection requested is not the version being served. A stale "
        "projection is never served as if it were current; rebuild the projection or "
        "request the version now available."
    ),
    RunNotAvailableError: (
        "That run is not materialized in this process. Start a pipeline execution for the "
        "same inputs to materialize it."
    ),
    LawViolationError: (
        "The engine refused to produce a result because doing so would have violated one "
        "of its own invariants. This is a defect in the engine, not in the request; "
        "please report it with the correlation id."
    ),
}

#: The remedies for failures that never reach the engine at all.
_TRANSPORT_MESSAGES: Final[dict[int, tuple[str, str]]] = {
    401: (
        "UNAUTHENTICATED",
        "No valid credential was presented. Supply a signed token in the Authorization " "header.",
    ),
    403: (
        "FORBIDDEN",
        "The authenticated role is not permitted this operation. The permission matrix is "
        "published in docs/api.md.",
    ),
    409: (
        "IDEMPOTENCY_KEY_REUSED",
        "This idempotency key was already used for a different request body. Reusing a key "
        "with different content is refused rather than served the earlier response.",
    ),
    429: (
        "RATE_LIMITED",
        "The request budget for this caller and endpoint class is exhausted. Retry after "
        "the interval named in retry_after_seconds.",
    ),
}


class ApiError(BaseModel):
    """One refusal, in the shape a client can act on.

    `correlation_id` is on every error, and it is the field that makes a production
    response debuggable without being revealing: the caller reports the id, and an operator
    reads the full engine message out of the structured log and the audit trail, where
    `CONVENTIONS.md` §8 already threads it through.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_code: ErrorCode = Field(min_length=1)
    message: str = Field(min_length=1)
    remediation: str = Field(min_length=1)
    correlation_id: str | None = None
    #: Present only on 429. A 429 without it leaves every client to guess the same wrong
    #: interval at the same moment.
    retry_after_seconds: int | None = None


def _declared_type(failure: CausaLogError) -> type[CausaLogError]:
    """Return the declared taxonomy member governing this error.

    Exact type first, then the MRO. The MRO walk is what makes the mapping total over
    subclasses without listing them: `RunNotAvailableError` is declared, and a future
    subclass of it would resolve to its parent's status rather than to a default. Walking
    the MRO rather than scanning the dict also makes the resolution independent of
    insertion sequence, so adding an entry cannot silently re-route an existing one.

    Raises:
        KeyError: no ancestor of this error is declared. Deliberately not defaulted to 500
            -- an undeclared failure mode should be found by the test that enumerates the
            taxonomy, not by the first caller to trigger it.
    """
    for candidate in type(failure).__mro__:
        if candidate in ERROR_STATUS:
            return candidate
    raise KeyError(
        f"{type(failure).__name__} has no declared HTTP status. Add it to ERROR_STATUS: "
        "the taxonomy in core/errors.py is closed (CONVENTIONS.md §7), so a member with no "
        "mapping is an omission rather than a case to default."
    )


def status_for(failure: CausaLogError) -> int:
    """Return the HTTP status for an engine error."""
    return ERROR_STATUS[_declared_type(failure)]


def error_for(
    failure: CausaLogError, *, correlation_id: str | None, production: bool
) -> tuple[int, ApiError]:
    """Render an engine error as a status and a body.

    Outside production the engine's own message is returned, because it is written to name
    the identifier and the contract and is the fastest way to a diagnosis. In production it
    is replaced wholesale by the fixed sentence for its taxonomy member -- replaced, not
    filtered, because deciding sentence by sentence what is safe to reveal is a judgement
    that will eventually be made wrong.
    """
    declared = _declared_type(failure)
    public = PUBLIC_MESSAGES[declared]
    return ERROR_STATUS[declared], ApiError(
        error_code=declared.__name__,
        message=public if production else str(failure),
        remediation=public,
        correlation_id=correlation_id,
    )


def transport_error(
    status: int, *, correlation_id: str | None, retry_after_seconds: int | None = None
) -> ApiError:
    """Render a failure that never reached the engine: auth, permissions, limits."""
    code, remedy = _TRANSPORT_MESSAGES[status]
    return ApiError(
        error_code=code,
        message=remedy,
        remediation=remedy,
        correlation_id=correlation_id,
        retry_after_seconds=retry_after_seconds,
    )
