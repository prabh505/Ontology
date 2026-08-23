"""The ASGI application object.

This module exists so the backend container has something to run and something to report
health on. It is **not** module 16: no endpoint here returns a reasoning result, and the
prd.md §53 surface lands with the Visualization API.

Adding a route that returns reasoning output to this file is a defect -- routes belong in
`causalog.api.routes`, and they reach reasoning only through `causalog.orchestration` (F5).
"""

from __future__ import annotations

from fastapi import FastAPI

from causalog import ENGINE_VERSION

app = FastAPI(
    title="CausaLog",
    version=ENGINE_VERSION,
    description="A domain-agnostic causal intelligence engine.",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Report liveness and the engine version.

    The engine version participates in every `run_id` (ADR-0013), so reporting it here
    makes "which engine produced this?" answerable from the running container.
    """
    return {"status": "ok", "engine_version": ENGINE_VERSION}
