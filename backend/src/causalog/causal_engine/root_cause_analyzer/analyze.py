"""Module 11's entry point: one outcome in, four labelled answers out.

The assembly step. Every judgement has been made somewhere else -- the counterfactual in
module 12, the composition in `core.composition`, the sequencing key in `core.ranking`, the
bounds in the pack -- and this module runs them in sequence and returns an artifact whose
numbers agree with each other.

THE SHAPE OF THE WORK

1. Walk BACKWARDS from the outcome to find every ancestor: the candidate set.
2. For each candidate, ask module 12 forward: what does the graph say stops occurring if
   this is removed. That question is asked of the SAME context module 12 walked, under the
   same bounds, so the two cannot disagree about which graph they are describing.
3. Compose belief about the chain joining the candidate to the outcome.
4. Emit four labelled views and a trade-off wherever two of them disagree.

**It creates no link.** `CausalEdge` is never constructed here and `ProvenanceClass.INFERRED`
is never assigned here, which `tests/law/test_ranking_never_collapses.py` asserts over the
AST of both this package and module 12's.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.propagation_analyzer import (
    PathConfidence,
    PropagationResult,
    analyze_propagation,
    prevented_by_removing,
    share_of_whole,
)
from causalog.causal_engine.propagation_analyzer.view import GraphLink, GraphStanding
from causalog.causal_engine.root_cause_analyzer.context import RootCauseContext
from causalog.causal_engine.root_cause_analyzer.ranking import (
    ActionabilityStanding,
    RankedCause,
)
from causalog.causal_engine.root_cause_analyzer.recurrence import recurrence_of
from causalog.causal_engine.root_cause_analyzer.report import (
    RootCauseRanking,
    RootCauseReport,
    build_report,
)
from causalog.causal_engine.root_cause_analyzer.views import (
    ViewName,
    earliest,
    highest_consequence,
    most_actionable,
    recommended,
    trade_offs,
)
from causalog.core.composition import DEFAULT_COMPOSER, compose
from causalog.core.precedence import DerivedPrecedence  # noqa: F401  -- see _partial_data
from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.ranking import rank_value
from causalog.core.run import OutputEnvelope
from causalog.core.temporal import Precision
from causalog.core.types import Event

__all__ = ["RootCauseResult", "analyze_root_causes"]

#: How many ancestors are explored before the search reports truncation. A ceiling rather
#: than a default: the pack's `candidate_cap` is the operative bound, and a pack that
#: declares none gets this rather than an unbounded walk, because an unbounded backward
#: sweep over a dense graph does not terminate inside prd.md §55's three-second budget.
CANDIDATE_SEARCH_CEILING = 5000


class RootCauseResult(BaseModel):
    """The module's whole output: the ranking, the propagation behind it, and the report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ranking: RootCauseRanking
    propagation: PropagationResult
    report: RootCauseReport


def _ancestors(outcome_event_id: str, context: RootCauseContext) -> tuple[dict[str, int], bool]:
    """Return every ancestor at its shortest backward distance, and whether it truncated.

    Backward breadth-first, so a candidate reachable by two routes is settled at the shorter
    -- the same never-count-twice rule module 12 applies forwards. The distance is what
    `earliness_rank` is derived from: further back is earlier in the chain, which is a
    STRUCTURAL statement about the graph and deliberately not a reading of any clock. Two
    candidates the same distance back are the same rank, and the report says so rather than
    breaking the tie on a timestamp the source may never have observed.
    """
    cap = context.parameters.candidate_cap or CANDIDATE_SEARCH_CEILING
    distances: dict[str, int] = {}
    frontier: list[tuple[str, int]] = [(outcome_event_id, 0)]
    truncated = False
    while frontier:
        event_id, distance = frontier.pop(0)
        for link in context.propagation.view.links_into(event_id):
            source = link.source_event_id
            if source in distances or source == outcome_event_id:
                continue
            if len(distances) >= cap:
                truncated = True
                continue
            distances[source] = distance + 1
            frontier.append((source, distance + 1))
    return distances, truncated


