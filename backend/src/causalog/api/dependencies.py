"""FastAPI dependencies: the only place a route acquires anything.

A route handler here takes its dependencies as parameters and reaches for nothing. That is
what keeps `docs/architecture.md` §2's "forbidden from computing anything that changes a
conclusion" true in practice rather than in intent -- a handler with no way to reach a
store or a reasoning package cannot drift into using one.

**Where the read audit happens, and why it is here.** `CONVENTIONS.md` §8 requires an audit
entry for "access to any endpoint returning inferences". Putting that call in each handler
makes it forgettable, and a forgotten one is silent. It lives in `requires(...)`, the
dependency every route must declare to name its capability: a route with no capability does
not authorize at all and fails the test that enumerates the route table, so there is no way
to add an inference endpoint that skips the audit. Middleware was the alternative and is
worse here -- it would have to infer from the path whether a response carried inference,
and that inference would be wrong the first time a path was renamed.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any, Final

from fastapi import Depends, Header, HTTPException, Request

from causalog.api.schemas.errors import transport_error
from causalog.api.security.authorization import Capability, permitted
from causalog.api.security.context import (
    RequestContext,
    new_correlation_id,
)
from causalog.core.errors import CausaLogError
from causalog.core.ports.clock import Clock
from causalog.core.ports.identity import Principal
from causalog.orchestration import audit
from causalog.orchestration.facade import EngineFacade
from causalog.orchestration.wiring import Adapters

__all__ = [
    "AUDITED_CAPABILITIES",
    "RATE_LIMITS",
    "adapters_of",
    "clock_of",
    "facade_of",
    "requires",
    "standing_guard",
]

#: The capabilities whose exercise is an "access to an endpoint returning inferences"
#: (`CONVENTIONS.md` §8). `READ_OBSERVED` is absent on purpose: a fact is not an inference,
#: and auditing every read of observed data would bury the entries that matter under the
#: ones that do not, which is how an audit trail stops being read.
AUDITED_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {
        Capability.READ_INFERRED,
        Capability.READ_DIAGNOSTIC,
        Capability.READ_EVIDENCE,
        Capability.READ_RECOMMENDATIONS,
        Capability.SIMULATE,
    }
)

#: Requests per window, per caller, per capability class. Simulation is tightest because it
#: is the most expensive call on this surface -- module 14 simulates once per candidate and
#: again per multi-node set -- and one caller looping it would push everybody else past the
#: prd.md §55 budgets. Numbers are deployment policy and are published in `docs/api.md`.
RATE_LIMITS: Final[dict[Capability, tuple[int, int]]] = {
    Capability.SIMULATE: (30, 60),
    Capability.EXECUTE_PIPELINE: (10, 60),
    Capability.MUTATE_DATASET: (30, 60),
    Capability.DELETE_INFERRED: (10, 60),
}

#: Everything not named above.
_DEFAULT_RATE_LIMIT: Final[tuple[int, int]] = (300, 60)


def adapters_of(request: Request) -> Adapters:
    """Return the adapters bound to this application."""
    bundle = getattr(request.app.state, "adapters", None)
    if isinstance(bundle, Adapters):
        return bundle
    if bundle is None:
        raise RuntimeError(
            "No adapters are bound to this application. Build it with "
            "`causalog.api.app.create_app(adapters=...)`; there is deliberately no "
            "lazy default, because a default would silently connect to whatever store "
            "happened to be configured in the environment."
        )
    raise RuntimeError(f"app.state.adapters holds {type(bundle).__name__}, not Adapters.")


def clock_of(request: Request) -> Clock:
    """Return the clock bound to this application.

    A dependency rather than a module-level `datetime.now`, for the reason ADR-0014 made
    time a port: this is the one instant in a response that a determinism test would
    otherwise be unable to hold still.
    """
    return adapters_of(request).clock


def facade_of(request: Request) -> EngineFacade:
    """Return the engine facade bound to this application."""
    engine = getattr(request.app.state, "facade", None)
    if isinstance(engine, EngineFacade):
        return engine
    raise RuntimeError(
        "No engine facade is bound to this application. Build it with "
        "`causalog.api.app.create_app(...)`."
    )


def _authenticate(request: Request, authorization: str | None, correlation_id: str) -> Principal:
    """Resolve the caller, or refuse with a 401 that reveals nothing.

    Every refusal is the same 401 body whatever went wrong, while the specific reason goes
    to the structured log under the correlation id. Distinguishing "no credential" from
    "bad signature" from "expired" in the RESPONSE tells an unauthenticated caller which
    of its guesses was closest, which is the one thing a 401 should not do.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail=transport_error(401, correlation_id=correlation_id).model_dump(mode="json"),
        )
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(
            status_code=401,
            detail=transport_error(401, correlation_id=correlation_id).model_dump(mode="json"),
        )
    adapters = adapters_of(request)
    try:
        return adapters.authenticator.authenticate(credential)
    except CausaLogError as failure:
        raise HTTPException(
            status_code=401,
            detail=transport_error(401, correlation_id=correlation_id).model_dump(mode="json"),
        ) from failure


