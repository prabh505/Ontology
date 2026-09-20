"""Liveness and the API contract version. Unauthenticated, and deliberately minimal.

These two endpoints carry no envelope and no reasoning output, which is why they are the
only routes in this package exempt from the envelope law -- and why they are in a file of
their own, so that the exemption is a property of a named, tiny module rather than a
special case scattered among the reasoning routes. The law test enumerates them by name.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from causalog import ENGINE_VERSION

__all__ = ["API_SCHEMA_VERSION", "router"]

#: The version of the API SHELL -- routes, envelope, error taxonomy, pagination, the auth
#: and role contract, idempotency and job shapes. Frozen at 1.0.0 by ADR-0085.
#:
#: It is emphatically NOT the version of the payload bodies. Those are owned by the modules
#: that produce them and are still `draft` in `CONTEXT.md` §6; three of their owning modules
#: do not exist. Freezing them here would be the assertion-not-specification error OQ-009
#: exists to prevent, committed in a new place.
API_SCHEMA_VERSION: Final[str] = "1.0.0"

router = APIRouter(tags=["meta"])


class HealthView(BaseModel):
    """What a health probe reports."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    engine_version: str
    api_schema_version: str


@router.get("/healthz", response_model=HealthView)
def healthz() -> HealthView:
    """Report liveness, the engine version, and the frozen API shell version.

    The engine version participates in every `run_id` (ADR-0013), so reporting it here
    makes "which engine produced this?" answerable from the running container.
    """
    return HealthView(
        status="ok",
        engine_version=ENGINE_VERSION,
        api_schema_version=API_SCHEMA_VERSION,
    )
