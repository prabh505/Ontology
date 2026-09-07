"""The module's one entry point: a scored graph in, the stated causal view out.

Assembles selection, typing, weighting and loop detection into one deterministic pass, and
gathers the policy gaps the report needs. Holds no policy of its own -- every threshold it
acts on came from the pack, and every classification it reports was decided in the module
that owns it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.causal_graph_builder.context import GraphBuildContext
from causalog.causal_engine.causal_graph_builder.cycles import (
    DetectionStatus,
    LoopDetectionResult,
    detect_loops,
)
from causalog.causal_engine.causal_graph_builder.graph import PromotedGraph
from causalog.causal_engine.causal_graph_builder.report import (
    GraphQualityReport,
    PolicyGap,
    build_report,
)
from causalog.causal_engine.causal_graph_builder.select import select
from causalog.causal_engine.confidence_scorer import CausalGraph
from causalog.core.run import OutputEnvelope
from causalog.core.types.causal_edge import CausalEdgeKind

__all__ = ["GraphBuildResult", "build_causal_graph"]


class GraphBuildResult(BaseModel):
    """The module's whole output: the stated view, the loops, and the report over both."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    graph: PromotedGraph
    loops: LoopDetectionResult
    report: GraphQualityReport


def _policy_gaps(context: GraphBuildContext, loops: LoopDetectionResult) -> tuple[PolicyGap, ...]:
    """Collect every declaration the pack did not make, with what its absence cost.

    Assembled here rather than raised at each site, so the report carries one list a pack
    author can work through instead of a finding buried per edge.
    """
    parameters = context.parameters
    gaps: list[PolicyGap] = []
    undeclared = sorted(
        kind.value for kind in CausalEdgeKind if parameters.threshold_for(kind.value) is None
    )
    if undeclared:
        gaps.append(
            PolicyGap(
                policy="graph_construction.promotion_thresholds",
                requirement=(
                    "one entry per edge kind the pack is willing to assert; missing for "
                    + ", ".join(f"`{kind}`" for kind in undeclared)
                ),
                consequence=(
                    "no claim of those kinds may be promoted, however it scored. Every such "
                    "claim is in the ledger under `NO_THRESHOLD_DECLARED`, which is a "
                    "statement about the pack and never about the claim."
                ),
            )
        )
    if parameters.competing_effect_policy is None:
        gaps.append(
            PolicyGap(
                policy="graph_construction.competing_effect_policy",
                requirement="one of RETAIN_ALL, RETAIN_ABOVE_THRESHOLD, RETAIN_TOP_N",
                consequence=(
                    "every claim clearing its threshold is retained. That is the same "
                    "behaviour RETAIN_ALL declares, and it is reached here by default "
                    "rather than by declaration -- which is the one place this module "
                    "falls back rather than refusing, because retaining everything hides "
                    "nothing."
                ),
            )
        )
    if parameters.weight_normalization is None:
        gaps.append(
            PolicyGap(
                policy="graph_construction.weight_normalization",
                requirement="SHARE_OF_INCOMING",
                consequence=(
                    "weights are still computed and every one carries `normalization: "
                    "null`, so a stored artifact says that the rule producing its number "
                    "was never declared."
                ),
            )
        )
    if not parameters.magnitude_attributions:
        gaps.append(
            PolicyGap(
                policy="graph_construction.magnitude_attributions",
                requirement="an effect event type mapped to a declared measurement id",
                consequence=(
                    "no effect has a nominated quantity, so every propagation weight is a "
                    "share of BELIEF rather than a share of a magnitude, and is reported "
                    "under the `CONFIDENCE_SHARE` basis."
                ),
            )
        )
    if parameters.diversity_credit_ceiling is None:
        gaps.append(
            PolicyGap(
                policy="graph_construction.diversity_credit_ceiling",
                requirement="a ceiling in [0, 1]",
                consequence=(
                    "no tie-break credit is given for a claim reached by several "
                    "independent generators. Nothing is lost: module 10 already scored that "
                    "multiplicity as `evidence_diversity`, and this credit only ever "
                    "reorders claims a competition policy has to choose between."
                ),
            )
        )
    if loops.status is DetectionStatus.NOT_RUNNABLE and loops.requirement:
        gaps.append(
            PolicyGap(
                policy="graph_construction (loop detection)",
                requirement=loops.requirement,
                consequence=(
                    "no circuit was enumerated. This is NOT a report of zero feedback "
                    "loops, and the report says so where the loop counts would otherwise "
                    "appear."
                ),
            )
        )
    return tuple(gaps)


def build_causal_graph(
    scored: CausalGraph, context: GraphBuildContext, envelope: OutputEnvelope
) -> GraphBuildResult:
    """Turn module 10's scored claims into the engine's stated causal view.

    Deterministic: two calls over one input produce byte-identical artifacts, including the
    rendered report. Every grouping is sorted and no dictionary is read in insertion
    sequence (`CONVENTIONS.md` §11).
    """
    graph = select(scored, context)
    loops = detect_loops(scored, graph, context)
    events_by_id = context.events_by_id()

    events_by_type: dict[str, int] = {}
    for event in events_by_id.values():
        events_by_type[event.event_type] = events_by_type.get(event.event_type, 0) + 1

    considered: dict[str, int] = {}
    for edge in scored.edges:
        kind = edge.edge.payload.edge_kind.value
        considered[kind] = considered.get(kind, 0) + 1

    rejected_by_type: dict[str, dict[str, int]] = {}
    for record in graph.demotions:
        target = events_by_id.get(record.target_event_id)
        if target is None:
            continue
        tally = rejected_by_type.setdefault(target.event_type, {})
        tally[record.reason.value] = tally.get(record.reason.value, 0) + 1

    explained = frozenset(
        events_by_id[edge.edge.target_event_id].event_type
        for edge in graph.edges
        if edge.edge.target_event_id in events_by_id
    )

    report = build_report(
        graph,
        loops,
        envelope,
        events_by_type=events_by_type,
        considered_by_kind=tuple(sorted(considered.items())),
        rejected_effect_types={
            event_type: tuple(sorted(tally.items()))
            for event_type, tally in sorted(rejected_by_type.items())
        },
        explained_effect_types=explained,
        policy_gaps=_policy_gaps(context, loops),
    )
    return GraphBuildResult(graph=graph, loops=loops, report=report)
