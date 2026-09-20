"""Ontology and rule-pack introspection -- prd.md **Principle 4**, made reachable.

Principle 4 is not a nice-to-have on this surface, it is a requirement with teeth: "Every
explanation must be inspectable. Black-box reasoning is unacceptable. The user must be able
to inspect every inferred relationship."

A relationship inferred by a rule is not inspectable while the rule is invisible. These two
endpoints are what make it inspectable -- the vocabulary a run reasoned in, and the rules
that governed its conclusions, served from the same run the conclusion came from so that a
user reading a conclusion and a user reading the rule behind it cannot be looking at two
different rule packs.

The rule-pack response carries `event_types_without_a_rule` for a reason
`docs/architecture.md` §7 risk 2 states plainly: recall is bounded by rule coverage, and a
mechanism nobody wrote a rule for is invisible. Publishing the rules without publishing
what they fail to cover would satisfy Principle 4's letter and invert its purpose.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from causalog.api.dependencies import ClockDep, FacadeDep, requires
from causalog.api.responses import respond
from causalog.api.schemas.envelope import ApiResponse
from causalog.api.security.authorization import Capability
from causalog.api.security.context import RequestContext
from causalog.orchestration import views

__all__ = ["router"]

router = APIRouter(prefix="/v1/runs", tags=["introspection"])

RulesDep = Annotated[RequestContext, Depends(requires(Capability.READ_RULES))]


@router.get("/{run_id}/ontology", response_model=ApiResponse[views.OntologySummaryView])
def read_ontology(
    run_id: str, facade: FacadeDep, clock: ClockDep, context: RulesDep
) -> ApiResponse[views.OntologySummaryView]:
    """Return the ontology this run reasoned under, with its hash."""
    result = facade.ontology(run_id)
    return respond(result, clock=clock, correlation_id=context.correlation_id)


@router.get("/{run_id}/rule-pack", response_model=ApiResponse[views.RulePackView])
def read_rule_pack(
    run_id: str, facade: FacadeDep, clock: ClockDep, context: RulesDep
) -> ApiResponse[views.RulePackView]:
    """Return the rules that governed this run's conclusions, and their coverage gaps."""
    result = facade.rule_pack(run_id)
    return respond(result, clock=clock, correlation_id=context.correlation_id)
