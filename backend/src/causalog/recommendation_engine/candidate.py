"""Where an operator could act, and the one gate that decides whether they may be told to.

prd.md §32 asks each causal chain to expose its intervention opportunities. It does not say
how to find them, and there is no single right answer -- so this module runs four
independent generators and TAGS each candidate with the one that proposed it. A reader can
then see why a node is on the list, and can dismiss a whole generator's output without
dismissing the others. Module 9 established the pattern for exactly this reason.

THE GATE
--------
`admissible_target` is the only place in this engine that decides whether an event type may
be recommended. It is called once, from `discover`, and a law test asserts that structurally
over the AST -- the mechanism `causal_graph_builder/policy.py` uses to keep `INFERRED`
assignment in one file. A gate called from four generators would be four gates, and the
fourth would eventually be forgotten.

A refused candidate becomes a `RefusedCandidate` naming the declaration that refused it. It
is never dropped silently: "no candidate was found here" and "a candidate was found and the
pack forbids acting on it" are completely different statements about a domain, and a list
that showed only the first would read as an absence of opportunity.

WHAT THE GATE READS, AND WHY IT READS IT TWICE
-----------------------------------------------
`Event.is_actionable` is stamped at generation time; `ActionabilityView.actionable` is
flattened from the pack for this run. They should agree. When they do not, the candidate is
refused and the disagreement is REPORTED rather than resolved -- module 11's
`ActionabilityStanding` exists for the same situation and takes the same position. Picking
a winner would mean this module deciding which of two declarations about the domain is
right, which is precisely the judgement it has no standing to make.

NOTHING HERE MAKES AN ACTIONABILITY CLAIM TRUE. R-15 records that a mis-declared flag
silently changes the headline ranking and that nothing in this system can detect it; R-25
records that a mis-declared cost or operational risk does the same to this module's
sequencing. Carrying the declaration further does not validate it.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.propagation_analyzer import reachable_from
from causalog.core.ontology_view import ActionabilityView
from causalog.recommendation_engine.context import RecommendationContext

__all__ = [
    "Candidate",
    "CandidateSource",
    "Discovery",
    "RefusalReason",
    "RefusedCandidate",
    "admissible_target",
    "discover",
]


class CandidateSource(str, Enum):
    """Which generator proposed a node, so a reader can weigh or dismiss it by origin."""

    HIGH_LEVERAGE = "HIGH_LEVERAGE"
    """Largest set of consequences reachable from it. prd.md §32's leverage reading."""

    LOW_COST = "LOW_COST"
    """Lowest declared cost class. The cheap act, whether or not it is the big one."""

    EARLY = "EARLY"
    """Earliest in its chain. prd.md §29's earliness, as a source rather than as a term."""

    LOOP_WEAKEST_LINK = "LOOP_WEAKEST_LINK"
    """The link a detected feedback loop names as cheapest to break (prd.md §31)."""


class RefusalReason(str, Enum):
    """Why a node an operator might act on was not offered as one.

    Closed, and every member names a declaration the node was checked against, so a refusal
    tells a reader what would have admitted it rather than only that it failed.
    """

    NOT_ACTIONABLE = "NOT_ACTIONABLE"
    """The pack declares that no operator can act on this kind of occurrence."""

    ACTIONABILITY_NOT_DECLARED = "ACTIONABILITY_NOT_DECLARED"
    """The pack declares nothing about this event type at all. Not the same as a refusal."""

    STAMP_DISAGREES_WITH_PACK = "STAMP_DISAGREES_WITH_PACK"
    """The event's stamped flag and this run's pack declaration do not agree."""

    COST_NOT_DECLARED = "COST_NOT_DECLARED"
    """Declared actionable with no cost class. Ranking it would rank it as free."""

    UNKNOWN_TARGET = "UNKNOWN_TARGET"
    """The graph names an occurrence the facts do not hold."""

    LOOP_NOT_GENUINE = "LOOP_NOT_GENUINE"
    """The circuit is a temporal artifact; it names no link to break (ADR-0056)."""


