"""The eight component scorers, and the canonical set the orchestrator runs.

Six are prd.md §49's named components. Two more -- `evidence_diversity` and
`contradiction_freedom` -- arrive at `confidence_schema_version` 2.0.0 (ADR-0052), because
§49's list cannot express two things the brief requires: that independent evidence counts
for more than repeated evidence, and that counter-evidence lowers a score.

Each scorer is independently testable by construction: it reads a `ScoringContext` and a
`FusedClaim`, holds no reference to any other scorer, and returns exactly one component.
`ALL_SCORERS` is assembled by `score.py` rather than being a module constant, because
`EvidenceDiversityScorer` needs the run's reachable spread and a constant could not carry it.
"""

from causalog.causal_engine.confidence_scorer.scorers.contradiction_freedom import (
    CONTRADICTION_WEIGHTS,
    ContradictionFreedomScorer,
)
from causalog.causal_engine.confidence_scorer.scorers.evidence_count import EvidenceCountScorer
from causalog.causal_engine.confidence_scorer.scorers.evidence_diversity import (
    EvidenceDiversityScorer,
)
from causalog.causal_engine.confidence_scorer.scorers.graph_connectivity import (
    MAX_CONNECTIVITY_HOPS,
    GraphConnectivityScorer,
)
from causalog.causal_engine.confidence_scorer.scorers.historical_support import (
    HistoricalSupportScorer,
)
from causalog.causal_engine.confidence_scorer.scorers.rule_support import RuleSupportScorer
from causalog.causal_engine.confidence_scorer.scorers.statistical_support import (
    MEASURE_USED,
    StatisticalSupportScorer,
)
from causalog.causal_engine.confidence_scorer.scorers.temporal_support import (
    TemporalSupportScorer,
)

__all__ = [
    "CONTRADICTION_WEIGHTS",
    "MAX_CONNECTIVITY_HOPS",
    "MEASURE_USED",
    "ContradictionFreedomScorer",
    "EvidenceCountScorer",
    "EvidenceDiversityScorer",
    "GraphConnectivityScorer",
    "HistoricalSupportScorer",
    "RuleSupportScorer",
    "StatisticalSupportScorer",
    "TemporalSupportScorer",
]