def _chain(
    cause_event_id: str, outcome_event_id: str, context: RootCauseContext
) -> tuple[PathConfidence, tuple[tuple[str, str, str], ...], tuple[str, ...]]:
    """Compose belief about the shortest chain from one cause to the outcome.

    Returns the composed confidence, the links cause-first, and the evidence identifiers
    behind them. The shortest chain is used rather than the strongest: the strongest would
    make the reported route depend on the scores it is then used to explain, which is
    circular, and the shortest is a property of the graph alone.
    """
    parent: dict[str, tuple[str, GraphLink]] = {}
    frontier: list[str] = [cause_event_id]
    seen = {cause_event_id}
    while frontier and outcome_event_id not in parent:
        event_id = frontier.pop(0)
        for link in context.propagation.view.links_from(event_id):
            if link.target_event_id in seen:
                continue
            seen.add(link.target_event_id)
            parent[link.target_event_id] = (event_id, link)
            frontier.append(link.target_event_id)
    route: list[tuple[str, str, str]] = []
    scalars: list[float] = []
    classes: list[ProvenanceClass] = []
    cursor = outcome_event_id
    while cursor in parent:
        source, link = parent[cursor]
        route.append((source, cursor, link.edge_kind))
        scalars.append(link.link_scalar)
        classes.append(link.provenance_class)
        cursor = source
    route.reverse()
    scalars.reverse()
    declared = context.propagation.parameters.path_confidence_composition or DEFAULT_COMPOSER
    if not scalars:
        # No route survives the bounds. The candidate is still reported -- it IS an
        # ancestor -- with a single-link chain of zero, which is the honest statement that
        # nothing joins it to the outcome inside the declared depth.
        scalars = [0.0]
        route = [(cause_event_id, outcome_event_id, "UNREACHABLE_WITHIN_BOUND")]
        classes = [ProvenanceClass.ASSUMED]
    chain = PathConfidence(
        composed=compose(scalars, declared),
        composition=declared,
        product=compose(scalars, "independent_product_v1"),
        path_length=len(scalars),
        link_scalars=tuple(scalars),
        provenance_class=combine(*classes) if classes else ProvenanceClass.ASSUMED,
    )
    return chain, tuple(route), tuple(sorted({source for source, _, _ in route}))


def _partial_data(route: tuple[tuple[str, str, str], ...], context: RootCauseContext) -> str | None:
    """Flag a chain that passes through an instant the source never observed.

    `docs/architecture.md` §2 makes this module responsible for it: a chain containing a
    timeline gap is RANKED and FLAGGED, and the flag must survive into the explanation. On
    the reference dataset this fires on essentially everything -- not one event in the
    measured slice carries an `OBSERVED` timestamp (R-22) -- and that is the point: a
    ranking built on inferred instants should say so on every row rather than nowhere.
    """
    events = context.propagation.events_by_id()
    unplaced: list[str] = []
    assumed: list[str] = []
    for source, target, _ in route:
        for event_id in (source, target):
            event = events.get(event_id)
            if event is None:
                unplaced.append(event_id)
                continue
            if event.occurred_at.precision is Precision.UNKNOWN:
                unplaced.append(event_id)
            elif event.occurred_at.provenance is not ProvenanceClass.OBSERVED:
                assumed.append(event_id)
    if not unplaced and not assumed:
        return None
    parts: list[str] = []
    if unplaced:
        parts.append(
            f"{len(set(unplaced))} event(s) on this chain were never placed in time by the "
            "source"
        )
    if assumed:
        parts.append(
            f"{len(set(assumed))} event(s) carry an instant that was computed rather than "
            "recorded"
        )
    return (
        "PARTIAL DATA: "
        + "; ".join(parts)
        + ". The chain is ranked and this flag travels with it into every explanation "
        "built on it. A precedence resting on a computed instant is a precedence resting "
        "on the arithmetic that produced it."
    )


def _standing(event: Event, context: RootCauseContext) -> ActionabilityStanding:
    """Read what is known about acting on one candidate, cross-checking stamp against pack."""
    declared = context.declares_actionable(event)
    view = context.declaration_for(event.event_type)
    disagreement = None
    if declared is not None and declared != event.is_actionable:
        disagreement = (
            f"the event was stamped is_actionable={event.is_actionable} at generation time "
            f"and the pack now declares {declared} for type {event.event_type}. The STAMP is "
            "authoritative (ADR-0008) and is what this ranking used. The disagreement is "
            "reported rather than resolved: it usually means the run was generated under an "
            "earlier ontology, and silently preferring either value would move the headline "
            "answer with nothing recording that it had."
        )
    return ActionabilityStanding(
        is_actionable=event.is_actionable,
        pack_declares=declared,
        cost_class=view.cost_class if view is not None else None,
        cost_rank=context.cost_rank(event.event_type),
        severity_class=view.severity_class if view is not None else None,
        severity_rank=context.severity_rank(event.event_type),
        disagreement=disagreement,
    )


