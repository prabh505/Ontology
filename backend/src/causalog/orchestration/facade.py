"""The only surface `causalog.api` may call (F5).

Every route handler in module 16 is a translation of an HTTP request into one call here
and one serialization of what comes back. That is the point of the boundary: a handler
that computed anything would be reasoning at L10, and `docs/architecture.md` §2 forbids the
API from "computing anything that changes a conclusion".

Each query returns a `QueryResult`, which carries the payload view **and** the four things
prd.md and this repository's laws require to travel with it: the `OutputEnvelope`
(`CONVENTIONS.md` §11 -- an output without it is a defect), the provenance summary
(LAW-PROVENANCE, five classes never flattened), the evidence references (LAW-EVIDENCE), and
the timing against its prd.md §55 budget. The API cannot assemble a response without them
because `QueryResult` has no constructor that omits them.

WHAT A RUN IS, HERE, AND THE LIMIT THAT COMES WITH IT
-----------------------------------------------------
A query needs more than the facts a run produced: a traversal needs the graph, the
timelines, and the rule-pack parameters that bound it. Modules 7 and 8 are not built, so
there is no temporal property graph to rehydrate those from, and `CONTEXT.md` OQ-020
records that extraction output is discarded at the end of each run for the same reason.

So this facade serves queries from a `RunWorkspace` -- the artifacts of a pipeline
execution that ran **in this process**. A query naming a run with no workspace raises
`RunNotAvailableError`, which the API renders as a 404 naming the run, exactly as
`docs/architecture.md` §2 requires ("an absent run is a 404 naming the run_id, never an
empty success").

This is a real limitation and it is stated rather than disguised: restarting the API
loses the ability to answer graph queries about a run until that run is executed again.
The facts themselves are NOT lost -- the `persist_facts` stage commits them to the system
of record -- and closing the gap is exactly what modules 7 and 8 are for. Pretending
otherwise, by rebuilding a partial graph from causal edges alone and serving it as though
it were the run's graph, would be the overclaiming this project is built to avoid.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import TypeAdapter, ValidationError

from causalog.causal_engine.causal_graph_builder import PromotedEdge
from causalog.causal_engine.propagation_analyzer import (
    GraphStanding,
    GraphView,
    PropagationContext,
    analyze_propagation,
    diagnostic_view,
    stated_view,
)
from causalog.causal_engine.root_cause_analyzer import (
    RankedCause,
    RootCauseContext,
    RootCauseRanking,
    analyze_root_causes,
)
from causalog.core.errors import CausaLogError, ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope
from causalog.core.types import Timeline
from causalog.counterfactual_engine import (
    Intervention,
    InterventionPayload,
    SimulationContext,
    simulate,
    stated_links,
    unpromoted_links,
)
from causalog.extraction.ontology_adapters import (
    actionability_of,
    cost_classes_of,
    lifecycles_of,
    magnitude_measurements_of,
    mutable_attributes_of,
    process_definitions_of,
    severity_classes_of,
)
from causalog.orchestration import views
from causalog.orchestration.stages import PipelineState
from causalog.orchestration.timing import Budget, BudgetName, TimingMeta, budget_for

__all__ = [
    "EngineFacade",
    "QueryResult",
    "RunNotAvailableError",
    "RunWorkspace",
]

PayloadT = TypeVar("PayloadT")


class RunNotAvailableError(CausaLogError):
    """A query named a run this process cannot answer for.

    Its own error class rather than a `ContractViolationError`, because the two mean
    different things to a caller: a contract violation says the request was wrong, and this
    says the request was fine and the run is not materialized here. The API maps this to
    404 and the other to 422, and one class could not carry both.
    """


@dataclass(frozen=True)
class QueryResult(Generic[PayloadT]):
    """A payload and everything that must travel with it.

    There is deliberately no default for `envelope`, `provenance` or `timing`. A result
    that could be constructed without them would eventually be, and `CONVENTIONS.md` §11
    makes an output without its envelope a defect rather than an omission.
    """

    data: PayloadT
    envelope: OutputEnvelope
    provenance: views.ProvenanceSummary
    timing: TimingMeta
    evidence: tuple[views.EvidenceReference, ...] = ()
    confidence: views.ConfidenceView | None = None
    standing: views.GraphStandingView = views.GraphStandingView.STATED
    stage_status: views.StageStatusView = views.StageStatusView.COMPLETE
    #: Present when `stage_status` is not COMPLETE, naming the module that would supply the
    #: missing part. Required by the API's response model in that case, so an endpoint
    #: cannot report NOT_RUNNABLE without saying what is not runnable.
    stage_detail: str | None = None


@dataclass
class RunWorkspace:
    """One executed run's artifacts, held for the queries that need to traverse them."""

    run_id: str
    state: PipelineState
    created_at: datetime

    def envelope(self) -> OutputEnvelope:
        """Return this run's output envelope."""
        return self.state.require_envelope()

    def has_promoted_graph(self) -> bool:
        """Return whether a promoted graph was built at all."""
        return self.state.construction is not None


