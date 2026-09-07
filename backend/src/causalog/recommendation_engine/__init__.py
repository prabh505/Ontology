"""Module 14 -- the Intervention Optimizer. Ranked acts over a graph, at L7.

prd.md §32 asks each causal chain to expose its intervention opportunities and §50 gives
each one seven quantities and a three-line ranking function. This package produces those,
and it is the first artifact in this system that is an INSTRUCTION rather than a
description: everything upstream says what happened or what might have; this says what to
do. An operator who follows it will be held accountable for having done so, and the
engineering follows from that one fact.

WHAT THIS MODULE STRUCTURALLY CANNOT DO
----------------------------------------
* **It cannot infer a cost.** `CostBasis` and `RiskBasis` are closed two-member enums with
  no `DERIVED` member, so an author who computes a cost has nowhere to record that they did.
  This package's README has carried the sentence "may never infer a cost" since the
  scaffold; `cost.py` is where it stopped being prose.
* **It cannot recommend an act nobody can take.** `candidate.admissible_target` is the only
  gate, is called from one place, and a law test asserts that over the AST. A refused node
  becomes a ledger entry naming the declaration that refused it, never a silent absence.
* **It cannot estimate a benefit.** Every figure is the return of
  `counterfactual_engine.simulate` (ADR-0074). A second estimator would be a second opinion
  about one question, and the two would agree on the day they were written and no day after.
  Asserted structurally and numerically, the second by a test that poses one hypothetical
  through both modules and requires one figure out.
* **It cannot add two benefits.** `sum` appears nowhere; the naive total exists only to be
  contrasted with the jointly simulated one, and even it is taken under a named operator in
  `core.attribution` (ADR-0077).
* **It cannot publish a recommendation without confidence, evidence and assumptions.** Not
  "filters them out" -- `Recommendation` carries `min_length=1` on both lists and a
  `ConfidenceVector` with no default, so such an object cannot be instantiated (ADR-0075,
  prd.md Principle 5).
* **It cannot state a causal claim.** It constructs no `CausalEdge` and assigns no
  `INFERRED`. `ProvenanceClass.SIMULATED` is pinned on every recommendation and a validator
  refuses anything else; `SIMULATED` is the weakest member of `WEAKEST_FIRST`, so
  containment is arithmetic rather than discipline.
* **It cannot choose the weights.** They are declared in the pack, they travel on every
  artifact, and `core.scalarization` does the arithmetic -- `CONVENTIONS.md` §6a would
  refuse it here anyway, and is right to.
* **It cannot walk a graph the engine does not stand behind, unless a caller says so at the
  call site.** OQ-026, ADR-0072 -- module 13's guard, in the same shape.

WHY A RANKED LIST NEEDS A FRONTIER BESIDE IT
----------------------------------------------
A scalarization is one traversal of a trade-off surface. Reweight it and the sequence
changes, and nothing on a ranked list tells a reader how fragile first place is. So
`on_pareto_frontier` is published per recommendation: a weight-independent claim that
nothing else beats this act on all four objectives at once. ADR-0008 refused a blended
root-cause score outright; this is the weaker case, because an operator genuinely must pick
one -- so the scalar is permitted, and only with the surface printed next to it.

THE ERROR THIS MODULE EXISTS TO NOT MAKE
-----------------------------------------
**An operator shown two recommendations worth eleven hours each will plan for twenty-two.**
If both acts lie on one chain the second saves what the first already saved. Every part of
the system upstream is correct and the operator is still wrong, because nothing told them
the two interact. `portfolio.py` simulates a set as a set and publishes the naive total
beside the true one so the overlap is visible rather than merely corrected.

EVERY BOUND IS DECLARED
------------------------
Weights, the confidence floor, the cut-set ceiling, the node cap, the set size cap and the
publication limit all come from the pack's `recommendation` block (ADR-0079). An absent
declaration means the policy **cannot run**, is reported as a policy gap naming what it
would have needed, and is never defaulted (ADR-0049, sixth application).
"""

from __future__ import annotations

from causalog.recommendation_engine.candidate import (
    Candidate,
    CandidateSource,
    Discovery,
    RefusalReason,
    RefusedCandidate,
    admissible_target,
    discover,
)
from causalog.recommendation_engine.context import (
    RecommendationContext,
    vocabulary_rank,
    vocabulary_span,
)
from causalog.recommendation_engine.cost import (
    CostAssessment,
    CostBasis,
    RiskAssessment,
    RiskBasis,
    assess_cost,
    assess_risk,
)
from causalog.recommendation_engine.cutset import (
    CutSet,
    SearchRegime,
    chains_of,
    find_cut_sets,
)
from causalog.recommendation_engine.estimate import (
    BenefitEstimate,
    BenefitRange,
    estimate,
    intervention_for,
)
from causalog.recommendation_engine.optimize import RecommendationResult, optimize
from causalog.recommendation_engine.portfolio import (
    NAIVE_OPERATOR,
    InteractionKind,
    PortfolioBenefit,
    interactions_within,
    portfolio_benefit,
)
from causalog.recommendation_engine.rank import (
    CONFIDENCE_COMPOSITION,
    confidence_of,
    desirability_of,
    estimate_stability,
    frontier_of,
    orient,
    weights_of,
)
from causalog.recommendation_engine.recommendation import (
    Recommendation,
    WithheldRecommendation,
    WithholdingReason,
)
from causalog.recommendation_engine.report import (
    ASSUMED_COST_NOTICE,
    RECOMMENDATION_REPORT_SCHEMA_VERSION,
    RecommendationReport,
    build_report,
    render_markdown,
)

__all__ = [
    "ASSUMED_COST_NOTICE",
    "CONFIDENCE_COMPOSITION",
    "NAIVE_OPERATOR",
    "RECOMMENDATION_REPORT_SCHEMA_VERSION",
    "BenefitEstimate",
    "BenefitRange",
    "Candidate",
    "CandidateSource",
    "CostAssessment",
    "CostBasis",
    "CutSet",
    "Discovery",
    "InteractionKind",
    "PortfolioBenefit",
    "Recommendation",
    "RecommendationContext",
    "RecommendationReport",
    "RecommendationResult",
    "RefusalReason",
    "RefusedCandidate",
    "RiskAssessment",
    "RiskBasis",
    "SearchRegime",
    "WithheldRecommendation",
    "WithholdingReason",
    "admissible_target",
    "assess_cost",
    "assess_risk",
    "build_report",
    "chains_of",
    "confidence_of",
    "desirability_of",
    "discover",
    "estimate",
    "estimate_stability",
    "find_cut_sets",
    "frontier_of",
    "interactions_within",
    "intervention_for",
    "optimize",
    "orient",
    "portfolio_benefit",
    "render_markdown",
    "vocabulary_rank",
    "vocabulary_span",
    "weights_of",
]