class RefusedCandidate(BaseModel):
    """One node that was found and not offered, with what refused it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    source: CandidateSource
    reason: RefusalReason
    #: The declaration this was checked against, named so a pack author can act on it.
    checked_against: str = Field(min_length=1)
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[str, str, str]:
        """Canonical sequence: by node, then generator, then reason."""
        return (self.event_id, self.source.value, self.reason.value)


class Candidate(BaseModel):
    """One node an operator may be told to act on, with what the pack says about acting.

    `reach` is the consequence set the node transmits into, computed once here so that the
    cut-set search, the interaction test and the estimator all read one number rather than
    three that could disagree.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    #: Every generator that proposed this node, sorted. A node found by three generators is
    #: one candidate carrying three reasons, never three candidates.
    sources: tuple[CandidateSource, ...] = Field(min_length=1)
    cost_class: str
    severity_class: str
    #: `None` where the pack declares no operational risk for this type (ADR-0073). Absent
    #: is reported, never defaulted, and it costs the candidate its risk term.
    risk_class: str | None = None
    #: Consequences reachable from this node, sorted. Attributed to the node, not to routes.
    reach: tuple[str, ...] = ()
    #: The joint group this node belongs to, when it belongs to one. A cut set holding this
    #: node must hold the whole group, because removing one member of a joint cause does not
    #: prevent the effect (ADR-0069).
    joint_cause_group_id: str | None = None

    def sort_key(self) -> tuple[int, str]:
        """Canonical sequence: widest reach first, then by identifier to break ties."""
        return (-len(self.reach), self.event_id)


def admissible_target(
    event_id: str, context: RecommendationContext
) -> tuple[ActionabilityView | None, RefusedCandidate | None]:
    """Decide whether one node may be recommended, and say what decided it.

    **The only gate in this package.** Called once, from `discover`. See this module's
    docstring for why that is asserted structurally rather than left to convention.

    Returns:
        `(view, None)` when the node may be recommended, `(None, refusal)` when it may not.
        Exactly one of the two is ever populated.
    """
    events = context.propagation.events_by_id()
    event = events.get(event_id)
    if event is None:
        return (
            None,
            RefusedCandidate(
                event_id=event_id,
                event_type="UNKNOWN",
                source=CandidateSource.HIGH_LEVERAGE,
                reason=RefusalReason.UNKNOWN_TARGET,
                checked_against="the run's facts",
                detail=(
                    f"the graph names occurrence {event_id}, which this run's facts do not "
                    "hold. A recommendation to act on something that was never observed "
                    "cannot be traced back to anything."
                ),
            ),
        )

    declared = context.actionability_for(event.event_type)
    if declared is None:
        return (
            None,
            RefusedCandidate(
                event_id=event_id,
                event_type=event.event_type,
                source=CandidateSource.HIGH_LEVERAGE,
                reason=RefusalReason.ACTIONABILITY_NOT_DECLARED,
                checked_against=f"ontology event_types.{event.event_type}.actionability",
                detail=(
                    f"the pack declares no actionability for '{event.event_type}'. That is "
                    "not a refusal and is not read as one: it is a gap, and it is reported "
                    "so a pack author can close it rather than so this run can assume past "
                    "it (ADR-0049)."
                ),
            ),
        )

    if declared.actionable != event.is_actionable:
        return (
            None,
            RefusedCandidate(
                event_id=event_id,
                event_type=event.event_type,
                source=CandidateSource.HIGH_LEVERAGE,
                reason=RefusalReason.STAMP_DISAGREES_WITH_PACK,
                checked_against=(
                    f"Event.is_actionable={event.is_actionable} against ontology "
                    f"event_types.{event.event_type}.actionability.actionable="
                    f"{declared.actionable}"
                ),
                detail=(
                    "the flag stamped onto this occurrence when it was generated and the "
                    "flag this run's pack declares do not agree. The disagreement is "
                    "reported and NOT resolved: choosing a winner would be this module "
                    "deciding which of two declarations about the domain is right, and "
                    "nothing here can establish that (R-15)."
                ),
            ),
        )

    if not declared.actionable:
        return (
            None,
            RefusedCandidate(
                event_id=event_id,
                event_type=event.event_type,
                source=CandidateSource.HIGH_LEVERAGE,
                reason=RefusalReason.NOT_ACTIONABLE,
                checked_against=f"ontology event_types.{event.event_type}.actionability",
                detail=(
                    f"'{event.event_type}' is declared not actionable: no operator can act "
                    "on this kind of occurrence, so proposing it would be proposing "
                    "something nobody can do."
                ),
            ),
        )

    if declared.cost_class is None:
        return (
            None,
            RefusedCandidate(
                event_id=event_id,
                event_type=event.event_type,
                source=CandidateSource.HIGH_LEVERAGE,
                reason=RefusalReason.COST_NOT_DECLARED,
                checked_against=(
                    f"ontology event_types.{event.event_type}.actionability.cost_class"
                ),
                detail=(
                    "declared actionable with no cost class. The pack schema forbids this "
                    "and it is checked again here, because ranking a costless candidate "
                    "would rank it as free and place it above every candidate that "
                    "declared a cost honestly."
                ),
            ),
        )
    return (declared, None)