class EngineFacade:
    """Composes reasoning modules into answers. Holds no reasoning of its own.

    Every method here does the same four things and nothing else: resolve a workspace,
    build the context a reasoning module declares, call that module's published entry
    point, and render the result through `orchestration.views`. Where a decision looks like
    it is being made here -- which standing to walk, what to say when a result is empty --
    it is being REPORTED here, from a value the reasoning layer produced.
    """

    def __init__(self) -> None:
        """Start with no materialized runs."""
        self._workspaces: dict[str, RunWorkspace] = {}

    # -- workspace management -------------------------------------------------

    def remember(self, state: PipelineState, *, at: datetime) -> str:
        """Record a completed execution's artifacts and return its `run_id`.

        Called by the job runner's caller once an execution finishes. A run with no
        envelope never reaches here: without one there is no `run_id` to file it under,
        and filing it under a placeholder would mint an identifier that addresses nothing.
        """
        envelope = state.require_envelope()
        self._workspaces[envelope.run_id] = RunWorkspace(
            run_id=envelope.run_id, state=state, created_at=at
        )
        return envelope.run_id

    def forget(self, run_id: str) -> bool:
        """Drop a run's in-process artifacts. Returns whether anything was dropped.

        Used by the delete endpoint. It removes INFERENCE only: observed facts are
        dataset-scoped rather than run-scoped (ADR-0013), so they are not reachable from a
        run identifier at all. That asymmetry is what makes this operation safe to expose.
        """
        return self._workspaces.pop(run_id, None) is not None

    def workspace(self, run_id: str) -> RunWorkspace:
        """Return a materialized run, or refuse by naming it.

        Raises:
            RunNotAvailableError: no execution in this process produced that run.
        """
        found = self._workspaces.get(run_id)
        if found is None:
            raise RunNotAvailableError(
                f"Run {run_id!r} is not materialized in this process. A run_id is "
                "content-addressed from its inputs (ADR-0013), so this is not a "
                "'not found' about the identifier -- it means no execution here produced "
                "its artifacts. Start a pipeline execution for the same inputs to "
                "materialize it."
            )
        return found

    def run_ids(self) -> tuple[str, ...]:
        """Return every materialized run, in canonical sequence.

        Sorted rather than insertion-sequenced: `CONVENTIONS.md` §11 requires every read to
        yield a canonical sequence, and a listing that followed execution sequence would
        page differently on two processes holding the same runs.
        """
        return tuple(sorted(self._workspaces))

    # -- queries --------------------------------------------------------------

    def events(
        self, run_id: str, *, limit: int, after_event_id: str | None = None
    ) -> QueryResult[tuple[views.EventView, ...]]:
        """Return a page of a run's events in canonical sequence.

        Paged on `(t_earliest, t_latest, event_id)` -- `CONVENTIONS.md` §11's canonical sort
        key for events, not an invented one -- so a cursor is stable across requests and
        across processes holding the same run.
        """
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        ranked = sorted(
            workspace.state.events,
            key=lambda event: (
                event.occurred_at.t_earliest,
                event.occurred_at.t_latest,
                event.event_id,
            ),
        )
        if after_event_id is not None:
            position = next(
                (
                    index + 1
                    for index, event in enumerate(ranked)
                    if event.event_id == after_event_id
                ),
                None,
            )
            if position is None:
                raise ContractViolationError(
                    f"Cursor names event {after_event_id!r}, which is not in run "
                    f"{run_id!r}. A cursor from another run would silently page through "
                    "the wrong sequence."
                )
            ranked = ranked[position:]
        page = tuple(views.event_view(event) for event in ranked[:limit])
        return self._result(
            workspace,
            page,
            provenance=tuple(event.provenance_class for event in ranked[:limit]),
            operation="events",
            started=started,
            budget=None,
        )

    def timeline(
        self, run_id: str, process_instance_id: str
    ) -> QueryResult[views.TimelineView | None]:
        """Return one process instance's timeline, with its gaps marked rather than filled."""
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        found = next(
            (
                timeline
                for timeline in workspace.state.timelines
                if process_instance_id in timeline.subject_entity_ids
                or timeline.timeline_id == process_instance_id
            ),
            None,
        )
        rendered = None if found is None else _timeline_view(found)
        return self._result(
            workspace,
            rendered,
            provenance=(() if rendered is None else (rendered.provenance_class,)),
            operation="timeline",
            started=started,
            budget=None,
        )

    def graph(
        self,
        run_id: str,
        *,
        seed_event_id: str | None,
        depth: int,
        limit: int,
        standing: views.GraphStandingView = views.GraphStandingView.STATED,
    ) -> QueryResult[views.GraphSubgraphView]:
        """Extract a bounded subgraph around a seed.

        Reports `NOT_RUNNABLE` rather than an empty graph when module 8 has not run. The
        distinction matters more here than anywhere else in the API: an empty `edges` list
        reads as "this event causes nothing", and on this repository the true statement is
        "the projection that would answer this does not exist yet".
        """
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        if not workspace.has_promoted_graph():
            return self._not_runnable(
                workspace,
                views.GraphSubgraphView(
                    standing=standing, seed_event_id=seed_event_id, depth=depth
                ),
                operation="graph",
                started=started,
                budget=budget_for(BudgetName.GRAPH_GENERATION),
                detail=(
                    "No causal graph was built for this run, so there is nothing to "
                    "extract a subgraph from."
                ),
            )
        view = self._graph_view(workspace, standing)
        nodes, edges, truncated = _extract_subgraph(
            workspace, view, seed_event_id=seed_event_id, depth=depth, limit=limit
        )
        rejected = len(workspace.state.construction.graph.demotions)
        payload = views.GraphSubgraphView(
            standing=standing,
            standing_notice=_standing_notice(standing),
            seed_event_id=seed_event_id,
            depth=depth,
            nodes=nodes,
            edges=edges,
            empty_because=_graph_empty_because(edges, rejected, standing, seed_event_id),
            rejected_claim_count=rejected,
            truncated=truncated,
            truncation_detail=(
                f"The traversal reached its bound of {limit} edges. What is missing is "
                "not 'nothing else is connected' -- raise the bound or narrow the seed."
                if truncated
                else None
            ),
        )
        return self._result(
            workspace,
            payload,
            provenance=tuple(edge.provenance_class for edge in edges),
            operation="graph",
            started=started,
            budget=budget_for(BudgetName.GRAPH_GENERATION),
            standing=standing,
        )

    def root_cause(
        self,
        run_id: str,
        outcome_event_id: str,
        *,
        standing: views.GraphStandingView = views.GraphStandingView.STATED,
    ) -> QueryResult[views.RootCauseView]:
        """Rank the causes of one outcome, as ADR-0008's four never-merged views."""
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        budget = budget_for(BudgetName.ROOT_CAUSE_QUERY)
        if not workspace.has_promoted_graph():
            return self._not_runnable(
                workspace,
                _empty_root_cause(outcome_event_id, standing, "No causal graph was built."),
                operation="root_cause",
                started=started,
                budget=budget,
                detail="No causal graph was built for this run.",
            )
        context = self._root_cause_context(workspace, standing)
        result = analyze_root_causes(outcome_event_id, context, workspace.envelope())
        payload = _root_cause_view(result.ranking)
        return self._result(
            workspace,
            payload,
            provenance=(payload.provenance_class,),
            operation="root_cause",
            started=started,
            budget=budget,
            standing=standing,
        )

    def propagation(
        self,
        run_id: str,
        seed_event_id: str,
        *,
        standing: views.GraphStandingView = views.GraphStandingView.STATED,
    ) -> QueryResult[dict[str, Any]]:
        """Measure what one event's consequences are, attributed to the node set."""
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        if not workspace.has_promoted_graph():
            return self._not_runnable(
                workspace,
                {},
                operation="propagation",
                started=started,
                budget=None,
                detail="No causal graph was built for this run.",
            )
        context = self._propagation_context(workspace, standing)
        result = analyze_propagation(seed_event_id, context, workspace.envelope())
        return self._result(
            workspace,
            views.artifact_body(result.report),
            # `PropagationReport` carries no provenance class of its own -- it is a
            # measurement OVER a graph, not an assertion -- so the summary comes from the
            # edges that were walked. Substituting a constant here would attach an
            # epistemic claim the report does not make.
            provenance=tuple(
                promoted.edge.provenance_class
                for promoted in workspace.state.construction.graph.edges
            ),
            operation="propagation",
            started=started,
            budget=None,
            standing=standing,
        )

    def counterfactual(
        self,
        run_id: str,
        requested: tuple[views.InterventionSpec, ...],
        *,
        standing: views.GraphStandingView = views.GraphStandingView.STATED,
    ) -> QueryResult[dict[str, Any]]:
        """Simulate a world in which the named interventions held.

        `accept_unpromoted` is passed only for the diagnostic standing, and ADR-0072 is the
        reason it is an explicit opt-in rather than an inference: module 13 REFUSES a
        disowned input unless a caller says, in the call, that it wants one.
        """
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        budget = budget_for(BudgetName.COUNTERFACTUAL_QUERY)
        if not workspace.has_promoted_graph():
            return self._not_runnable(
                workspace,
                {},
                operation="counterfactual",
                started=started,
                budget=budget,
                detail="No causal graph was built for this run.",
            )
        context = self._simulation_context(workspace, standing)
        result = simulate(
            _parse_interventions(requested),
            context,
            workspace.envelope(),
            accept_unpromoted=standing is views.GraphStandingView.UNPROMOTED_DIAGNOSTIC,
        )
        return self._result(
            workspace,
            views.artifact_body(result.report),
            provenance=(ProvenanceClass.SIMULATED,),
            operation="counterfactual",
            started=started,
            budget=budget,
            standing=standing,
        )

    def ontology(self, run_id: str) -> QueryResult[views.OntologySummaryView]:
        """Return the ontology this run reasoned under (prd.md Principle 4)."""
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        pack = workspace.state.pack
        payload = views.OntologySummaryView(
            ontology_version=pack.pack.ontology_version,
            ontology_hash=pack.ontology_hash,
            pack_schema_version=str(getattr(pack.pack, "pack_schema_version", "1.0.0")),
            concepts=tuple(
                views.OntologyConceptView(
                    concept_kind="event_type",
                    concept_id=item.id,
                    label=getattr(item, "label", None),
                )
                for item in sorted(pack.pack.event_types, key=lambda entry: str(entry.id))
            ),
        )
        return self._result(
            workspace,
            payload,
            provenance=(ProvenanceClass.OBSERVED,),
            operation="ontology",
            started=started,
            budget=None,
        )

    def rule_pack(self, run_id: str) -> QueryResult[views.RulePackView]:
        """Return the rules that governed this run's conclusions (prd.md Principle 4).

        Principle 4 says the user must be able to inspect every inferred relationship, and a
        relationship inferred by a rule is not inspectable while the rule is invisible. The
        coverage gaps travel with the rules for the reason ADR-0044's coverage report
        exists: publishing what the rules DO without publishing what they do not cover
        satisfies the principle's letter and inverts its purpose.
        """
        workspace = self.workspace(run_id)
        started = time.perf_counter()
        loaded = workspace.state.rules
        payload = views.RulePackView(
            rule_pack_version=loaded.rule_pack_version,
            rule_pack_schema_version=str(getattr(loaded.pack, "rule_pack_schema_version", "1.0.0")),
            rule_pack_hash=loaded.rule_pack_hash,
            rules=tuple(
                views.RuleSummaryView(
                    rule_id=str(rule.id),
                    rule_kind=str(getattr(rule, "kind", "UNKNOWN")),
                    knowledge_provenance=_optional_str(getattr(rule, "knowledge_provenance", None)),
                    condition=views.artifact_body(rule.condition)
                    if getattr(rule, "condition", None) is not None
                    else {},
                    conclusion=views.artifact_body(rule),
                )
                for rule in sorted(loaded.pack.rules, key=lambda entry: str(entry.id))
            ),
        )
        return self._result(
            workspace,
            payload,
            provenance=(ProvenanceClass.ASSUMED,),
            operation="rule_pack",
            started=started,
            budget=None,
        )

    # -- context builders -----------------------------------------------------

    def _graph_view(self, workspace: RunWorkspace, standing: views.GraphStandingView) -> GraphView:
        """Return the `GraphView` for a standing.

        `diagnostic_view` is the ONLY construction site of `UNPROMOTED_DIAGNOSTIC` in the
        engine (ADR-0059, asserted over the AST), so this branch calls it rather than
        constructing a standing itself.
        """
        if standing is views.GraphStandingView.UNPROMOTED_DIAGNOSTIC:
            return diagnostic_view(workspace.state.scored)
        return stated_view(workspace.state.construction.graph)

    def _propagation_context(
        self, workspace: RunWorkspace, standing: views.GraphStandingView
    ) -> PropagationContext:
        """Build module 12's context from a workspace."""
        state = workspace.state
        return PropagationContext(
            facts=state.facts,
            timelines=state.timelines,
            view=self._graph_view(workspace, standing),
            parameters=state.rules.pack.propagation_analysis,
            magnitude_measurements=magnitude_measurements_of(state.pack.pack),
            run_id=workspace.run_id,
        )

    def _root_cause_context(
        self, workspace: RunWorkspace, standing: views.GraphStandingView
    ) -> RootCauseContext:
        """Build module 11's context, which carries module 12's whole."""
        state = workspace.state
        return RootCauseContext(
            propagation=self._propagation_context(workspace, standing),
            actionability=actionability_of(state.pack.pack),
            cost_classes=cost_classes_of(state.pack.pack),
            severity_classes=severity_classes_of(state.pack.pack),
            parameters=state.rules.pack.root_cause_analysis,
            run_id=workspace.run_id,
        )

    def _simulation_context(
        self, workspace: RunWorkspace, standing: views.GraphStandingView
    ) -> SimulationContext:
        """Build module 13's context, which carries module 12's WHOLE (ADR-0069).

        Carried whole rather than rebuilt so the two cannot disagree about which graph or
        which depth -- which is the stated reason ADR-0069 shaped it that way.
        """
        state = workspace.state
        links = (
            unpromoted_links(state.scored)
            if standing is views.GraphStandingView.UNPROMOTED_DIAGNOSTIC
            else stated_links(state.construction.graph)
        )
        return SimulationContext(
            propagation=self._propagation_context(workspace, standing),
            links=links,
            joint_groups=state.construction.graph.joint_cause_groups,
            lifecycles=lifecycles_of(state.pack.pack),
            processes=process_definitions_of(state.pack.pack),
            mutability=mutable_attributes_of(state.pack.pack),
            derived_precedence=state.derived_precedence,
            entities=state.entities,
            parameters=state.rules.pack.counterfactual_simulation,
            run_id=workspace.run_id,
        )

    # -- result assembly ------------------------------------------------------

    def _result(
        self,
        workspace: RunWorkspace,
        data: PayloadT,
        *,
        provenance: tuple[ProvenanceClass, ...],
        operation: str,
        started: float,
        budget: Budget | None,
        standing: views.GraphStandingView = views.GraphStandingView.STATED,
        evidence: tuple[views.EvidenceReference, ...] = (),
        confidence: views.ConfidenceView | None = None,
    ) -> QueryResult[PayloadT]:
        """Assemble a result with its envelope, provenance and timing attached."""
        return QueryResult(
            data=data,
            envelope=workspace.envelope(),
            provenance=views.provenance_summary(provenance),
            timing=TimingMeta.measured(
                operation=operation,
                elapsed_seconds=time.perf_counter() - started,
                budget=budget,
            ),
            evidence=evidence,
            confidence=confidence,
            standing=standing,
        )

    def _not_runnable(
        self,
        workspace: RunWorkspace,
        data: PayloadT,
        *,
        operation: str,
        started: float,
        budget: Budget | None,
        detail: str,
    ) -> QueryResult[PayloadT]:
        """Assemble a result that says what could not be computed, and why."""
        result = self._result(
            workspace,
            data,
            provenance=(),
            operation=operation,
            started=started,
            budget=budget,
        )
        return QueryResult(
            data=result.data,
            envelope=result.envelope,
            provenance=result.provenance,
            timing=result.timing,
            stage_status=views.StageStatusView.NOT_RUNNABLE,
            stage_detail=detail,
        )


