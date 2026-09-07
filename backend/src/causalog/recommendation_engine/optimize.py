"""Module 14's entry point: discover, cost, estimate, rank, and withhold what cannot stand.

THE SEQUENCE IS THE ARGUMENT
-----------------------------
Discovery gates everything before anything is estimated, so a non-actionable node never
reaches a simulator and never costs the budget. Estimation runs per candidate before any
ranking, so the benefit ceiling every desirability is expressed against is a property of the
whole set rather than of whichever candidate happened to be scored first. The confidence
floor is applied AFTER scoring and BEFORE publication, so the ledger can say how far below
the floor a candidate fell rather than only that it was absent.

WHY A DIAGNOSTIC GRAPH IS REFUSED BY DEFAULT (ADR-0072, OQ-026)
----------------------------------------------------------------
OQ-026 requires modules 13 and 14 to refuse a graph the engine does not stand behind. It
matters more here than it did there: a counterfactual is a question, and a recommendation is
an instruction. So the guard is module 13's, in the same shape and for the same reason, with
the same two details that make it hold rather than merely intend:

* **This module never names `UNPROMOTED_DIAGNOSTIC`.** It compares `is not
  GraphStanding.STATED`. `diagnostic_view` remains the engine's only construction site of
  that member, and a caller outside the engine decides which adapter to call.
* **The notices are imported, never restated.** Two copies of a caveat have drifted once in
  this repository.

WHAT THIS MODULE STRUCTURALLY CANNOT DO
-----------------------------------------
It cannot infer a cost (`cost.py`), cannot recommend a non-actionable node (`candidate.py`),
cannot estimate a benefit itself (`estimate.py`), cannot sum two benefits (`portfolio.py`),
cannot publish a recommendation without confidence, evidence and assumptions
(`recommendation.py`), and cannot weight the objectives itself (`rank.py` reads the pack).
Each of those is enforced in the file named, and each is asserted by a test.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.propagation_analyzer import GraphStanding
from causalog.core.errors import ContractViolationError
from causalog.core.run import OutputEnvelope
from causalog.core.types import ConfidenceVector
from causalog.recommendation_engine.candidate import (
    Candidate,
    CandidateSource,
    Discovery,
    discover,
)
from causalog.recommendation_engine.context import RecommendationContext
from causalog.recommendation_engine.cost import (
    CostAssessment,
    RiskAssessment,
    assess_cost,
    assess_risk,
)
from causalog.recommendation_engine.cutset import CutSet, SearchRegime, find_cut_sets
from causalog.recommendation_engine.estimate import BenefitEstimate, estimate
from causalog.recommendation_engine.portfolio import PortfolioBenefit, portfolio_benefit
from causalog.recommendation_engine.rank import confidence_of, desirability_of, frontier_of, orient
from causalog.recommendation_engine.recommendation import (
    Recommendation,
    WithheldRecommendation,
    WithholdingReason,
)

__all__ = ["RecommendationResult", "optimize"]


class RecommendationResult(BaseModel):
    """One run of module 14: what is recommended, what was not, and why either way.

    All four fields are published together and none is derivable from the others. A run that
    discovered forty nodes, refused thirty-eight at the gate and withheld the other two for
    want of belief is a strong finding about a pack and a dataset, and it is invisible in a
    `recommendations` field that is simply empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendations: tuple[Recommendation, ...] = ()
    withheld: tuple[WithheldRecommendation, ...] = ()
    discovery: Discovery
    cut_sets: tuple[CutSet, ...] = ()
    #: Named declarations that were absent, so a run that could not rank says which knob
    #: would have let it. Never a default (ADR-0049).
    policy_gaps: tuple[str, ...] = ()


def _evidence_of(
    node_event_ids: tuple[str, ...], context: RecommendationContext
) -> tuple[str, ...]:
    """Return the evidence records behind the nodes an act touches, sorted and unique.

    LAW-EVIDENCE's chain for a recommendation. An occurrence with no evidence record cannot
    contribute one, and a recommendation whose whole membership has none is refused by
    `Recommendation`'s own `min_length=1` -- it becomes a `NO_EVIDENCE` entry in the ledger
    rather than a published entry with an empty list.
    """
    events = context.propagation.events_by_id()
    found: set[str] = set()
    for event_id in node_event_ids:
        event = events.get(event_id)
        if event is not None:
            found.update(event.evidence_record_ids)
    return tuple(sorted(found))


