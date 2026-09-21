"""Reasoning endpoints: events, timelines, graph, root cause, propagation.

Every handler in this file has the same shape -- declare the capability, call the facade,
hand the result to `respond`. That uniformity is the design rather than an accident of
style: `docs/architecture.md` §2 forbids this layer from "computing anything that changes a
conclusion", and a handler with no branch in it cannot.

The paths carry no domain vocabulary. prd.md §53's example paths name their path
parameter with a LAW-DOMAIN banned stem, and this package is in the lint's scan
(ADR-0081), so the parameter here is `process_instance_id` -- which is also what it
actually is, since the engine computes over process instances and a domain pack decides
what one is called. `docs/api.md` carries the §53-to-actual mapping so the PRD stays
traceable. This docstring cannot quote the PRD's spelling directly, which is the lint
working rather than an inconvenience.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from causalog.api.dependencies import ClockDep, FacadeDep, InferenceDep, requires
from causalog.api.responses import respond
from causalog.api.schemas.envelope import ApiResponse
from causalog.api.schemas.pagination import Page, clamp_limit
from causalog.api.security.authorization import Capability
from causalog.api.security.context import RequestContext
from causalog.orchestration import views
from causalog.orchestration.facade import QueryResult

__all__ = ["router"]

router = APIRouter(prefix="/v1/runs", tags=["analysis"])

ObservedDep = Annotated[RequestContext, Depends(requires(Capability.READ_OBSERVED))]
RecommendationsDep = Annotated[RequestContext, Depends(requires(Capability.READ_RECOMMENDATIONS))]


@router.get("/{run_id}/events", response_model=ApiResponse[Page[views.EventView]])
def read_events(
    run_id: str,
    facade: FacadeDep,
    clock: ClockDep,
    context: ObservedDep,
    limit: Annotated[int | None, Query(ge=1)] = None,
    cursor: str | None = None,
) -> ApiResponse[Page[views.EventView]]:
    """Return a page of a run's events, in `CONVENTIONS.md` §11's canonical sequence.

    One extra item is requested and then dropped. That is how `has_more` is answered
    without a second query and without a count: asking for `size + 1` and seeing whether it
    arrived distinguishes "this is the last page" from "the next page is empty", which a
    cursor alone cannot.
    """
    size = clamp_limit(limit)
    result = facade.events(run_id, limit=size + 1, after_event_id=cursor)
    items = result.data[:size]
    has_more = len(result.data) > size
    page: QueryResult[Page[views.EventView]] = QueryResult(
        data=Page(
            items=items,
            next_cursor=items[-1].event_id if has_more and items else None,
            has_more=has_more,
            sequenced_by="(t_earliest, t_latest, event_id)",
        ),
        envelope=result.envelope,
        provenance=result.provenance,
        timing=result.timing,
        stage_status=result.stage_status,
        stage_detail=result.stage_detail,
    )
    return respond(page, clock=clock, correlation_id=context.correlation_id)


@router.get(
    "/{run_id}/timelines/{process_instance_id}",
    response_model=ApiResponse[views.TimelineView | None],
)
def read_timeline(
    run_id: str,
    process_instance_id: str,
    facade: FacadeDep,
    clock: ClockDep,
    context: ObservedDep,
) -> ApiResponse[views.TimelineView | None]:
    """Return one process instance's timeline, with gaps marked rather than interpolated."""
    result = facade.timeline(run_id, process_instance_id)
    return respond(result, clock=clock, correlation_id=context.correlation_id)


@router.get("/{run_id}/graph", response_model=ApiResponse[views.GraphSubgraphView])
def read_graph(
    run_id: str,
    facade: FacadeDep,
    clock: ClockDep,
    context: InferenceDep,
    seed_event_id: str | None = None,
    depth: Annotated[int, Query(ge=0, le=10)] = 2,
    limit: Annotated[int | None, Query(ge=1)] = None,
    standing: views.GraphStandingView = views.GraphStandingView.STATED,
) -> ApiResponse[views.GraphSubgraphView]:
    """Extract a bounded subgraph, saying what was left out and why it may be empty."""
    result = facade.graph(
        run_id,
        seed_event_id=seed_event_id,
        depth=depth,
        limit=clamp_limit(limit),
        standing=standing,
    )
    return respond(result, clock=clock, correlation_id=context.correlation_id)


