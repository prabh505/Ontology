"""Measure how an effect spreads through the causal graph (module 12).

WHAT THIS MODULE MEASURES, AND WHAT IT REFUSES TO COMBINE

prd.md §30 says every downstream consequence should be measured and lists seven things
propagation includes: depth, breadth, duration, affected entities, economic impact,
operational impact, confidence. This module produces all seven and **combines none of them
into a headline**. A single propagation score would be a number that rises for seven
unrelated reasons; a reader could not tell a deep narrow chain from a shallow wide fan-out,
nor a large loss over one subject from a small one over many. Depth and breadth are two
fields. Duration and economic magnitude are separate rows keyed by the measurement that
produced them, because a share of elapsed time and a share of currency are both shares and
printing them under one heading would be one number meaning two things.

THE SET IS THE UNIT OF ATTRIBUTION, AND THAT IS THE WHOLE NO-DOUBLE-COUNTING GUARANTEE

A consequence reachable by four routes is one consequence. Magnitude is attributed to
NODES, never to paths, and `ConsequenceSet` is keyed by event identifier and validates its
own membership unique -- so the guarantee is held by a type rather than by care taken at a
call site. Routes are reported as structure (`route_count`) and multiply nothing. On a
diamond the shared consequence contributes once, which is asserted by
`tests/graph/test_impact_is_not_double_counted.py` against a hand-computed constant.

A CHAIN IS ONLY AS STRONG AS ITS WEAKEST LINK

Route confidence composes under a named function held in `causalog.core.composition`, and
the name travels with the data as `ConfidenceVector.aggregation` does one level down. The
default is the minimum, for four reasons stated in full in that module: it is the doctrine
`core.provenance.combine` and `aggregation.minimum_v1` already hold; a product would be
arithmetic with probability semantics these uncalibrated numbers do not have, reporting
chain LENGTH while appearing to report belief; the minimum is monotonically non-increasing
and idempotent along a path; and its cost -- it ties heavily -- is paid for by carrying the
product beside it in its own column and by reporting path length as a separate field rather
than folding it in.

TWO STANDINGS, NEVER BLENDED

The traversal walks a `GraphView`, which either graph satisfies. `STATED` is the promoted
graph and its findings are the engine's. `UNPROMOTED_DIAGNOSTIC` is module 10's scored graph
before promotion, and everything derived from it is disowned by the type that carries it,
refused `INFERRED` by a validator, and printed under a fixed notice held as a property so no
revision can soften it. It exists because on the committed bounded run the stated graph is
EMPTY -- 0 of 9,492 claims promoted, 79.3% stopped by the temporal verdict rather than by
any threshold -- and silence is a true answer that shows a reader nothing about whether the
machinery works. See `view.py`.

WHAT THIS MODULE STRUCTURALLY CANNOT DO

It creates no link: `CausalEdge` is never constructed here and `ProvenanceClass.INFERRED` is
never assigned here, which `tests/law/test_ranking_never_collapses.py` asserts over the AST.
It ranks nothing: the tree comes back sequenced by depth and identifier, canonically and
deliberately not by consequence, because ranking is module 11's. It recomputes no domain
metric: every magnitude is a walk of an ontology-declared operator tree through
`core.measurement`, and no formula appears anywhere in the package.

EVERY BOUND IS DECLARED

`maximum_depth`, `traversal_node_cap`, the combination operator per measurement and the
composition function are all read from the pack's `propagation_analysis` block. An absent
declaration means the policy CANNOT RUN, is reported as a `PolicyGap` with what it would
have needed, and is never defaulted (ADR-0049). A pack that declares no depth gets no
traversal and a report that says so -- not a propagation of zero.
"""

from causalog.causal_engine.propagation_analyzer.analyze import (
    PropagationResult,
    analyze_propagation,
)
from causalog.causal_engine.propagation_analyzer.attribute import consequence_set, share_for
from causalog.causal_engine.propagation_analyzer.context import (
    CACHE_TTL_SECONDS,
    PropagationContext,
)
from causalog.causal_engine.propagation_analyzer.counterfactual import (
    PreventedConsequence,
    prevented_by_removing,
    share_of_whole,
)
from causalog.causal_engine.propagation_analyzer.graph import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE,
    MAX_PROPAGATION_DEPTH,
    ConsequenceSet,
    MagnitudeShare,
    PathConfidence,
    PropagationNode,
    PropagationTree,
    TruncationReason,
    TruncationRecord,
)
from causalog.causal_engine.propagation_analyzer.report import (
    PROPAGATION_REPORT_SCHEMA_VERSION,
    PolicyGap,
    PropagationReport,
    build_report,
    render_markdown,
)
from causalog.causal_engine.propagation_analyzer.traverse import (
    DEPTH_NOT_DECLARED,
    effective_depth_bound,
    links_along_route,
    reachable_from,
    walk,
)
from causalog.causal_engine.propagation_analyzer.view import (
    DIAGNOSTIC_NOT_STATED_NOTICE,
    GraphLink,
    GraphStanding,
    GraphView,
    diagnostic_view,
    stated_view,
)

__all__ = [
    "ATTRIBUTION_NOT_MEASUREMENT_NOTICE",
    "CACHE_TTL_SECONDS",
    "DEPTH_NOT_DECLARED",
    "DIAGNOSTIC_NOT_STATED_NOTICE",
    "MAX_PROPAGATION_DEPTH",
    "PROPAGATION_REPORT_SCHEMA_VERSION",
    "ConsequenceSet",
    "GraphLink",
    "GraphStanding",
    "GraphView",
    "MagnitudeShare",
    "PathConfidence",
    "PolicyGap",
    "PreventedConsequence",
    "PropagationContext",
    "PropagationNode",
    "PropagationReport",
    "PropagationResult",
    "PropagationTree",
    "TruncationReason",
    "TruncationRecord",
    "analyze_propagation",
    "build_report",
    "consequence_set",
    "diagnostic_view",
    "effective_depth_bound",
    "links_along_route",
    "prevented_by_removing",
    "reachable_from",
    "render_markdown",
    "share_for",
    "share_of_whole",
    "stated_view",
    "walk",
]