def _sources_of(members: tuple[Candidate, ...]) -> tuple[CandidateSource, ...]:
    """Return every generator that proposed any member, sorted and unique.

    Shared by the published list and the withheld ledger, so a candidate's origin reads the
    same whichever of the two it ends up in.
    """
    return tuple(
        sorted(
            {source for candidate in members for source in candidate.sources},
            key=lambda source: source.value,
        )
    )


def _describe(members: tuple[Candidate, ...]) -> str:
    """Say what the act is, in the pack's own type names and nothing else."""
    types = ", ".join(sorted({candidate.event_type for candidate in members}))
    if len(members) == 1:
        return f"Act on the occurrence of {types} identified below."
    return f"Act together on {len(members)} occurrences, of type(s) {types}."


def _risks_of(
    item: BenefitEstimate, context: RecommendationContext, cut_set: CutSet
) -> tuple[str, ...]:
    """Enumerate hazards a reader must weigh that are not the declared operational risk."""
    found: list[str] = []
    if context.standing is not GraphStanding.STATED:
        found.append(
            "this recommendation was derived over a graph the engine does not stand behind; "
            "nothing in it was asserted as a causal claim by this engine."
        )
    if cut_set.not_minimal_because:
        found.append(cut_set.not_minimal_because)
    if item.attributed_absent_because:
        found.append(
            f"the downstream share could not be attributed: {item.attributed_absent_because}"
        )
    if item.rejected_detail:
        found.append(
            f"{len(item.rejected_detail)} proposed change(s) in this act were refused before "
            "simulation; the act as simulated may be narrower than the act as described."
        )
    if item.affected_instance_count == 0:
        found.append(
            "no process instance was identified as affected, so the scope figures below are "
            "empty rather than small."
        )
    return tuple(sorted(found))


def optimize(
    context: RecommendationContext,
    envelope: OutputEnvelope,
    *,
    accept_unpromoted: bool = False,
) -> RecommendationResult:
    """Rank the acts this graph supports, and withhold the ones it does not.

    Deterministic: two calls over one input produce byte-identical artifacts. Every grouping
    is sorted and no dictionary is read in insertion sequence (`CONVENTIONS.md` §11).

    Args:
        context: this run's inputs.
        envelope: the run's output envelope (`CONVENTIONS.md` §11).
        accept_unpromoted: opt in to recommending over a graph the engine does not stand
            behind. **Refused by default** (OQ-026, ADR-0072).

    Raises:
        ContractViolationError: if the view's standing is not `STATED` and the caller did
            not opt in.
    """
    standing = context.standing
    if standing is not GraphStanding.STATED and not accept_unpromoted:
        raise ContractViolationError(
            f"recommendation_engine.optimize received a graph whose standing is "
            f"{standing.value}. Nothing in that graph was asserted by the engine, and "
            "propagation_analyzer/view.py states in fixed text that it is not an input to "
            "recommendation (OQ-026). A counterfactual over such a graph is a question; a "
            "recommendation over it is an instruction to a person who will be held "
            "accountable for following it. Pass accept_unpromoted=True to do it anyway; "
            "everything produced will be disowned by the artifacts that carry it."
        )

    gaps: list[str] = []
    found = discover(context)
    cut_sets, cut_set_gap, oversized = find_cut_sets(found.candidates, context)
    if cut_set_gap is not None:
        gaps.append(cut_set_gap)
    gaps.extend(oversized)

    by_id = {candidate.event_id: candidate for candidate in found.candidates}
    estimates: dict[str, BenefitEstimate] = {}
    for candidate in found.candidates:
        estimates[candidate.event_id] = estimate(
            (candidate.event_id,), context, envelope, accept_unpromoted=accept_unpromoted
        )

    # Singletons are cut sets of size one and `find_cut_sets` records every one of them, so
    # one code path scores both and the ranked list is never narrower than the candidate
    # list. This fallback covers only the run whose pack declared no cut-set bounds at all:
    # the SEARCH was unavailable, the candidates were not, and each is still worth ranking on
    # its own benefit with its coverage reported as unmeasured.
    considered = cut_sets or tuple(
        CutSet(
            member_event_ids=(candidate.event_id,),
            chains_broken=0,
            chains_considered=0,
            regime=SearchRegime.NOT_RUNNABLE,
            not_minimal_because=(
                cut_set_gap
                or "no cut-set search ran, so this act's coverage of the chains was never "
                "measured. It is ranked on its own benefit alone."
            ),
        )
        for candidate in found.candidates
    )

    scored: list[_Scored] = []
    for cut_set in considered:
        members = tuple(
            by_id[event_id] for event_id in cut_set.member_event_ids if event_id in by_id
        )
        if not members:
            continue
        if len(members) == 1:
            scored.append(_Scored(cut_set, members, estimates[members[0].event_id], None))
            continue
        # A set is simulated ONCE, as a set, and the portfolio contrast is read from the
        # same call rather than from a second one. Two simulations of one hypothetical
        # could disagree, and the artifact would carry whichever was assembled last.
        joint = portfolio_benefit(
            members, estimates, context, envelope, accept_unpromoted=accept_unpromoted
        )
        scored.append(
            _Scored(
                cut_set,
                members,
                estimate(
                    cut_set.member_event_ids,
                    context,
                    envelope,
                    accept_unpromoted=accept_unpromoted,
                ),
                joint,
            )
        )

    ceiling = max(
        (item.estimate.benefit.high for item in scored if item.estimate.benefit.high is not None),
        default=None,
    )
    return _publish(scored, ceiling, found, cut_sets, tuple(gaps), context)


