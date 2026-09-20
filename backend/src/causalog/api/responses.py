"""The one function that turns a facade result into a response body.

Every route calls `respond`. Nothing in `api/routes/` constructs an `ApiResponse` directly,
and a law test asserts that over the AST -- because a handler that built one by hand would
be a handler that could omit a field, and the whole point of the envelope is that no
endpoint can.

`generated_at` is read from the `Clock` port rather than from `datetime.now()`. That looks
excessive for a display timestamp until you notice the alternative: a wall-clock read here
would be the one place in the request path a test could not control, and
`tests/determinism/test_api_responses_are_stable.py` compares two bodies for byte-identity
with only the declared exclusions removed.
"""

from __future__ import annotations

from typing import TypeVar

from causalog.api.schemas.envelope import ApiResponse, ResponseScope
from causalog.core.ports.clock import Clock
from causalog.orchestration.facade import QueryResult
from causalog.orchestration.timing import TimingMeta, log_slow_operation
from causalog.orchestration.views import (
    GraphStandingView,
    ProvenanceSummary,
    StageStatusView,
)

__all__ = ["respond", "respond_catalog"]

PayloadT = TypeVar("PayloadT")

_DIAGNOSTIC_NOTICE = (
    "DISOWNED. This was walked over the scored graph BEFORE promotion. The engine does "
    "not assert it, nothing here is INFERRED, and a figure quoted from it without this "
    "notice is being quoted as something it is not (ADR-0059, OQ-026)."
)


def respond(
    result: QueryResult[PayloadT], *, clock: Clock, correlation_id: str | None = None
) -> ApiResponse[PayloadT]:
    """Assemble the response body for a facade result, and log it if it was slow.

    The slow-query log is written here rather than in middleware for the reason the read
    audit is written in the dependency: this is where the budget and the measurement are
    both in hand. Middleware measures the whole request including serialization, which is
    a different number from the one prd.md §55 bounds, and logging that against a §55
    budget would make the log quietly wrong.
    """
    log_slow_operation(result.timing, run_id=result.envelope.run_id, correlation_id=correlation_id)
    body: ApiResponse[PayloadT] = ApiResponse(
        scope=ResponseScope.RUN_SCOPED,
        run_id=result.envelope.run_id,
        envelope=result.envelope,
        provenance=result.provenance,
        standing=result.standing,
        stage_status=result.stage_status,
        timing=result.timing,
        generated_at=clock.now_utc(),
        data=result.data,
        evidence=result.evidence,
        confidence=result.confidence,
        stage_detail=result.stage_detail,
        standing_notice=(
            _DIAGNOSTIC_NOTICE
            if result.standing is GraphStandingView.UNPROMOTED_DIAGNOSTIC
            else None
        ),
    )
    return body.check_conditional_fields()


def respond_catalog(
    data: PayloadT,
    *,
    clock: Clock,
    timing: TimingMeta,
    provenance: ProvenanceSummary,
) -> ApiResponse[PayloadT]:
    """Assemble a body that describes the deployment rather than one run's output.

    Separate from `respond` on purpose. Making it a flag on one function would mean a
    caller could pass the flag to silence the envelope check on a body that genuinely is
    run-scoped -- which is precisely the failure the check exists to catch. Two functions
    means choosing `CATALOG` is a visible edit, and the routes that may make it are
    enumerated by a test.
    """
    return ApiResponse(
        scope=ResponseScope.CATALOG,
        run_id=None,
        envelope=None,
        provenance=provenance,
        standing=GraphStandingView.STATED,
        stage_status=StageStatusView.COMPLETE,
        timing=timing,
        generated_at=clock.now_utc(),
        data=data,
    ).check_conditional_fields()
