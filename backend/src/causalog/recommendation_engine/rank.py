"""Sequencing four objectives that do not agree, and saying so beside the sequence.

prd.md §50's ranking function is three lines: highest benefit, lowest cost, highest
belief. That is a preference SEQUENCE, not a procedure: it says nothing about the only
interesting case, where one act is better on benefit and worse on cost. Making it a
procedure needs weights, weights are a judgement, and this file holds none of them -- they
come from the pack, they travel on every artifact, and `core.scalarization` does the
arithmetic.

WHY A FRONTIER IS PUBLISHED BESIDE THE SEQUENCE (ADR-0078)
-----------------------------------------------------------
A scalarization is one traversal of a trade-off surface. Reweight it and the sequence
changes, and nothing on a ranked list tells a reader how fragile their first place is. The
Pareto frontier is weight-independent: a candidate on it is one that nothing else beats on
every objective at once, which is true under every weighting anybody could have chosen.

So `on_pareto_frontier` is a stronger claim than a high desirability, and it is reported as
a separate field rather than folded into the score. ADR-0008 refused a blended root-cause
score outright; a recommendation ranking is the weaker case -- an operator genuinely must
pick one -- so the scalar is permitted here, and only with the surface printed next to it.

THE CONFIDENCE OF A RECOMMENDATION
------------------------------------
Composed under `minimum_v1`: **a recommendation is only as believable as its weakest
component** (ADR-0060, one layer up). The alternative, a weighted mean, lets a strong belief
in the chain compensate for a figure that sits outside anything the run witnessed, and those
two are not the kind of thing that should compensate for each other.

Three components, and graph standing is deliberately NOT among them. Standing is a field on
every artifact this engine produces and a disowning notice on every page; folding it into
the confidence as well would count one fact twice, and would make the diagnostic machinery
unexercisable by scoring every diagnostic candidate at zero.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.scalarization import (
    DEFAULT_SCALARIZER,
    inverted_rank,
    pareto_front_v1,
    scalarize,
)
from causalog.core.types import ConfidenceVector
from causalog.core.types.confidence import ConfidenceComponent
from causalog.counterfactual_engine import ValidityVerdict
from causalog.recommendation_engine.context import RecommendationContext
from causalog.recommendation_engine.cost import CostAssessment, RiskAssessment
from causalog.recommendation_engine.estimate import BenefitEstimate

__all__ = [
    "CONFIDENCE_COMPOSITION",
    "confidence_of",
    "desirability_of",
    "estimate_stability",
    "frontier_of",
    "orient",
    "weights_of",
]

#: Named on every artifact. `minimum_v1` is name-agnostic in `core.aggregation`, which is
#: what lets this module use component names of its own rather than module 10's six.
CONFIDENCE_COMPOSITION = "minimum_v1"

#: What each validity verdict is worth as a support component. `EXTRAPOLATION` scores zero
#: only for completeness: it does not score low, it REPLACES the figure (ADR-0070), so a
#: candidate carrying it has no benefit and is withheld before it is ever scored.
_SUPPORT_VALUE = {
    ValidityVerdict.WITHIN_SUPPORT: 1.0,
    ValidityVerdict.AT_EDGE_OF_SUPPORT: 0.5,
    ValidityVerdict.NOT_ASSESSABLE: 0.0,
    ValidityVerdict.EXTRAPOLATION: 0.0,
}


def weights_of(context: RecommendationContext) -> dict[str, float] | None:
    """Return the pack's declared objective weights, or `None` if it declares none.

    `None` is a refusal. Nothing is defaulted: a weighting chosen here would decide which
    act an operator is shown first, and would do it invisibly (ADR-0049, ADR-0079).
    """
    declared = context.parameters.objective_weights
    if not declared:
        return None
    return {weight.objective: weight.weight for weight in declared}


def confidence_of(
    estimate: BenefitEstimate, evidence_record_ids: tuple[str, ...]
) -> ConfidenceVector:
    """Compose a recommendation's belief from named, inspectable components.

    LAW-EVIDENCE: a bare float is a defect. Every component below names what it measures and
    carries the evidence records behind it, and the scalar is the MINIMUM of them -- see this
    module's docstring for why a mean was refused.

    A component whose input is absent scores 0.0 and is reported, never dropped. Dropping it
    would renormalize the missing evidence away and rank a candidate nobody could assess
    above one that was assessed and found weak -- module 10's `graph_connectivity` ruling.

    THE ONE EXCEPTION, AND WHY IT IS NOT THAT RULE
    ------------------------------------------------
    `support_envelope` is omitted -- not scored zero -- when module 13 built NO envelope at
    all. A support envelope asks whether a changed VALUE lies inside the range this run
    witnessed, and a removal changes no value: there is nothing to place. So module 13
    attempts no envelope and returns `NOT_ASSESSABLE`, and that verdict means "the question
    does not apply to this kind of change", not "this change is unsupported".

    Charging a candidate for the absence of a check that cannot exist would charge it for
    the KIND of act proposed rather than for the strength of its evidence, and under
    `minimum_v1` it would score every removal at zero permanently -- which would make module
    14 structurally incapable of ever recommending anything, while looking like a finding
    about the data. An envelope that WAS built and came back `NOT_ASSESSABLE` is the other
    thing entirely, and scores zero exactly as module 10's ruling requires.

    The distinction is drawn on `support_envelope_count`, which is why that field exists.
    """
    components: list[ConfidenceComponent] = [
        ConfidenceComponent(
            component_name="simulated_chain_belief",
            value=estimate.composed_belief if estimate.composed_belief is not None else 0.0,
            provenance_class=ProvenanceClass.SIMULATED,
            evidence_record_ids=evidence_record_ids,
        ),
        ConfidenceComponent(
            component_name="sensitivity_stability",
            # The sweep is what tests whether the answer survives an assumption the data
            # cannot adjudicate. An answer that inverts under one perturbation is not a
            # slightly weaker answer; it is an answer whose sign the inputs do not fix.
            value=estimate_stability(estimate),
            provenance_class=ProvenanceClass.SIMULATED,
            evidence_record_ids=evidence_record_ids,
        ),
    ]
    if estimate.support_envelope_count > 0:
        components.append(
            ConfidenceComponent(
                component_name="support_envelope",
                value=_SUPPORT_VALUE[estimate.verdict],
                provenance_class=ProvenanceClass.SIMULATED,
                evidence_record_ids=evidence_record_ids,
            )
        )
    scalar = min(component.value for component in components)
    return ConfidenceVector(
        components=tuple(sorted(components, key=lambda item: item.component_name)),
        scalar=scalar,
        aggregation=CONFIDENCE_COMPOSITION,
        provenance_class=combine(*(item.provenance_class for item in components)),
    )


def estimate_stability(estimate: BenefitEstimate) -> float:
    """Return 1.0 when the swept answer held its sign, 0.0 when a perturbation inverted it.

    An answer that inverts under one perturbation is not a slightly weaker answer; it is an
    answer whose sign the inputs do not fix. Module 13 reports that per finding and this
    reads it -- a range that reached this function always has a sweep behind it, because
    `estimate._range_from` refuses to build one without perturbations.
    """
    if estimate.benefit.absent_because is not None:
        return 0.0
    low, high = estimate.benefit.low, estimate.benefit.high
    if low is None or high is None:
        return 0.0
    return 0.0 if (low < 0.0) != (high < 0.0) else 1.0


def desirability_of(
    estimate: BenefitEstimate,
    cost: CostAssessment,
    risk: RiskAssessment,
    confidence: ConfidenceVector,
    benefit_ceiling: float | None,
    context: RecommendationContext,
) -> tuple[float | None, str | None]:
    """Return the scalarized desirability and the name of the function that produced it.

    `(None, None)` when the pack declares no weighting -- a run that cannot rank says so
    rather than ranking under weights nobody chose.
    """
    weights = weights_of(context)
    scalarizer = context.parameters.scalarization or DEFAULT_SCALARIZER
    if weights is None:
        return (None, None)
    return (
        scalarize(
            benefit=estimate.benefit.high,
            benefit_ceiling=benefit_ceiling,
            cost_rank=cost.rank,
            cost_span=max(1, cost.span),
            risk_rank=risk.rank,
            risk_span=max(1, risk.span),
            belief_scalar=confidence.scalar,
            weights=weights,
            scalarizer_name=scalarizer,
        ),
        scalarizer,
    )


def frontier_of(
    points: tuple[tuple[float | None, float | None, float | None, float | None], ...],
) -> tuple[frozenset[int], frozenset[int]]:
    """Return the non-dominated indices and the indices the frontier could not judge.

    Coordinates arrive ALREADY oriented so that higher is better, which is this module's
    job and not `core.scalarization`'s: cost and risk are inverted here, once, where the
    inversion is visible beside the objective names it applies to.
    """
    front, excluded = pareto_front_v1([list(point) for point in points])
    return (frozenset(front), frozenset(excluded))


def orient(
    estimate: BenefitEstimate,
    cost: CostAssessment,
    risk: RiskAssessment,
    confidence: ConfidenceVector,
    context: RecommendationContext,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Return one candidate's four objectives with every axis pointing the same way.

    Benefit and belief are already better-high. Cost and risk are better-LOW, and
    `core.scalarization.inverted_rank` re-points them -- there rather than here, because
    `CONVENTIONS.md` §6a refuses arithmetic over a cost-named value in this package, and is
    right to: an inversion written inline is a formula that does not move when the ontology
    does.

    An undeclared cost or risk yields `None`, which excludes the point from the frontier
    rather than scoring it worst. `pareto_front_v1` states why the frontier treats absence
    differently from the way the scalarizer does: membership is a CLAIM.
    """
    del context  # spans travel on the assessments; retained for signature stability
    return (
        estimate.benefit.high,
        inverted_rank(cost.rank, cost.span),
        confidence.scalar,
        inverted_rank(risk.rank, risk.span),
    )