# ---------------------------------------------------------------------------
# Rendering helpers. Module-level because they hold no facade state.
# ---------------------------------------------------------------------------


#: Parses a wire payload into module 13's closed, discriminated union of five change
#: types (ADR-0066). The union is discriminated on `kind`, so a body naming an unknown kind
#: is refused with the five admissible values rather than reaching the simulator.
_PAYLOAD_ADAPTER: TypeAdapter[InterventionPayload] = TypeAdapter(InterventionPayload)


def _parse_interventions(
    requested: tuple[views.InterventionSpec, ...],
) -> tuple[Intervention, ...]:
    """Turn wire-level intervention specs into module 13's typed language.

    This function is the reason `InterventionSpec` exists: it is the one place a mapping
    becomes an `Intervention`, and it lives at L9 because L10 may not name the type it
    produces (forbidden edge F5).
    """
    parsed: list[Intervention] = []
    for index, item in enumerate(requested):
        try:
            payload = _PAYLOAD_ADAPTER.validate_python(item.payload)
        except ValidationError as failure:
            raise ContractViolationError(
                f"Intervention {index} does not match any of the five admissible change "
                "types. The set is closed because the kind enters the content address of "
                f"the simulated world it produces (ADR-0066). Detail: {failure.errors()}"
            ) from failure
        parsed.append(Intervention.of(payload, rationale=item.rationale))
    return tuple(parsed)