def _joint_group_of(event_id: str, context: RecommendationContext) -> str | None:
    """Return the joint cause group this node contributes to, or `None`.

    A node in two groups is returned under the first by sorted identifier, deterministically.
    Two groups sharing a contributor is a graph the builder admits, and picking the lowest
    identifier keeps this function total without inventing a preference between them.
    """
    for group in sorted(context.joint_groups, key=lambda item: item.joint_cause_group_id):
        if event_id in group.member_source_event_ids:
            return group.joint_cause_group_id
    return None


def _high_leverage(context: RecommendationContext) -> tuple[str, ...]:
    """Return nodes by how much they transmit into, widest first.

    Leverage is the size of the reachable consequence SET, never a count of routes. A node
    that reaches one consequence four ways has leverage one (ADR-0061), and `reachable_from`
    already returns a set, so the guarantee comes from the primitive rather than from care
    taken here.
    """
    reach = {
        event_id: len(reachable_from(event_id, context.propagation))
        for event_id in context.propagation.events_by_id()
    }
    return tuple(
        sorted(
            (event_id for event_id, size in reach.items() if size > 0),
            key=lambda event_id: (-reach[event_id], event_id),
        )
    )


def _low_cost(context: RecommendationContext) -> tuple[str, ...]:
    """Return nodes whose declared cost class is cheapest, cheapest first.

    Cheap and high-leverage are different questions and this engine refuses to merge them:
    prd.md §32's own worked example is a LOW cost with a HIGH benefit, which is only
    interesting because the two were asked separately. Sorted by rank, then identifier.
    """
    from causalog.recommendation_engine.context import vocabulary_rank

    ranked: list[tuple[int, str]] = []
    for event_id, event in context.propagation.events_by_id().items():
        declared = context.actionability_for(event.event_type)
        if declared is None or not declared.actionable:
            continue
        rank = vocabulary_rank(context.cost_vocabulary, declared.cost_class)
        if rank is None:
            continue
        ranked.append((rank, event_id))
    return tuple(event_id for _, event_id in sorted(ranked))


def _early(context: RecommendationContext) -> tuple[str, ...]:
    """Return nodes that transmit into something and are transmitted into by nothing.

    Structural earliness -- a source of the walked graph -- rather than earliness in time.
    The two agree wherever LAW-TIME held when the links were made, and where they disagree
    the structural reading is the one this graph can defend: a timestamp on this dataset is
    frequently arithmetic rather than observation (R-22), and sequencing candidates by a
    computed instant would rank on the arithmetic.
    """
    arriving: set[str] = set()
    for event_id in context.propagation.events_by_id():
        for link in context.propagation.view.links_from(event_id):
            arriving.add(link.target_event_id)
    sources = tuple(
        sorted(
            event_id
            for event_id in context.propagation.events_by_id()
            if event_id not in arriving and context.propagation.view.links_from(event_id)
        )
    )
    return sources


