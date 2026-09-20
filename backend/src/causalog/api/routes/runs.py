"""Run listing, comparison, and deletion of a run's inferred artifacts.

**Why comparison is an endpoint and not a client-side diff.** ADR-0013's stated positive
consequence is that two runs differing in one `RunKey` input isolate that input's effect.
That is only usable if something says WHICH inputs differ, and a client comparing two
response bodies field by field would have to know which of them participate in the
fingerprint -- `created_at` does not, `seed` does. The engine knows; the client should not
have to.

**What deletion deletes, and why it is offered at all.** Only inference. Observed facts are
dataset-scoped and inferred artifacts are run-scoped (ADR-0013), so a run identifier cannot
reach a fact even in principle -- the scoping asymmetry that makes "inference never
overwrites observation" structural is the same thing that makes this operation safe to
expose. It is audited with before/after counts (`CONVENTIONS.md` §8, migration 0014).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from causalog.api.dependencies import AdaptersDep, ClockDep, FacadeDep, requires
from causalog.api.responses import respond, respond_catalog
from causalog.api.schemas.envelope import ApiResponse
from causalog.api.security.authorization import Capability
from causalog.api.security.context import RequestContext
from causalog.orchestration import audit, caching, views
from causalog.orchestration.facade import QueryResult
from causalog.orchestration.timing import TimingMeta

__all__ = ["router"]

router = APIRouter(prefix="/v1/runs", tags=["runs"])

ObservedDep = Annotated[RequestContext, Depends(requires(Capability.READ_OBSERVED))]
DeleteDep = Annotated[RequestContext, Depends(requires(Capability.DELETE_INFERRED))]


def _run_view(facade: FacadeDep, run_id: str) -> views.RunView:
    """Render one materialized run from its envelope."""
    workspace = facade.workspace(run_id)
    envelope = workspace.envelope()
    construction = workspace.state.construction
    return views.RunView(
        run_id=envelope.run_id,
        dataset_version=envelope.dataset_version,
        ontology_hash=envelope.ontology_hash,
        rule_pack_version=envelope.rule_pack_version,
        engine_version=envelope.engine_version,
        seed=envelope.seed,
        created_at=workspace.created_at,
        graph_projection_version=envelope.graph_projection_version,
        causal_edge_count=0 if construction is None else len(construction.graph.edges),
    )


@router.get("", response_model=ApiResponse[tuple[views.RunView, ...]])
def list_runs(
    facade: FacadeDep, clock: ClockDep, context: ObservedDep
) -> ApiResponse[tuple[views.RunView, ...]]:
    """List every run materialized in this process, in canonical sequence.

    CATALOG scope: this body spans many runs, so there is no single `OutputEnvelope` that
    describes it. Each ITEM carries the five inputs that identify its run; synthesizing an
    envelope for the listing would be fabricating version fields that describe nothing.
    """
    rendered = tuple(_run_view(facade, run_id) for run_id in facade.run_ids())
    return respond_catalog(
        rendered,
        clock=clock,
        timing=TimingMeta.measured(operation="list_runs", elapsed_seconds=0.0, budget=None),
        provenance=views.provenance_summary(()),
    )


@router.get("/compare", response_model=ApiResponse[views.RunComparisonView])
def compare_runs(
    left: str, right: str, facade: FacadeDep, clock: ClockDep, context: ObservedDep
) -> ApiResponse[views.RunComparisonView]:
    """Compare two runs and name the inputs that differ."""
    first = _run_view(facade, left)
    second = _run_view(facade, right)
    differing = tuple(
        field
        for field in (
            "dataset_version",
            "ontology_hash",
            "rule_pack_version",
            "engine_version",
            "seed",
        )
        if getattr(first, field) != getattr(second, field)
    )
    comparison: QueryResult[views.RunComparisonView] = QueryResult(
        data=views.RunComparisonView(
            left=first,
            right=second,
            differing_inputs=differing,
            identical=not differing,
        ),
        envelope=facade.workspace(left).envelope(),
        provenance=views.provenance_summary(()),
        timing=TimingMeta.measured(operation="compare_runs", elapsed_seconds=0.0, budget=None),
    )
    return respond(comparison, clock=clock, correlation_id=context.correlation_id)


@router.delete("/{run_id}/inferred-artifacts", response_model=ApiResponse[views.RunView | None])
def delete_inferred_artifacts(
    run_id: str,
    facade: FacadeDep,
    adapters: AdaptersDep,
    clock: ClockDep,
    context: DeleteDep,
) -> ApiResponse[views.RunView | None]:
    """Drop a run's inferred artifacts. Observed facts are untouched and unreachable here."""
    workspace = facade.workspace(run_id)
    envelope = workspace.envelope()
    construction = workspace.state.construction
    edges = 0 if construction is None else len(construction.graph.edges)
    projection_nodes = 0 if adapters.projection is None else adapters.projection.drop_run(run_id)
    cache_entries = caching.invalidate_run(adapters.cache, run_id)
    facade.forget(run_id)
    audit.record_artifacts_deleted(
        adapters.audit,
        principal=context.principal,
        run_id=run_id,
        correlation_id=context.correlation_id,
        edges_removed=edges,
        projection_nodes_removed=projection_nodes,
        cache_entries_removed=cache_entries,
    )
    removed: QueryResult[views.RunView | None] = QueryResult(
        data=None,
        envelope=envelope,
        provenance=views.provenance_summary(()),
        timing=TimingMeta.measured(
            operation="delete_inferred_artifacts", elapsed_seconds=0.0, budget=None
        ),
    )
    return respond(removed, clock=clock, correlation_id=context.correlation_id)