def _optional_str(value: object) -> str | None:
    """Return a string form of an optional enum-or-text value, or None."""
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _standing_notice(standing: views.GraphStandingView) -> str | None:
    """Return the disowning notice for a diagnostic standing, or None for a stated one."""
    if standing is not views.GraphStandingView.UNPROMOTED_DIAGNOSTIC:
        return None
    return (
        "DISOWNED. This was walked over the scored graph BEFORE promotion. The engine "
        "does not assert it, nothing here is INFERRED, and a figure quoted from it "
        "without this notice is being quoted as something it is not (ADR-0059, OQ-026)."
    )


def _graph_empty_because(
    edges: tuple[views.GraphEdgeView, ...],
    rejected: int,
    standing: views.GraphStandingView,
    seed_event_id: str | None,
) -> str | None:
    """Say why a subgraph is empty, when it is. Returns None when it is not.

    Three genuinely different emptinesses, and collapsing them would be the whole problem:

    * **Claims were made and all were refused.** The common case on this dataset -- the
      builder proposed thousands and promoted none, and the ledger holds a reason per
      claim. The graph being empty is a statement about the engine's CONFIDENCE, not about
      the data's connectedness.
    * **Nothing was ever proposed.** A different finding: no candidate reached the
      promotion decision at all.
    * **The seed is isolated.** The graph has edges; this event is on none of them.
    """
    if edges:
        return None
    if seed_event_id is not None and rejected == 0:
        return (
            f"No promoted edge touches {seed_event_id!r}. The graph is not empty; this "
            "event sits on none of its edges."
        )
    if rejected:
        return (
            f"The causal graph is empty: {rejected:,} claim(s) were proposed and every one "
            "was refused promotion. This is a statement about what the engine ASSERTS, not "
            "about what the data contains -- each refusal is recorded in the rejection "
            "ledger with its reason, and on a day-granular source most are refused for "
            "TEMPORAL reasons rather than for weak evidence. Re-ask under the "
            "UNPROMOTED_DIAGNOSTIC standing to see the scored-but-unasserted structure, "
            "reading its disowning notice first."
        )
    if standing is views.GraphStandingView.UNPROMOTED_DIAGNOSTIC:
        return (
            "No edge was scored at all, even before promotion. Nothing was proposed for "
            "this graph."
        )
    return (
        "The causal graph holds no promoted edge and no claim was refused, which means no "
        "candidate ever reached the promotion decision."
    )