class _Scored(NamedTuple):
    """One act with everything measured about it, before any of it is ranked."""

    cut_set: CutSet
    members: tuple[Candidate, ...]
    estimate: BenefitEstimate
    portfolio: PortfolioBenefit | None


def _publish(
    scored: list[_Scored],
    ceiling: float | None,
    found: Discovery,
    cut_sets: tuple[CutSet, ...],
    gaps: tuple[str, ...],
    context: RecommendationContext,
) -> RecommendationResult:
    """Rank what was measured, withhold what cannot stand, and say which is which.

    The confidence floor is a GATE and is applied here rather than as a term in the
    scalarization. A ranked list is read as a list of things to do, and position in it
    outweighs any number printed beside it -- so a candidate below the floor leaves the list
    entirely and enters the ledger, where the threshold that withheld it is named.
    """
    floor = context.parameters.minimum_belief_to_publish
    limit = context.parameters.maximum_recommendations
    policy_gaps = list(gaps)
    if floor is None:
        policy_gaps.append(
            "the pack declares no recommendation.minimum_belief_to_publish, so no "
            "candidate could be withheld for want of belief. Nothing is defaulted: the "
            "threshold decides how sure is sure enough to tell an operator to act, which is "
            "the most domain-specific number module 14 reads (ADR-0079)."
        )

    withheld: list[WithheldRecommendation] = []
    admitted: list[
        tuple[_Scored, CostAssessment, RiskAssessment, ConfidenceVector, float | None, str | None]
    ] = []
    for item in scored:
        types = tuple(sorted({candidate.event_type for candidate in item.members}))
        cost = assess_cost(item.members[0].cost_class, context)
        risk = assess_risk(item.members[0].risk_class, context)
        evidence = _evidence_of(item.cut_set.member_event_ids, context)
        confidence = confidence_of(item.estimate, evidence)

        if item.estimate.benefit.absent_because is not None:
            withheld.append(
                WithheldRecommendation(
                    node_event_ids=item.cut_set.member_event_ids,
                    node_event_types=types,
                    reason=WithholdingReason.BENEFIT_NOT_MEASURABLE,
                    checked_against="counterfactual_engine.simulate",
                    detail=item.estimate.benefit.absent_because,
                    belief_scalar=confidence.scalar,
                    expected_benefit=item.estimate.benefit,
                    implementation_cost=cost,
                    operational_risk=risk,
                    sources=_sources_of(item.members),
                    chains_broken=item.cut_set.chains_broken,
                    chains_considered=item.cut_set.chains_considered,
                )
            )
            continue
        if not evidence:
            withheld.append(
                WithheldRecommendation(
                    node_event_ids=item.cut_set.member_event_ids,
                    node_event_types=types,
                    reason=WithholdingReason.NO_EVIDENCE,
                    checked_against="Event.evidence_record_ids",
                    detail=(
                        "no evidence record stands behind any occurrence this act touches, "
                        "so LAW-EVIDENCE cannot be satisfied and prd.md Principle 5 refuses "
                        "to show it. The Recommendation type could not have been "
                        "constructed either; this ledger entry is what exists instead."
                    ),
                    belief_scalar=confidence.scalar,
                    expected_benefit=item.estimate.benefit,
                    implementation_cost=cost,
                    operational_risk=risk,
                    sources=_sources_of(item.members),
                    chains_broken=item.cut_set.chains_broken,
                    chains_considered=item.cut_set.chains_considered,
                )
            )
            continue
        if not item.estimate.assumptions:
            withheld.append(
                WithheldRecommendation(
                    node_event_ids=item.cut_set.member_event_ids,
                    node_event_types=types,
                    reason=WithholdingReason.NO_ASSUMPTIONS_ENUMERATED,
                    checked_against="counterfactual_engine.assess",
                    detail=(
                        "module 13 enumerated no assumption behind this figure. Principle 5 "
                        "requires the assumptions to be shown, and there are none to show."
                    ),
                    belief_scalar=confidence.scalar,
                    expected_benefit=item.estimate.benefit,
                    implementation_cost=cost,
                    operational_risk=risk,
                    sources=_sources_of(item.members),
                    chains_broken=item.cut_set.chains_broken,
                    chains_considered=item.cut_set.chains_considered,
                )
            )
            continue
        if floor is not None and confidence.scalar < floor:
            withheld.append(
                WithheldRecommendation(
                    node_event_ids=item.cut_set.member_event_ids,
                    node_event_types=types,
                    reason=WithholdingReason.BELOW_CONFIDENCE_FLOOR,
                    checked_against=(f"rule pack recommendation.minimum_belief_to_publish={floor}"),
                    detail=(
                        f"composed belief {confidence.scalar} under "
                        f"{confidence.aggregation}, below the declared floor of {floor}. "
                        "The floor is a gate rather than a term: publishing this low down a "
                        "ranked list would still read as an instruction to act."
                    ),
                    belief_scalar=confidence.scalar,
                    expected_benefit=item.estimate.benefit,
                    implementation_cost=cost,
                    operational_risk=risk,
                    sources=_sources_of(item.members),
                    chains_broken=item.cut_set.chains_broken,
                    chains_considered=item.cut_set.chains_considered,
                )
            )
            continue
        desirability, scalarizer = desirability_of(
            item.estimate, cost, risk, confidence, ceiling, context
        )
        if desirability is None and scalarizer is None:
            withheld.append(
                WithheldRecommendation(
                    node_event_ids=item.cut_set.member_event_ids,
                    node_event_types=types,
                    reason=WithholdingReason.POLICY_NOT_DECLARED,
                    checked_against="rule pack recommendation.objective_weights",
                    detail=(
                        "the pack declares no objective weights, so nothing could be "
                        "ranked. A weighting chosen here would decide which act an operator "
                        "is shown first, invisibly (ADR-0049, ADR-0079)."
                    ),
                    belief_scalar=confidence.scalar,
                    expected_benefit=item.estimate.benefit,
                    implementation_cost=cost,
                    operational_risk=risk,
                    sources=_sources_of(item.members),
                    chains_broken=item.cut_set.chains_broken,
                    chains_considered=item.cut_set.chains_considered,
                )
            )
            continue
        admitted.append((item, cost, risk, confidence, desirability, scalarizer))

    front, unjudged = frontier_of(
        tuple(
            orient(item.estimate, cost, risk, confidence, context)
            for item, cost, risk, confidence, _, _ in admitted
        )
    )

    weights = tuple(
        sorted((weight.objective, weight.weight) for weight in context.parameters.objective_weights)
    )
    built: list[Recommendation] = []
    for position, (item, cost, risk, confidence, desirability, scalarizer) in enumerate(admitted):
        built.append(
            Recommendation(
                recommendation_id=(
                    f"rec:{context.run_id}:" + "+".join(item.cut_set.member_event_ids)
                ),
                run_id=context.run_id,
                standing=context.standing.value,
                node_event_ids=item.cut_set.member_event_ids,
                node_event_types=tuple(
                    sorted({candidate.event_type for candidate in item.members})
                ),
                is_set=len(item.cut_set.member_event_ids) > 1,
                is_set_because=item.cut_set.is_set_because,
                sources=tuple(
                    sorted(
                        {source for candidate in item.members for source in candidate.sources},
                        key=lambda source: source.value,
                    )
                ),
                description=_describe(item.members),
                expected_benefit=item.estimate.benefit,
                portfolio=item.portfolio,
                implementation_cost=cost,
                operational_risk=risk,
                confidence=confidence,
                affected_event_ids=item.estimate.affected_event_ids,
                affected_instance_count=item.estimate.affected_instance_count,
                affected_magnitude=item.estimate.attributed_consequence,
                affected_magnitude_unit=item.estimate.attributed_unit,
                affected_share=(
                    item.estimate.attributed_share
                    if item.estimate.attributed_consequence is not None
                    else None
                ),
                desirability=desirability,
                scalarization=scalarizer,
                objective_weights=weights,
                on_pareto_frontier=position in front,
                frontier_absent_because=(
                    "an objective was not measured, so no claim that nothing beats this act "
                    "can be made; the frontier excludes it rather than ranking it worst."
                    if position in unjudged
                    else None
                ),
                chains_broken=item.cut_set.chains_broken,
                chains_considered=item.cut_set.chains_considered,
                search_regime=item.cut_set.regime,
                not_minimal_because=item.cut_set.not_minimal_because,
                evidence_item_ids=_evidence_of(item.cut_set.member_event_ids, context),
                assumptions=item.estimate.assumptions,
                risks=_risks_of(item.estimate, context, item.cut_set),
                justification=_justify(item, cost, risk, confidence, desirability),
            )
        )

    built.sort(key=lambda entry: entry.sort_key())
    if limit is not None and len(built) > limit:
        for entry in built[limit:]:
            withheld.append(
                WithheldRecommendation(
                    node_event_ids=entry.node_event_ids,
                    node_event_types=entry.node_event_types,
                    reason=WithholdingReason.BEYOND_PUBLICATION_LIMIT,
                    checked_against=f"rule pack recommendation.maximum_recommendations={limit}",
                    detail=(
                        "ranked below the pack's publication limit. Withheld rather than "
                        "rejected: it satisfied every gate and there was no room for it."
                    ),
                    belief_scalar=entry.confidence.scalar,
                )
            )
        built = built[:limit]

    return RecommendationResult(
        recommendations=tuple(built),
        withheld=tuple(sorted(withheld, key=lambda entry: entry.sort_key())),
        discovery=found,
        cut_sets=cut_sets,
        policy_gaps=tuple(sorted(set(policy_gaps))),
    )


def _justify(
    item: _Scored,
    cost: CostAssessment,
    risk: RiskAssessment,
    belief: ConfidenceVector,
    desirability: float | None,
) -> str:
    """One line an operator can act on, naming every quantity behind the sequencing.

    prd.md §32 asks for it. It is assembled from figures already on the artifact rather than
    from a template with adjectives in it: a justification that says "high impact" where the
    fields say 3.5 DAYS has added a judgement the engine did not make.
    """
    benefit = item.estimate.benefit
    span = (
        f"{benefit.low} to {benefit.high} {benefit.unit}"
        if benefit.low is not None
        else "no measurable benefit"
    )
    return (
        f"Breaks {item.cut_set.chains_broken} of {item.cut_set.chains_considered} chain(s) "
        f"for a benefit between {span}, at declared cost "
        f"{cost.class_id or 'NOT_DECLARED'} and declared operational risk "
        f"{risk.class_id or 'NOT_DECLARED'}, with composed belief "
        f"{belief.scalar} and desirability {desirability}. "
        "Cost and risk are ASSUMED declarations, not measurements."
    )
