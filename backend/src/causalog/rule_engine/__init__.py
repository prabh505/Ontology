"""`causalog.rule_engine` -- load, conflict-check, and evaluate rule packs (L5).

Rule **data** lives in `/rule_engine/<domain>/`. This package holds code only, and it is
**not** exempt from the LAW-DOMAIN lint (`CONVENTIONS.md` §6): nothing here may name the
thing it reasons about. Every type, role, state and attribute a rule mentions arrives as a
string from the pack and is checked against a `VocabularyView` (ADR-0046); nothing in this
package branches on the value of one.

The seam this implements is extension seam 4 of `docs/architecture.md` §5.1, and it is the
last `RunKey` input to be set -- `rule_pack_version` participates in `run_id` (ADR-0013), so
editing a rule creates a new Run.

What this package produces, and what it does not
------------------------------------------------
It produces `RuleFiring` values: a rule, its bindings, the events it matched, every
condition it evaluated with the value each one read, and the LAW-TIME verdict over the pair.
**A firing that cannot explain itself cannot be constructed** (ADR-0047).

It does **not** produce a `CausalEdge`. `docs/architecture.md` §Module 9 gives the Candidate
Cause Generator (L6) the LAW-TIME gate and edge construction, and the §6.2 sequence diagram
has this layer returning fired rule identifiers to it. It does not assign confidence either;
that is module 10.
"""

from causalog.rule_engine.conflict import ConflictFinding, ConflictReport
from causalog.rule_engine.coverage import (
    CoverageReport,
    EventTypeCoverage,
    measure_coverage,
    render_markdown,
)
from causalog.rule_engine.diagnostics import Diagnostic, Severity, render
from causalog.rule_engine.dsl import (
    RULE_PACK_SCHEMA_VERSION,
    CandidateGenerationSpec,
    CompetingEffectPolicy,
    ConditionExpression,
    ConditionOperator,
    ConfidenceBandSpec,
    ConfidenceScoringSpec,
    CounterfactualSimulationSpec,
    GraphConstructionSpec,
    ImpactAggregationSpec,
    KnowledgeProvenance,
    MagnitudeAttributionSpec,
    PatternMiningSpec,
    PromotionThresholdSpec,
    PropagationAnalysisSpec,
    ProximityWindowSpec,
    RootCauseAnalysisSpec,
    Rule,
    RuleKind,
    RulePackSpec,
    TemporalWindow,
    WeightNormalization,
)
from causalog.rule_engine.evaluate import EvaluationResult, EvaluationStatistics, evaluate
from causalog.rule_engine.facts import FactSet, GraphFacts
from causalog.rule_engine.loader import (
    LoadedRulePack,
    inspect_rule_pack,
    load_rule_pack,
    rule_pack_hash,
)
from causalog.rule_engine.trace import ConditionTraceEntry, RuleFiring, WindowObservation

__all__ = [
    "RULE_PACK_SCHEMA_VERSION",
    "CandidateGenerationSpec",
    "CompetingEffectPolicy",
    "ConditionExpression",
    "ConditionOperator",
    "ConditionTraceEntry",
    "ConfidenceBandSpec",
    "ConfidenceScoringSpec",
    "ConflictFinding",
    "ConflictReport",
    "CounterfactualSimulationSpec",
    "CoverageReport",
    "Diagnostic",
    "EvaluationResult",
    "EvaluationStatistics",
    "EventTypeCoverage",
    "FactSet",
    "GraphConstructionSpec",
    "GraphFacts",
    "ImpactAggregationSpec",
    "KnowledgeProvenance",
    "LoadedRulePack",
    "MagnitudeAttributionSpec",
    "PatternMiningSpec",
    "PromotionThresholdSpec",
    "PropagationAnalysisSpec",
    "ProximityWindowSpec",
    "RootCauseAnalysisSpec",
    "Rule",
    "RuleFiring",
    "RuleKind",
    "RulePackSpec",
    "Severity",
    "TemporalWindow",
    "WeightNormalization",
    "WindowObservation",
    "evaluate",
    "inspect_rule_pack",
    "load_rule_pack",
    "measure_coverage",
    "render",
    "render_markdown",
    "rule_pack_hash",
]