def _ranked(
    cause_event_id: str,
    distance: int,
    outcome_event_id: str,
    context: RootCauseContext,
) -> RankedCause | None:
    """Assemble one candidate into a ranked result, or None if its event is unknown."""
    events = context.propagation.events_by_id()
    event = events.get(cause_event_id)
    if event is None:
        return None
    chain, route, _ = _chain(cause_event_id, outcome_event_id, context)
    prevented = prevented_by_removing(cause_event_id, (cause_event_id,), context.propagation)
    ranker = context.parameters.ranking_function
    evidence = tuple(sorted(set(event.evidence_record_ids))) or (event.event_id,)
    return RankedCause(
        event_id=cause_event_id,
        event_type=event.event_type,
        prevented_event_ids=prevented.prevented_event_ids,
        prevented_magnitude=prevented.prevented_total,
        prevented_unit=prevented.unit,
        whole_magnitude=prevented.whole_total,
        prevented_share=share_of_whole(prevented),
        prevented_absent_because=prevented.absent_because,
        actionability=_standing(event, context),
        earliness_rank=distance,
        chain=chain,
        confidence=event.confidence,
        recurrence=recurrence_of(
            cause_event_id,
            outcome_event_id,
            context.propagation,
            context.parameters.recurrence_minimum_support,
        ),
        sequencing_value=(
            rank_value(prevented.prevented_total, chain.composed, ranker)
            if ranker is not None
            else None
        ),
        sequencing_function=ranker,
        evidence_item_ids=evidence,
        chain_links=route,
        provenance_class=combine(event.provenance_class, chain.provenance_class),
        partial_data_flag=_partial_data(route, context),
    )


def analyze_root_causes(
    outcome_event_id: str, context: RootCauseContext, envelope: OutputEnvelope
) -> RootCauseResult:
    """Rank the causes of one outcome, under the standing the graph view declares.

    Deterministic: two calls over one input produce byte-identical artifacts, including the
    rendered report. Every grouping is sorted and no dictionary is read in insertion
    sequence (`CONVENTIONS.md` §11).

    The four views are returned as four fields and are never collapsed. A `TradeOff` is
    emitted for every pair that names different events, so a user who disagrees with the
    recommendation can see the alternative and why it was not preferred.
    """
    distances, truncated = _ancestors(outcome_event_id, context)
    causes = tuple(
        sorted(
            (
                ranked
                for cause_event_id, distance in sorted(distances.items())
                if (ranked := _ranked(cause_event_id, distance, outcome_event_id, context))
                is not None
            ),
            key=lambda cause: cause.sort_key(),
        )
    )
    # Earliness is a RANK over the backward distances, not the distance itself: two
    # candidates equally far back share a rank, and the report says so rather than breaking
    # a structural tie on a clock the source may never have read.
    depths = sorted({cause.earliness_rank for cause in causes}, reverse=True)
    ranks = {depth: index + 1 for index, depth in enumerate(depths)}
    causes = tuple(
        cause.model_copy(update={"earliness_rank": ranks[cause.earliness_rank]}) for cause in causes
    )
    named = (
        (ViewName.EARLIEST, earliest(causes)),
        (ViewName.HIGHEST_CONSEQUENCE, highest_consequence(causes)),
        (ViewName.MOST_ACTIONABLE, most_actionable(causes)),
    )
    shortlist = recommended(causes, context.parameters.minimum_chain_scalar)
    ranking = RootCauseRanking(
        run_id=context.run_id,
        standing=context.propagation.view.standing,
        outcome_event_id=outcome_event_id,
        earliest_cause=named[0][1],
        highest_consequence_cause=named[1][1],
        most_actionable_cause=named[2][1],
        actionable_root_causes=shortlist,
        considered=causes,
        trade_offs=trade_offs(
            (*named, (ViewName.RECOMMENDED, shortlist[0] if shortlist else None)), causes
        ),
        candidate_search_truncated=truncated,
        sequencing_function=context.parameters.ranking_function,
        provenance_class=(
            ProvenanceClass.STATISTICAL
            if context.propagation.view.standing is not GraphStanding.STATED
            else combine(*(cause.provenance_class for cause in causes))
            if causes
            else ProvenanceClass.ASSUMED
        ),
    )
    propagation = analyze_propagation(outcome_event_id, context.propagation, envelope)
    return RootCauseResult(
        ranking=ranking,
        propagation=propagation,
        report=build_report(ranking, context, envelope),
    )