def _timeline_view(timeline: Timeline) -> views.TimelineView:
    """Render a `Timeline`, marking every gap rather than interpolating one.

    `TimelineEntryKind` is carried through verbatim, which is what makes a gap visible: a
    `Timeline` records a step no record witnessed as an entry of its own, and flattening
    entries to "the events" would delete exactly the information module 4's
    `MissingEventPolicy.RECORD_GAP` exists to preserve.

    `process_instance_id` is the FIRST subject entity. A timeline is keyed by its subjects
    and a process timeline has one anchor; the tuple is sequenced canonically upstream, so
    taking its head is deterministic rather than arbitrary.
    """
    return views.TimelineView(
        timeline_id=timeline.timeline_id,
        process_instance_id=(
            timeline.subject_entity_ids[0] if timeline.subject_entity_ids else timeline.timeline_id
        ),
        entries=tuple(
            views.TimelineEntryView(
                kind=entry.kind.value,
                event_id=entry.event_id,
                occurred_at=(
                    views.interval_view(entry.occurred_at)
                    if entry.occurred_at is not None
                    else None
                ),
                sequence_index=index,
                detail=entry.expected_event_type,
            )
            for index, entry in enumerate(timeline.entries)
        ),
        provenance_class=timeline.provenance_class,
    )


