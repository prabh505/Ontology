"""`causalog.causal_engine.confidence_scorer` -- module 10, the scored causal graph (L6).

prd.md §49, in full: every recommendation carries Overall Confidence, Rule Support,
Historical Support, Temporal Support, Statistical Support, Graph Connectivity and Evidence
Count -- and "Confidence should never be represented by a single unexplained number." This
package is that paragraph, plus the two things it cannot express.

WHAT THIS PACKAGE PRODUCES
--------------------------
`CausalEdge` values -- the first and only place in the pipeline one is constructed -- in a
`CausalGraph`, each carrying a `ConfidenceVector` of **eight** named components, and each
paired with a `ComponentExplanation` per component saying in words and in arithmetic why
that component holds the value it holds. Beside them, a `ConfidenceReport` whose first
section is what is *not* calibrated.

It owns **the LAW-EVIDENCE gate**. Module 9 owns LAW-TIME and stops; this is where a
proposal first becomes a scored claim, and where `INFERRED` may first be assigned.

THE EIGHT COMPONENTS, AND WHY TWO ARE NOT IN prd.md §49
--------------------------------------------------------
Six are §49's. Two more arrive at `confidence_schema_version` 2.0.0 (ADR-0052) because
§49's list cannot express two requirements:

* `evidence_diversity` -- independent lines of reasoning count for more than one line
  repeated. `evidence_count` alone lets a generator that fires ten times over one pair look
  like corroboration from ten directions.
* `contradiction_freedom` -- counter-evidence must lower a score. Named for *freedom*
  rather than for *penalty* so that every component rises with support and the aggregation
  stays monotone; the inversion is stated wherever it is rendered.

TWO OF THE EIGHT ARE GATES, NOT ADDENDS
----------------------------------------
`temporal_support` and `contradiction_freedom` do not contribute to a sum other evidence can
outvote. They CAP the result (`core.aggregation.gated_weighted_mean_v1`). A claim that A
caused B without knowing A came first is not a weak causal claim; it is not a causal claim,
and no quantity of correlation may lift it past its ceiling.

WHAT THIS PACKAGE DOES NOT DO, STRUCTURALLY RATHER THAN BY CONVENTION
----------------------------------------------------------------------
* **It never emits a bare float.** `CausalEdge.confidence` is a `ConfidenceVector` and the
  type refuses an empty component set. A confidence returned without components is not
  possible here, it is a `LawViolationError`.
* **It never skips a component.** Every edge carries all eight. A component whose data is
  absent is emitted at zero, marked `missing`, and counted in the report -- absence costs
  score rather than abstaining, and the cost is visible. `ComponentScorer.score` has no
  `None` return, so a component cannot be dropped by accident.
* **It never scores a count without its denominator.** `base_rates.py` computes the
  instance-level contingency table, and the historical and statistical components read
  **lift** against a baseline rate. A pattern present in every instance has lift 1.0 and
  scores zero, however large its count.
* **It never calls a small sample a large one.** Both lift-reading components carry a
  declared shrinkage term; small samples are discounted, never rounded up.
* **It never shows "we did not measure enough" as "this is weakly supported."**
  `INSUFFICIENT_EVIDENCE` is a distinct outcome, gets no band, and is never promoted.
* **It never invents a band.** Thresholds and their plain-language wording are declared in
  the rule pack (ADR-0053). A pack that declares none gets no labels and the report says so.
* **It does not rank.** `CausalGraph.edges` is sequenced canonically, never by score.
  Ranking is module 11's, and a pre-sorted graph would make its job look already done.
* **It does not resolve confounding, and nothing at V1 can.** Module 9's flags feed
  `contradiction_freedom` as the weakest of four signals, and every rendering repeats that
  visibility is not resolution.

WHAT IT READS
-------------
`tuple[CandidateEdge, ...]` from module 9, plus `GraphFacts`, `Timeline` values, the rule
evaluation, and the rule pack's `confidence_scoring` block. `GraphFacts` stands in for
`TemporalPropertyGraph` for the reason it does in module 9: module 8 does not exist. The
visible consequence is that `graph_connectivity` is MISSING on every edge today, which this
module publishes rather than papers over.
"""

from causalog.causal_engine.confidence_scorer.bands import (
    BAND_ABSENT_NOTICE,
    INSUFFICIENT_EVIDENCE_NOTICE,
    ScoringOutcome,
    band_for,
)
from causalog.causal_engine.confidence_scorer.base_rates import ContingencyTable, PairBaseRates
from causalog.causal_engine.confidence_scorer.context import (
    ComponentScorer,
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.fuse import PayloadDivergence, fuse_candidates
from causalog.causal_engine.confidence_scorer.graph import CausalGraph, ScoredEdge
from causalog.causal_engine.confidence_scorer.report import (
    CONFIDENCE_REPORT_SCHEMA_VERSION,
    NOT_CALIBRATED_NOTICE,
    RENDERED_TOP_EDGES,
    ComponentTally,
    ConfidenceReport,
    DerivedPrecedenceAudit,
    ScalarDistribution,
    render_markdown,
)
from causalog.causal_engine.confidence_scorer.score import (
    CONFIDENCE_AGGREGATOR,
    SCORER_COUNT,
    ScoringResult,
    score_candidates,
)
from causalog.causal_engine.confidence_scorer.scorers import (
    CONTRADICTION_WEIGHTS,
    MAX_CONNECTIVITY_HOPS,
    MEASURE_USED,
    ContradictionFreedomScorer,
    EvidenceCountScorer,
    EvidenceDiversityScorer,
    GraphConnectivityScorer,
    HistoricalSupportScorer,
    RuleSupportScorer,
    StatisticalSupportScorer,
    TemporalSupportScorer,
)

__all__ = [
    "BAND_ABSENT_NOTICE",
    "CONFIDENCE_AGGREGATOR",
    "CONFIDENCE_REPORT_SCHEMA_VERSION",
    "CONTRADICTION_WEIGHTS",
    "INSUFFICIENT_EVIDENCE_NOTICE",
    "MAX_CONNECTIVITY_HOPS",
    "MEASURE_USED",
    "NOT_CALIBRATED_NOTICE",
    "RENDERED_TOP_EDGES",
    "SCORER_COUNT",
    "CausalGraph",
    "ComponentExplanation",
    "ComponentScorer",
    "ComponentTally",
    "ConfidenceReport",
    "ContingencyTable",
    "ContradictionFreedomScorer",
    "DerivedPrecedenceAudit",
    "EvidenceCountScorer",
    "EvidenceDiversityScorer",
    "FusedClaim",
    "GraphConnectivityScorer",
    "HistoricalSupportScorer",
    "PairBaseRates",
    "PayloadDivergence",
    "RuleSupportScorer",
    "ScalarDistribution",
    "ScoredComponent",
    "ScoredEdge",
    "ScoringContext",
    "ScoringOutcome",
    "ScoringResult",
    "StatisticalSupportScorer",
    "TemporalSupportScorer",
    "band_for",
    "fuse_candidates",
    "render_markdown",
    "score_candidates",
]
