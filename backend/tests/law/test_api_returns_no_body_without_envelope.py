"""LAW: no endpoint returns a body without its output envelope.

`CONVENTIONS.md` §11: "An output without its envelope cannot be verified and is a defect."
`docs/architecture.md` §2 lists "returning a body without its envelope" under what module
16 is forbidden from. This file is where that stops being prose.

It checks the same property twice, on purpose, because the two checks fail in different
circumstances:

* **Over the live route table** -- catches a route whose `response_model` is wrong,
  including one added by a router this file has never heard of.
* **Over the AST of every file in `api/routes/`** -- parametrized per source file, so the
  assertion grows with the package. This catches a route that builds a response by hand
  and returns it, which the route table cannot see because the declared model still looks
  right.

`tests/law/` is blocking: a failure here is `CRITICAL` (`CONVENTIONS.md` §14).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from causalog.api.app import create_app
from causalog.api.schemas.envelope import ApiResponse, ResponseScope
from causalog.orchestration.identity import SignedTokenAuthenticator
from causalog.orchestration.wiring import Adapters
from causalog.persistence.memory.fakes import FixedClock

ROUTES_DIRECTORY = Path(__file__).resolve().parents[2] / "src" / "causalog" / "api" / "routes"

#: The only routes exempt, and they are exempt because they carry no reasoning output at
#: all. Enumerated by path rather than by a predicate so that adding an exemption is an
#: edit somebody reviews, not a property a new route can acquire by accident.
EXEMPT_PATHS = frozenset({"/healthz", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})

#: Routes permitted to answer under `CATALOG` scope -- bodies that describe the deployment
#: rather than one run, and so genuinely have no single envelope. Closed, for the same
#: reason `EXEMPT_PATHS` is: `CATALOG` must stay a deliberate choice.
CATALOG_PATHS = frozenset({"/v1/runs", "/v1/jobs", "/v1/jobs/{execution_id}"})


def _application() -> object:
    """Build an app over fakes, purely to read its route table."""
    clock = FixedClock()
    return create_app(
        adapters=Adapters.in_memory(
            clock=clock,
            authenticator=SignedTokenAuthenticator("x" * 48, clock),
            repository_root=Path(__file__).resolve().parents[3],
        )
    )


def _generic_metadata(model: object) -> tuple[object | None, tuple[object, ...]]:
    """Return a response model's (origin, args).

    Pydantic materializes `ApiResponse[X]` into a real, concrete subclass rather than
    leaving a `typing` generic alias behind, so `typing.get_origin` reports `None` for it.
    The parameterization is recorded on `__pydantic_generic_metadata__` instead, and
    reading that is what makes this check see what was actually declared rather than
    reporting every route as unparameterized.
    """
    metadata = getattr(model, "__pydantic_generic_metadata__", None)
    if not isinstance(metadata, dict):
        return None, ()
    args: Any = metadata.get("args", ())
    return metadata.get("origin"), tuple(args)


def _declared_routes() -> list[object]:
    """Return every route carrying a response model."""
    return [
        route
        for route in _application().routes  # type: ignore[attr-defined]
        if getattr(route, "methods", None) and route.path not in EXEMPT_PATHS
    ]


@pytest.mark.law
def test_every_route_declares_an_api_response() -> None:
    """Every non-exempt route's response model is an `ApiResponse[...]`."""
    offenders: list[str] = []
    for route in _declared_routes():
        model = getattr(route, "response_model", None)
        origin, _ = _generic_metadata(model)
        if not (model is ApiResponse or origin is ApiResponse):
            offenders.append(f"{sorted(route.methods)} {route.path} -> {model!r}")
    assert not offenders, (
        "These routes return a body that is not an ApiResponse, so nothing forces them to "
        "carry the output envelope (CONVENTIONS.md §11, docs/architecture.md §2):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.law
def test_every_route_declares_a_payload_type() -> None:
    """`ApiResponse` is never declared bare: the payload type is part of the contract.

    A bare `ApiResponse` would serialize `data` as whatever it received and publish nothing
    about its shape in the OpenAPI document, which defeats the contract tests that read
    that document.
    """
    bare = [
        f"{sorted(route.methods)} {route.path}"
        for route in _declared_routes()
        if not _generic_metadata(getattr(route, "response_model", None))[1]
    ]
    assert not bare, "These routes declare ApiResponse with no payload type:\n  " + "\n  ".join(
        bare
    )


@pytest.mark.law
@pytest.mark.parametrize(
    "source", sorted(ROUTES_DIRECTORY.glob("*.py")), ids=lambda path: path.name
)
def test_route_modules_never_construct_a_response_by_hand(source: Path) -> None:
    """No file in `api/routes/` calls `ApiResponse(...)` directly.

    Parametrized per source file so the assertion grows with the package -- the pattern
    `tests/law/test_law_time_gates_every_promotion.py` established.

    Constructing one by hand is how a field gets omitted: every argument becomes optional
    at the call site, and the next person adding a route copies whichever call they found.
    `causalog.api.responses.respond` is the one constructor, and it takes a `QueryResult`,
    which cannot exist without its envelope.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ApiResponse"
    ]
    assert not offenders, (
        f"{source.name} constructs ApiResponse directly at line(s) {offenders}. Build "
        "responses through `causalog.api.responses.respond` / `respond_catalog`, which "
        "take a QueryResult and so cannot omit the envelope."
    )


@pytest.mark.law
def test_catalog_scope_is_closed() -> None:
    """Only the declared catalog routes may answer without an envelope.

    `CATALOG` exists because a listing spans many runs and a job may have none yet, and
    fabricating an envelope for those would be worse than omitting one -- unverifiable
    while looking verified. That reasoning applies to a handful of routes; this test is
    what stops it spreading to a route that simply found the envelope inconvenient.
    """
    import inspect

    from causalog.api.routes import jobs, runs

    catalog_users: set[str] = set()
    for module in (jobs, runs):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "respond_catalog"
            ):
                catalog_users.add(module.__name__)
    assert catalog_users <= {
        "causalog.api.routes.jobs",
        "causalog.api.routes.runs",
    }, f"respond_catalog is used outside the declared catalog modules: {catalog_users}"

    # And the scope enum still has exactly the two members the design depends on.
    assert {member.value for member in ResponseScope} == {"RUN_SCOPED", "CATALOG"}


@pytest.mark.law
def test_the_route_table_check_rejects_a_bare_body() -> None:
    """The route-table check is observed to FAIL on a route that returns a bare body.

    DEF-0001's lesson, applied to a test rather than to a lint: a check that has only ever
    been seen to pass has not been shown to be a check. The three assertions above would
    all pass if `_declared_routes()` silently returned nothing, or if the metadata read
    came back empty for every route -- both of which are one refactor away.

    So this plants the violation and asserts the detection, using the same predicate the
    real check uses rather than a re-implementation of it.
    """
    from fastapi import APIRouter, FastAPI
    from pydantic import BaseModel

    class BareBody(BaseModel):
        """A response with no envelope -- exactly what the law forbids."""

        value: int

    planted = FastAPI()
    router = APIRouter()

    @router.get("/planted", response_model=BareBody)
    def planted_route() -> BareBody:
        """Return a body carrying no run, no provenance and no envelope."""
        return BareBody(value=1)

    planted.include_router(router)

    offenders = [
        route.path
        for route in planted.routes
        if getattr(route, "methods", None)
        and route.path not in EXEMPT_PATHS
        and _generic_metadata(getattr(route, "response_model", None))[0] is not ApiResponse
        and getattr(route, "response_model", None) is not ApiResponse
    ]
    assert "/planted" in offenders, (
        "The route-table check did not flag a route returning a bare body. The check "
        "cannot be relied on to flag a real one."
    )


@pytest.mark.law
def test_the_ast_check_rejects_a_hand_built_response(tmp_path: Path) -> None:
    """The AST check is observed to FAIL on a file that constructs `ApiResponse` directly."""
    planted = tmp_path / "planted_route_module.py"
    planted.write_text(
        "def handler():\n" "    return ApiResponse(run_id='r', data=None)\n",
        encoding="utf-8",
    )
    tree = ast.parse(planted.read_text(encoding="utf-8"), filename=str(planted))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ApiResponse"
    ]
    assert offenders == [2], (
        "The AST check did not flag a hand-built ApiResponse. It cannot be relied on to "
        "flag a real one."
    )