def requires(
    capability: Capability, *, audit_access: bool = True
) -> Callable[..., Coroutine[Any, Any, RequestContext]]:
    """Build the dependency a route uses to declare what it needs.

    Every route declares exactly one. The dependency does four things in a fixed sequence,
    and the sequence matters:

    1. **Correlate** -- so that everything after this, including the refusals, is traceable.
    2. **Authenticate** -- 401 before anything else looks at the request.
    3. **Authorize** -- 403 against the published matrix.
    4. **Rate limit** -- after authorization, deliberately. Limiting before authorizing
       would let an unauthorized caller consume an authorized caller's budget, and would
       leak the existence of endpoints through 429-versus-403.

    The read audit is written once authorization succeeds. It records the attempt that was
    *permitted*; a refused attempt is a 403 in the log, not an inference access, because no
    inference was disclosed.

    `audit_access=False` is for the one case where THIS dependency is not the last word on
    authorization: `standing_guard` composes it and then applies a second check, so a
    caller can still be refused after this returns. Auditing here would record an inference
    access for a request that ends in a 403 -- which is worse than a missing row, because a
    trail that claims disclosures that did not happen cannot be relied on for the ones that
    did. The guard writes the row itself once it has decided.
    """

    async def dependency(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_correlation_id: Annotated[str | None, Header()] = None,
    ) -> RequestContext:
        # Read the id the correlation middleware already minted, rather than minting a
        # second one. They were separate until a test compared an audit row against the
        # response header and found two different values for one request -- which silently
        # defeats `audit_log_by_correlation_idx`, whose justifying query is "everything one
        # API request did" (migration 0014). The middleware runs before routing, so this is
        # always populated; the fallbacks exist for a dependency exercised outside the ASGI
        # stack, where there is no middleware to have run.
        correlation_id = (
            getattr(request.state, "correlation_id", None)
            or x_correlation_id
            or new_correlation_id()
        )
        principal = _authenticate(request, authorization, correlation_id)
        endpoint = f"{request.method} {request.scope.get('route_path', request.url.path)}"

        if not permitted(principal.role, capability):
            raise HTTPException(
                status_code=403,
                detail=transport_error(403, correlation_id=correlation_id).model_dump(mode="json"),
            )

        adapters = adapters_of(request)
        if adapters.limiter is not None:
            limit, window = RATE_LIMITS.get(capability, _DEFAULT_RATE_LIMIT)
            verdict = adapters.limiter.consume(
                bucket=f"{principal.actor}:{capability.value}",
                limit=limit,
                window_seconds=window,
            )
            if not verdict.allowed:
                raise HTTPException(
                    status_code=429,
                    detail=transport_error(
                        429,
                        correlation_id=correlation_id,
                        retry_after_seconds=verdict.retry_after_seconds,
                    ).model_dump(mode="json"),
                )

        context = RequestContext(
            principal=principal, correlation_id=correlation_id, endpoint=endpoint
        )
        if audit_access and capability in AUDITED_CAPABILITIES:
            audit.record_inference_access(
                adapters.audit,
                principal=principal,
                endpoint=endpoint,
                run_id=request.path_params.get("run_id"),
                correlation_id=correlation_id,
            )
        return context

    return dependency


async def standing_guard(
    request: Request,
    context: Annotated[
        RequestContext,
        Depends(requires(Capability.READ_INFERRED, audit_access=False)),
    ],
) -> RequestContext:
    """Refuse the diagnostic standing to a caller without `READ_DIAGNOSTIC`.

    This closes a hole that a per-route capability alone leaves open. An endpoint that
    serves both standings can only declare ONE capability, and declaring `READ_INFERRED`
    would let any role that may read inferences also request the `UNPROMOTED_DIAGNOSTIC`
    view -- output the engine explicitly disowns (ADR-0059), which the matrix deliberately
    withholds from `EXECUTIVE` because OQ-026's risk is a disowned figure quoted as a
    finding and an executive summary is where that does the most damage.

    The check reads the query parameter rather than the handler's argument because it must
    run BEFORE the handler: authorization that happens after the work is done has already
    let the work happen.
    """
    diagnostic = request.query_params.get("standing") == "UNPROMOTED_DIAGNOSTIC"
    if diagnostic and not permitted(context.principal.role, Capability.READ_DIAGNOSTIC):
        raise HTTPException(
            status_code=403,
            detail=transport_error(403, correlation_id=context.correlation_id).model_dump(
                mode="json"
            ),
        )
    # Audited HERE rather than in `requires`, because this is the point at which the
    # request is certain to be served. Auditing before this check would record an
    # inference access for a request that ends in a 403 -- worse than a missing row,
    # because a trail claiming disclosures that did not happen cannot be relied on for
    # the ones that did.
    audit.record_inference_access(
        adapters_of(request).audit,
        principal=context.principal,
        endpoint=context.endpoint,
        run_id=request.path_params.get("run_id"),
        correlation_id=context.correlation_id,
    )
    return context


#: Convenience aliases so a route signature reads as a declaration rather than as plumbing.
AdaptersDep = Annotated[Adapters, Depends(adapters_of)]
ClockDep = Annotated[Clock, Depends(clock_of)]
FacadeDep = Annotated[EngineFacade, Depends(facade_of)]
#: For endpoints that serve both standings. Carries the `READ_INFERRED` check and the
#: diagnostic escalation check together, so a route cannot take one without the other.
InferenceDep = Annotated[RequestContext, Depends(standing_guard)]