def _loop_weakest_links(
    context: RecommendationContext,
) -> tuple[tuple[str, ...], tuple[RefusedCandidate, ...]]:
    """Return the event TYPES each genuine loop names as cheapest to break.

    Loops are detected over the event-type projection (ADR-0056) and this module does not
    re-detect them; it reads `weakest_link_index`, which the detector sets to `None` on any
    circuit it did not classify GENUINE. That `None` is the refusal, and it is honoured
    rather than worked around -- naming an intervention point on a temporal artifact would
    invite acting on one.

    Returns the participant TYPE names; the caller resolves them to occurrences.
    """
    types: list[str] = []
    refusals: list[RefusedCandidate] = []
    # A loop carries no identifier of its own; `participants` is canonical -- the circuit in
    # traversal sequence from its lexicographically smallest type -- so joining it names one
    # circuit exactly once however it was discovered.
    for loop in sorted(context.loops, key=lambda item: item.participants):
        circuit = "->".join(loop.participants)
        if loop.weakest_link_index is None:
            refusals.append(
                RefusedCandidate(
                    event_id=circuit,
                    event_type=loop.participants[0],
                    source=CandidateSource.LOOP_WEAKEST_LINK,
                    reason=RefusalReason.LOOP_NOT_GENUINE,
                    checked_against=f"FeedbackLoop.classification={loop.classification.value}",
                    detail=(
                        f"circuit {circuit} names no link to break because it is classified "
                        f"{loop.classification.value} rather than GENUINE. "
                        f"{loop.classification_reason or ''}"
                    ).strip(),
                )
            )
            continue
        types.append(loop.members[loop.weakest_link_index].source_event_type)
    return (tuple(types), tuple(refusals))


class Discovery(BaseModel):
    """Everything the four generators found: what may be offered and what may not.

    Both halves are published. A run that found forty nodes and could recommend none is a
    finding about the pack's actionability declarations, and it is invisible in a list that
    only shows what survived.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[Candidate, ...] = ()
    refused: tuple[RefusedCandidate, ...] = ()
    #: How many distinct nodes the generators proposed before the gate, so a reader can see
    #: the attrition rather than infer it.
    proposed_count: int = Field(default=0, ge=0)


def discover(context: RecommendationContext) -> Discovery:
    """Run the four generators and gate everything they propose.

    **The gate is called from here and from nowhere else.** A node proposed by several
    generators is gated once and carries every source that proposed it, so a candidate list
    holds one entry per node and the refusal ledger holds one entry per node too.

    Deterministic: generators are read in a fixed sequence, every grouping is sorted, and no
    dictionary is read in insertion sequence (`CONVENTIONS.md` §11).
    """
    from causalog.recommendation_engine.context import vocabulary_rank  # noqa: F401

    events = context.propagation.events_by_id()
    loop_types, loop_refusals = _loop_weakest_links(context)
    loop_nodes = tuple(
        sorted(event_id for event_id, event in events.items() if event.event_type in loop_types)
    )

    proposals: dict[str, set[CandidateSource]] = {}
    for source, nodes in (
        (CandidateSource.HIGH_LEVERAGE, _high_leverage(context)),
        (CandidateSource.LOW_COST, _low_cost(context)),
        (CandidateSource.EARLY, _early(context)),
        (CandidateSource.LOOP_WEAKEST_LINK, loop_nodes),
    ):
        for event_id in nodes:
            proposals.setdefault(event_id, set()).add(source)

    candidates: list[Candidate] = []
    refused: list[RefusedCandidate] = list(loop_refusals)
    for event_id in sorted(proposals):
        sources = tuple(sorted(proposals[event_id], key=lambda item: item.value))
        declared, refusal = admissible_target(event_id, context)
        if refusal is not None:
            # The gate reports one source because it does not know which asked; restate it
            # with the first that did, so a reader can find the generator responsible.
            refused.append(refusal.model_copy(update={"source": sources[0]}))
            continue
        if declared is None or declared.cost_class is None:  # pragma: no cover -- narrowed
            # Unreachable: the gate returns exactly one of a view or a refusal, and a view
            # it returns always carries a cost class. Written as a branch rather than an
            # assertion because assertions are stripped under -O, and the one thing that
            # must not happen under optimization is a costless candidate ranking as free.
            continue
        candidates.append(
            Candidate(
                event_id=event_id,
                event_type=events[event_id].event_type,
                sources=sources,
                cost_class=declared.cost_class,
                severity_class=declared.severity_class,
                risk_class=declared.risk_class,
                reach=tuple(sorted(reachable_from(event_id, context.propagation))),
                joint_cause_group_id=_joint_group_of(event_id, context),
            )
        )

    node_cap = context.parameters.cut_set_node_cap
    if node_cap is not None and len(candidates) > node_cap:
        candidates = sorted(candidates, key=lambda item: item.sort_key())[:node_cap]

    return Discovery(
        candidates=tuple(sorted(candidates, key=lambda item: item.sort_key())),
        refused=tuple(sorted(refused, key=lambda item: item.sort_key())),
        proposed_count=len(proposals),
    )
