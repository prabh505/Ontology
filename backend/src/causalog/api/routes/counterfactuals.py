"""Counterfactual simulation (prd.md §53's `/counterfactual`).

**POST, where prd.md §53 shows GET.** The PRD calls its list "Example endpoints", and the
example is `GET /counterfactual`. An intervention set is a structured, typed value -- five
payload shapes as a discriminated union (ADR-0066) -- and encoding one in a query string
means inventing a serialization for it, which would become a second wire format free to
disagree with the canonical one. The mapping is recorded in `docs/api.md`.

**The response is labelled as a simulation in three independent places**, because prd.md
§37 and OQ-031 both turn on a simulated figure never being readable as an observed one:
the payload provenance is `SIMULATED`, the body carries module 13's fixed
"not a prediction" notice as a required field, and the type carrying simulated events is
`SimulatedEventView`, which has no `occurred_at` and cannot be deserialized into an
`EventView`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from causalog.api.dependencies import ClockDep, FacadeDep, requires
from causalog.api.responses import respond
from causalog.api.schemas.envelope import ApiResponse
from causalog.api.security.authorization import Capability
from causalog.api.security.context import RequestContext
from causalog.core.errors import ContractViolationError
from causalog.orchestration import views

__all__ = ["router"]

router = APIRouter(prefix="/v1/runs", tags=["counterfactuals"])

SimulateDep = Annotated[RequestContext, Depends(requires(Capability.SIMULATE))]


class InterventionRequest(BaseModel):
    """One proposed change to the world, as it arrives on the wire.

    It holds a mapping rather than a typed payload because forbidden edge F5 forbids this
    package from naming a `counterfactual_engine` type at all. The mapping is parsed into
    module 13's closed discriminated union by `orchestration.facade`, on the far side of
    the seam -- which is also where the parse belongs, since it is a reasoning contract
    rather than a transport concern.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: dict[str, Any]
    rationale: str = Field(min_length=1)


class SimulationRequest(BaseModel):
    """A set of interventions to apply together.

    A SET, not a sequence of separate calls, because ADR-0077 is explicit that two acts on
    one chain are simulated jointly and never summed: the overlap between them is real, and
    adding two single-act results would double-count it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    interventions: tuple[InterventionRequest, ...] = Field(min_length=1)
    standing: views.GraphStandingView = views.GraphStandingView.STATED


@router.post("/{run_id}/counterfactuals", response_model=ApiResponse[dict[str, Any]])
def simulate_counterfactual(
    run_id: str,
    body: SimulationRequest,
    facade: FacadeDep,
    clock: ClockDep,
    context: SimulateDep,
) -> ApiResponse[dict[str, Any]]:
    """Simulate a world in which the named interventions held.

    A caller asking for the diagnostic standing must hold `READ_DIAGNOSTIC` as well as
    `SIMULATE`. The check is here rather than in `standing_guard` because the standing
    arrives in the BODY on this endpoint, not in the query string, and a guard reading
    query parameters would silently pass it.
    """
    if body.standing is views.GraphStandingView.UNPROMOTED_DIAGNOSTIC:
        from causalog.api.security.authorization import permitted

        if not permitted(context.principal.role, Capability.READ_DIAGNOSTIC):
            raise ContractViolationError(
                "Simulating over the UNPROMOTED_DIAGNOSTIC standing additionally requires "
                "READ_DIAGNOSTIC. Everything walked under that standing is disowned by "
                "the engine (ADR-0059), and a simulation over disowned structure is a "
                "figure twice removed from anything asserted."
            )
    interventions = tuple(
        views.InterventionSpec(payload=item.payload, rationale=item.rationale)
        for item in body.interventions
    )
    result = facade.counterfactual(run_id, interventions, standing=body.standing)
    return respond(result, clock=clock, correlation_id=context.correlation_id)