def _ranked_cause_view(cause: RankedCause) -> views.RankedCauseView:
    """Render one `RankedCause`, keeping its caveats attached to it."""
    return views.RankedCauseView(
        event_id=cause.event_id,
        event_type=cause.event_type,
        confidence=views.confidence_view(cause.confidence),
        chain_scalar=cause.chain.composed,
        chain_composition=cause.chain.composition,
        chain_length=len(cause.chain_links),
        earliness_rank=cause.earliness_rank,
        is_actionable=cause.actionability.is_actionable,
        cost_class=cause.actionability.cost_class,
        prevented_event_ids=cause.prevented_event_ids,
        prevented_magnitude=cause.prevented_magnitude,
        prevented_unit=cause.prevented_unit,
        prevented_share=cause.prevented_share,
        evidence_item_ids=cause.evidence_item_ids,
        provenance_class=cause.provenance_class,
        partial_data_flag=cause.partial_data_flag,
    )


def _plateau_groups(causes: tuple[RankedCause, ...]) -> tuple[views.PlateauGroupView, ...]:
    """Group a ranked set into plateaus, so a tie is presented as a tie (OQ-027).

    Grouped on the chain scalar, which is what `weakest_link_v1` composes and therefore what
    ties. Causes that tie are emitted as ONE group with `tied=True`; the tie is **not**
    broken on earliness, which would reintroduce ADR-0008's forbidden blend by the back
    door. Within a group the members are sequenced by `event_id` purely so the response is
    byte-identical across runs -- that sequence carries no ranking, and `docs/api.md` says so.
    """
    groups: list[views.PlateauGroupView] = []
    bucket: list[Any] = []
    current: float | None = None
    for cause in causes:
        value = cause.chain.composed
        if current is not None and value != current:
            groups.append(_plateau_group(bucket, current))
            bucket = []
        current = value
        bucket.append(cause)
    if bucket and current is not None:
        groups.append(_plateau_group(bucket, current))
    return tuple(groups)