@router.get(
    "/{run_id}/root-causes/{outcome_event_id}",
    response_model=ApiResponse[views.RootCauseView],
)
def read_root_causes(
    run_id: str,
    outcome_event_id: str,
    facade: FacadeDep,
    clock: ClockDep,
    context: InferenceDep,
    standing: views.GraphStandingView = views.GraphStandingView.STATED,
) -> ApiResponse[views.RootCauseView]:
    """Rank the causes of one outcome as ADR-0008's four never-merged views."""
    result = facade.root_cause(run_id, outcome_event_id, standing=standing)
    return respond(result, clock=clock, correlation_id=context.correlation_id)


@router.get(
    "/{run_id}/propagation/{seed_event_id}",
    response_model=ApiResponse[dict[str, Any]],
)
def read_propagation(
    run_id: str,
    seed_event_id: str,
    facade: FacadeDep,
    clock: ClockDep,
    context: InferenceDep,
    standing: views.GraphStandingView = views.GraphStandingView.STATED,
) -> ApiResponse[dict[str, Any]]:
    """Measure one event's consequences, attributed to the node set (ADR-0061).

    The payload is the canonical body of a `draft` artifact rather than a hand-written
    view: `PropagationReport` is `draft` in `CONTEXT.md` §6, and mirroring it into a frozen
    wire shape would freeze it by assertion. `docs/api.md` marks this body as `draft`.
    """
    result = facade.propagation(run_id, seed_event_id, standing=standing)
    return respond(result, clock=clock, correlation_id=context.correlation_id)


@router.get(
    "/{run_id}/recommendations",
    response_model=ApiResponse[views.RecommendationSetView],
)
def read_recommendations(
    run_id: str,
    facade: FacadeDep,
    clock: ClockDep,
    context: RecommendationsDep,
    outcome_event_id: Annotated[list[str] | None, Query()] = None,
    standing: views.GraphStandingView = views.GraphStandingView.STATED,
) -> ApiResponse[views.RecommendationSetView]:
    """Rank the acts this graph supports, and publish the ones it withheld.

    prd.md §55 budget: 5 s, enforced. **Every recommendation carries prd.md Principle 5's
    four requirements as REQUIRED fields** -- expected benefit, confidence, supporting
    evidence and assumptions -- so an unsupported one cannot be serialized rather than
    being filtered out somewhere downstream.

    The withheld set is published beside the ranked one. On this dataset the engine
    frequently recommends nothing, and an empty list on its own says "we found nothing"
    where the true statement is "we found candidates and every one failed a named test".
    """
    result = facade.recommendations(
        run_id,
        outcome_event_ids=tuple(outcome_event_id or ()),
        standing=standing,
    )
    return respond(result, clock=clock, correlation_id=context.correlation_id)


@router.get(
    "/{run_id}/reports/{process_instance_id}",
    response_model=ApiResponse[dict[str, Any]],
)
def read_report(
    run_id: str,
    process_instance_id: str,
    facade: FacadeDep,
    clock: ClockDep,
    context: InferenceDep,
) -> ApiResponse[dict[str, Any]]:
    """Render one process instance's narrative report (prd.md §53's `/report/{…}`).

    Declared, and always `NOT_RUNNABLE` today: module 15 is `not-started`. The route exists
    rather than being omitted because an absent route is indistinguishable from one that
    ran and found nothing to say, and because a client can bind to the contract now and get
    prose when the module lands. The body names the missing module and points at the three
    endpoints that already carry the same findings without the prose.
    """
    result = facade.report(run_id, process_instance_id)
    return respond(result, clock=clock, correlation_id=context.correlation_id)
