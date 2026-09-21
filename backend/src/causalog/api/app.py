"""The ASGI application: routers, middleware, and the adapters bound to them.

This file assembles module 16. It deliberately declares **no route of its own** beyond
mounting the routers -- the constraint its earlier version stated ("adding a route that
returns reasoning output to this file is a defect") still holds, and mounting a router
respects it: the routes live in `causalog.api.routes` and reach reasoning only through
`causalog.orchestration` (F5).

`create_app` takes its adapters rather than building them. There is no lazy default, and
that is the point: a default would connect to whatever happened to be configured in the
environment, which is how a test suite writes to a real database once.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from causalog import ENGINE_VERSION
from causalog.api.routes import (
    analysis,
    counterfactuals,
    datasets,
    health,
    introspection,
    jobs,
    runs,
)
from causalog.api.schemas.errors import ApiError, error_for
from causalog.api.security.context import CORRELATION_HEADER, new_correlation_id
from causalog.core.errors import CausaLogError
from causalog.orchestration.facade import EngineFacade
from causalog.orchestration.wiring import Adapters, is_production

__all__ = ["create_app"]

_ROUTERS = (
    health.router,
    jobs.router,
    datasets.router,
    runs.router,
    analysis.router,
    introspection.router,
    counterfactuals.router,
)


def create_app(*, adapters: Adapters, facade: EngineFacade | None = None) -> FastAPI:
    """Build the application around a set of adapters."""
    app = FastAPI(
        title="CausaLog",
        version=ENGINE_VERSION,
        description=(
            "A domain-agnostic causal intelligence engine. Every response carries its "
            "run, its provenance, its evidence references and its confidence "
            "decomposition; no endpoint returns a confidence without its components."
        ),
    )
    app.state.adapters = adapters
    app.state.facade = facade if facade is not None else EngineFacade()

    for router in _ROUTERS:
        app.include_router(router)

    _install_error_handling(app)
    _install_correlation(app)
    return app


def _install_correlation(app: FastAPI) -> None:
    """Echo the correlation id on every response, including refusals.

    On EVERY response is the part that matters. A correlation id present on success and
    absent on failure is useless precisely when it is needed: production error bodies
    carry no engine detail (ADR-0085), so the id is the only thing connecting a caller's
    report to the log line that explains it.
    """

    @app.middleware("http")
    async def correlate(
        request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]
    ) -> JSONResponse:
        correlation_id = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response


def _install_error_handling(app: FastAPI) -> None:
    """Map every failure onto the typed taxonomy, and never leak internals.

    Three handlers, covering the three ways a request can fail:

    * A `CausaLogError` -- the engine refused. Mapped to its declared status, with the
      engine's own message outside production and the fixed public sentence inside it.
    * A `RequestValidationError` -- the request was malformed. Rendered as a
      `ContractViolationError`-shaped body so that a client sees one error vocabulary
      rather than two, and so that pydantic's own error structure (which names internal
      field paths) never reaches a caller in production.
    * Anything else -- an unexpected exception. Always 500, always the same body, and the
      detail goes to the log under the correlation id. This is the handler that makes "no
      stack traces in production responses" true regardless of what raised.
    """

    @app.exception_handler(CausaLogError)
    async def engine_error(request: Request, failure: CausaLogError) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        status, body = error_for(failure, correlation_id=correlation_id, production=is_production())
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, failure: RequestValidationError) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        detail = (
            "The request does not match the published schema."
            if is_production()
            else f"The request does not match the published schema: {failure.errors()}"
        )
        body = ApiError(
            error_code="ContractViolationError",
            message=detail,
            remediation=("Check the request against the OpenAPI document served at /openapi.json."),
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(StarletteHTTPException)
    async def transport_failure(request: Request, failure: StarletteHTTPException) -> JSONResponse:
        # `detail` is already an `ApiError` payload when raised by this package's
        # dependencies; anything else (a 404 from the router, say) is given one here so
        # that a client never has to branch on two error shapes.
        correlation_id = getattr(request.state, "correlation_id", None)
        # Starlette annotates `detail` as `str`, but `HTTPException` accepts any JSON-able
        # value and this package's dependencies raise it holding an `ApiError` payload.
        # The cast states that, rather than restructuring the dependencies to fit an
        # annotation that is narrower than the class it describes.
        detail: object = cast("object", failure.detail)
        if isinstance(detail, dict):
            return JSONResponse(status_code=failure.status_code, content=detail)
        body = ApiError(
            error_code="HttpError",
            message=str(detail),
            remediation="Check the request path and method against /openapi.json.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=failure.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, failure: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        body = ApiError(
            error_code="InternalError",
            message=(
                "The request could not be completed. Report the correlation id; the "
                "detail is in the server log and is deliberately not in this response."
            ),
            remediation="Report the correlation id to an operator.",
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))