def _plateau_group(members: list[RankedCause], value: float) -> views.PlateauGroupView:
    """Build one plateau group from the causes sharing a composed value."""
    tied = len(members) > 1
    return views.PlateauGroupView(
        tied=tied,
        plateau_value=value,
        plateau_notice=(
            "These candidates compose to exactly the same value. The engine did not "
            "sequence them and this set is UNSEQUENCED: the sequence of `members` carries no "
            "ranking. Breaking the tie on earliness would blend two of ADR-0008's four "
            "views, which is the one thing they are kept apart to prevent."
            if tied
            else None
        ),
        members=tuple(
            _ranked_cause_view(cause) for cause in sorted(members, key=lambda item: item.event_id)
        ),
    )


def _root_cause_view(ranking: RootCauseRanking) -> views.RootCauseView:
    """Render a `RootCauseRanking` as four never-merged fields."""
    return views.RootCauseView(
        outcome_event_id=ranking.outcome_event_id,
        standing=views.standing_view(ranking.standing),
        standing_notice=ranking.standing_notice,
        actionability_notice=ranking.actionability_notice,
        earliest=(
            _ranked_cause_view(ranking.earliest_cause)
            if ranking.earliest_cause is not None
            else None
        ),
        highest_consequence=(
            _ranked_cause_view(ranking.highest_consequence_cause)
            if ranking.highest_consequence_cause is not None
            else None
        ),
        most_actionable=(
            _ranked_cause_view(ranking.most_actionable_cause)
            if ranking.most_actionable_cause is not None
            else None
        ),
        recommended_groups=_plateau_groups(ranking.actionable_root_causes),
        trade_offs=tuple(
            views.TradeOffView(
                first_view=str(getattr(item.first_view, "value", item.first_view)),
                first_event_id=item.first_event_id,
                second_view=str(getattr(item.second_view, "value", item.second_view)),
                second_event_id=item.second_event_id,
                detail=item.detail,
            )
            for item in ranking.trade_offs
        ),
        views_agree=ranking.views_agree,
        candidate_search_truncated=ranking.candidate_search_truncated,
        sequencing_function=ranking.sequencing_function,
        empty_because=_empty_because(ranking),
        provenance_class=ranking.provenance_class,
    )


def _empty_because(ranking: RootCauseRanking) -> str | None:
    """Say why a ranking is empty, when it is.

    An empty `[]` with no explanation reads as "we looked and there is nothing to find".
    On this dataset the true statement is usually different -- the promoted graph is empty
    because 79.3% of claims are stopped by the temporal verdict rather than by any
    threshold (R-22) -- and returning the list without the reason invites exactly the wrong
    reading of a correct result.
    """
    if ranking.considered:
        return None
    if ranking.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC:
        return (
            "No candidate was considered, even over the unpromoted scored graph. Nothing "
            "reached this outcome in the causal structure at all."
        )
    return (
        "No candidate was considered under the STATED standing, which walks the PROMOTED "
        "graph. This is a statement about what the engine ASSERTS, not about what the data "
        "contains: a claim that fails promotion is recorded in the rejection ledger with "
        "its reason. Query the rejection ledger, or re-ask under the diagnostic standing, "
        "to see what fell short and why."
    )


