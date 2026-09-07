"""The Causal Graph Builder -- scored claims become the engine's stated causal view (L6).

**Not one of the sixteen §36 modules.** prd.md §36 names no module that owns §25 (the causal
graph), §26 (the edge taxonomy) or §31 (feedback loops): module 9 proposes candidates, module
10 scores them, and modules 11 and 12 both consume a graph they assume already exists. This
package is that assembly step, landed the way the ontology layer and the rule engine landed
(ADR-0054). OQ-025 records the PRD gap and proposes amending §36 rather than renumbering it.

Single responsibility
---------------------
Decide which scored claims the engine will assert, type them, weight them, look for
feedback loops, and publish a report of what the resulting graph does **not** contain.

It does **not** rank. Sequencing is canonical, never by score; ranking is module 11's.
It does **not** score. Every number it reads about a claim's strength came from module 10.
It does **not** propose. A pair nobody proposed is absent, and the report says so.

Owns the promotion decision, and nothing else may make it
---------------------------------------------------------
`ProvenanceClass.INFERRED` is assigned in `policy.py` and nowhere else in `causal_engine`
(ADR-0054), asserted by `tests/law/test_law_time_gates_every_promotion.py`. LAW-TIME is
re-verified there twice over: explicitly against the two `Event` intervals, which a stored
`CausalEdge` cannot do for itself (DEF-0002), and structurally through
`core.immutability.revise`, which re-runs the frozen type's own
`INFERRED ⇒ CERTAIN ∧ ¬unverifiable` invariant.

Forbidden dependencies
----------------------
* `ontology_runtime` (forbidden edge F3) — the pack arrives as `core.ontology_view` values.
* `causalog.persistence` (F4) — every fact arrives by value through `GraphFacts`.
* any tabular library (F7) — nothing below module 4 sees a row.
* any higher layer (F2) — `counterfactual_engine`, `recommendation_engine`, `api`.
* domain vocabulary (LAW-DOMAIN) — every type, kind and identifier is a string from a pack.

Configuration
-------------
Every threshold is a declaration in the rule pack's `graph_construction` namespace
(ADR-0055), and an absent declaration means the policy CANNOT RUN and is reported as such --
never defaulted, never reported as a clean zero.
"""

from causalog.causal_engine.causal_graph_builder.build import (
    GraphBuildResult,
    build_causal_graph,
)
from causalog.causal_engine.causal_graph_builder.classify import (
    RULE_KIND_TO_EDGE_KIND,
    group_joint_causes,
    type_edge,
)
from causalog.causal_engine.causal_graph_builder.context import GraphBuildContext
from causalog.causal_engine.causal_graph_builder.cycles import (
    GAIN_CEILING_NOTICE,
    CircuitTruncation,
    DetectionStatus,
    FeedbackLoop,
    LoopClassification,
    LoopDetectionResult,
    LoopMember,
    detect_loops,
)
from causalog.causal_engine.causal_graph_builder.graph import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE,
    DemotionReason,
    DemotionRecord,
    EdgeLineage,
    JointCauseGroup,
    PromotedEdge,
    PromotedGraph,
    PropagationWeight,
    TypingBasis,
    TypingRecord,
    WeightBasis,
)
from causalog.causal_engine.causal_graph_builder.policy import PromotionVerdict, decide, promote
from causalog.causal_engine.causal_graph_builder.report import (
    GRAPH_QUALITY_SCHEMA_VERSION,
    STATED_VIEW_NOTICE,
    ContradictionFinding,
    GraphQualityReport,
    OrphanEffect,
    PolicyGap,
    render_markdown,
)
from causalog.causal_engine.causal_graph_builder.select import select
from causalog.causal_engine.causal_graph_builder.weights import (
    CONTRIBUTING_KINDS,
    MODIFIER_KINDS,
    weights_for_effect,
)

__all__ = [
    "ATTRIBUTION_NOT_MEASUREMENT_NOTICE",
    "CONTRIBUTING_KINDS",
    "GAIN_CEILING_NOTICE",
    "GRAPH_QUALITY_SCHEMA_VERSION",
    "MODIFIER_KINDS",
    "RULE_KIND_TO_EDGE_KIND",
    "STATED_VIEW_NOTICE",
    "CircuitTruncation",
    "ContradictionFinding",
    "DemotionReason",
    "DemotionRecord",
    "DetectionStatus",
    "EdgeLineage",
    "FeedbackLoop",
    "GraphBuildContext",
    "GraphBuildResult",
    "GraphQualityReport",
    "JointCauseGroup",
    "LoopClassification",
    "LoopDetectionResult",
    "LoopMember",
    "OrphanEffect",
    "PolicyGap",
    "PromotedEdge",
    "PromotedGraph",
    "PromotionVerdict",
    "PropagationWeight",
    "TypingBasis",
    "TypingRecord",
    "WeightBasis",
    "build_causal_graph",
    "decide",
    "detect_loops",
    "group_joint_causes",
    "promote",
    "render_markdown",
    "select",
    "type_edge",
    "weights_for_effect",
]