def _empty_root_cause(
    outcome_event_id: str, standing: views.GraphStandingView, reason: str
) -> views.RootCauseView:
    """Build a root-cause payload for a run with no graph to rank over."""
    return views.RootCauseView(
        outcome_event_id=outcome_event_id,
        standing=standing,
        standing_notice=_standing_notice(standing),
        actionability_notice=(
            "Actionability is ontology-declared and is not validated against any ground "
            "truth (R-15)."
        ),
        views_agree=True,
        empty_because=reason,
        provenance_class=ProvenanceClass.OBSERVED,
    )


def _extract_subgraph(
    workspace: RunWorkspace,
    view: GraphView,
    *,
    seed_event_id: str | None,
    depth: int,
    limit: int,
) -> tuple[tuple[views.GraphNodeView, ...], tuple[views.GraphEdgeView, ...], bool]:
    """Walk outward from a seed, bounded by depth and by edge count.

    Breadth-first and sequenced at every step, so the same request returns the same
    subgraph: an unsequenced frontier would make two identical requests differ in which
    edges fell inside the bound, which `CONVENTIONS.md` §11 forbids.
    """
    edges_by_id = {
        promoted.edge.causal_edge_id: promoted
        for promoted in _edges_of(workspace, seed_event_id, view)
    }
    ranked = sorted(edges_by_id.values(), key=lambda item: item.edge.causal_edge_id)
    truncated = len(ranked) > limit
    selected = ranked[:limit]
    depths = _depths(selected, seed_event_id, depth)
    events_by_id = {event.event_id: event for event in workspace.state.events}
    node_ids = sorted(
        {promoted.edge.source_event_id for promoted in selected}
        | {promoted.edge.target_event_id for promoted in selected}
    )
    nodes = tuple(
        views.GraphNodeView(
            event_id=event_id,
            event_type=(
                events_by_id[event_id].event_type if event_id in events_by_id else "UNKNOWN"
            ),
            occurred_at=(
                views.interval_view(events_by_id[event_id].occurred_at)
                if event_id in events_by_id
                else None
            ),
            provenance_class=(
                events_by_id[event_id].provenance_class
                if event_id in events_by_id
                else ProvenanceClass.INFERRED
            ),
            depth_from_seed=depths.get(event_id, 0),
        )
        for event_id in node_ids
    )
    rendered_edges = tuple(
        views.GraphEdgeView(
            causal_edge_id=promoted.edge.causal_edge_id,
            source_event_id=promoted.edge.source_event_id,
            target_event_id=promoted.edge.target_event_id,
            edge_kind=promoted.edge.payload.edge_kind.value,
            confidence=views.confidence_view(promoted.edge.confidence),
            propagation_weight=promoted.weight.weight,
            provenance_class=promoted.edge.provenance_class,
            temporal_verdict=promoted.edge.temporal_verdict.value,
            temporally_unverifiable=promoted.edge.temporally_unverifiable,
        )
        for promoted in selected
    )
    return nodes, rendered_edges, truncated


def _edges_of(
    workspace: RunWorkspace, seed_event_id: str | None, view: GraphView
) -> Iterator[PromotedEdge]:
    """Yield the causal edges in scope for one extraction."""
    del view
    graph = workspace.state.construction.graph
    for edge in graph.edges:
        if seed_event_id is None or seed_event_id in (edge.source_event_id, edge.target_event_id):
            yield edge


def _depths(edges: list[PromotedEdge], seed_event_id: str | None, depth: int) -> dict[str, int]:
    """Return each node's hop distance from the seed, bounded by `depth`."""
    if seed_event_id is None:
        return {}
    distances: dict[str, int] = {seed_event_id: 0}
    frontier = [seed_event_id]
    for hop in range(1, depth + 1):
        following: list[str] = []
        for promoted in edges:
            for near, far in (
                (promoted.edge.source_event_id, promoted.edge.target_event_id),
                (promoted.edge.target_event_id, promoted.edge.source_event_id),
            ):
                if near in frontier and far not in distances:
                    distances[far] = hop
                    following.append(far)
        if not following:
            break
        frontier = sorted(set(following))
    return distances
