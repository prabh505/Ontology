"""Selection: which scored claims become the stated view, and the ledger of the rest.

Three things happen here and they are kept apart on purpose.

**Lineage** is assembled from module 9's candidates, regrouped by exactly the key module 10
fused them on -- `(source, target, kind)`. This RECORDS provenance and re-derives no
judgement. It matters that the distinction is explicit, because the temptation in a
selection module is to look at four generators agreeing and treat that as extra support.
Module 10 has already done that: it fused the parallel candidates, deduplicated their
evidence by content-addressed `evidence_item_id`, and turned the multiplicity into the
`evidence_diversity` and `evidence_count` components of the vector. Counting it again would
be counting one fact twice.

**Diversity credit** is therefore a tie-break and nothing else. It is capped by a pack
declaration (`diversity_credit_ceiling`), it applies only when the pack's competing-effect
policy actually has to choose between claims, and it can only reorder claims that sit within
the ceiling of each other. It never moves a confidence scalar, never reaches an artifact,
and a pack that declares no ceiling gets no tie-break at all.

**Competition** is per effect, under the pack's declared policy. Losers become
`DemotionRecord`s with `LOST_COMPETITION`; nothing is dropped. `PromotedGraph` checks that
promoted plus demoted equals considered, so a claim that went missing raises at construction.

Joint groups are resolved last, because a group's fate depends on every member's individual
standing and on the competition outcome. Promotion is all-or-nothing: the moment one member
fails, every member is demoted with `JOINT_GROUP_INCOMPLETE`.
"""

from __future__ import annotations

from causalog.causal_engine.causal_graph_builder.classify import group_joint_causes, type_edge
from causalog.causal_engine.causal_graph_builder.context import GraphBuildContext
from causalog.causal_engine.causal_graph_builder.graph import (
    DemotionReason,
    DemotionRecord,
    EdgeLineage,
    JointCauseGroup,
    PromotedEdge,
    PromotedGraph,
    PropagationWeight,
    TypingRecord,
)
from causalog.causal_engine.causal_graph_builder.policy import decide, promote
from causalog.causal_engine.causal_graph_builder.weights import weights_for_effect
from causalog.causal_engine.confidence_scorer import CausalGraph, ScoredEdge
from causalog.core.types import CandidateEdge
from causalog.core.types.causal_edge import ContributingCause
from causalog.rule_engine import CompetingEffectPolicy

__all__ = ["EdgeKey", "select"]

#: `(source_event_id, target_event_id, edge_kind)` -- the key module 10 fuses on and the key
#: everything in this module is grouped and sequenced by.
EdgeKey = tuple[str, str, str]


def _lineage_index(candidates: tuple[CandidateEdge, ...]) -> dict[EdgeKey, list[CandidateEdge]]:
    """Group module 9's candidates by the key module 10 fused them on."""
    grouped: dict[EdgeKey, list[CandidateEdge]] = {}
    for candidate in candidates:
        key = (
            candidate.source_event_id,
            candidate.target_event_id,
            candidate.payload.edge_kind.value,
        )
        grouped.setdefault(key, []).append(candidate)
    return grouped


def _lineage_for(scored: ScoredEdge, index: dict[EdgeKey, list[CandidateEdge]]) -> EdgeLineage:
    """Return the lineage of one scored claim.

    When no candidate is indexed for the key -- a caller scoring edges it did not generate,
    which the tests do -- the lineage falls back to the edge's own evidence and a single
    synthetic generator name. It is never empty: an artifact with no lineage cannot answer
    the question the ledger exists to answer.
    """
    candidates = index.get(
        (
            scored.edge.source_event_id,
            scored.edge.target_event_id,
            scored.edge.payload.edge_kind.value,
        ),
        [],
    )
    if candidates:
        candidate_ids = tuple(sorted({item.candidate_edge_id for item in candidates}))
        generator_ids = tuple(sorted({item.generator_id for item in candidates}))
    else:
        candidate_ids = (scored.edge.causal_edge_id,)
        generator_ids = ("unattributed",)
    return EdgeLineage(
        candidate_edge_ids=candidate_ids,
        generator_ids=generator_ids,
        evidence_item_ids=tuple(sorted({item.evidence_item_id for item in scored.edge.evidence})),
        confidence=scored.edge.confidence,
        band_name=scored.band_name,
        scored_component_count=scored.scored_component_count,
        outcome=scored.outcome.value,
    )


def _diversity_credit(lineage: EdgeLineage, ceiling: float | None, reach: int) -> float:
    """Return the tie-break credit for one claim, bounded by the pack's declared ceiling.

    Zero when the pack declares no ceiling, and zero when only one generator reached the
    claim. Scaled across the range of generator counts this run actually produced, so the
    credit is relative to what was reachable rather than to an absolute number of generators
    that would change meaning when a generator is added.

    **This is not support.** It cannot exceed `ceiling`, so it can only reorder claims that
    already sit within `ceiling` of each other, and it is applied to a ranking key that is
    discarded once the ranking is made. No artifact carries it.
    """
    if ceiling is None or reach <= 1:
        return 0.0
    span = max(1, reach - 1)
    return ceiling * min(1.0, (len(lineage.generator_ids) - 1) / span)


def _competition_key(
    scored: ScoredEdge, lineage: EdgeLineage, ceiling: float | None, reach: int
) -> tuple[float, str, str, str]:
    """Return the ranking key used only when the policy must choose between claims.

    Best first: strongest adjusted scalar, then the canonical sort key so that two claims
    the arithmetic cannot separate are separated by something stable rather than by
    iteration sequence (`CONVENTIONS.md` §11).
    """
    adjusted = scored.edge.confidence.scalar + _diversity_credit(lineage, ceiling, reach)
    return (
        -adjusted,
        scored.edge.source_event_id,
        scored.edge.target_event_id,
        scored.edge.payload.edge_kind.value,
    )


def _demotion(
    scored: ScoredEdge, reason: DemotionReason, detail: str, lineage: EdgeLineage
) -> DemotionRecord:
    """Return one ledger entry."""
    return DemotionRecord(
        source_event_id=scored.edge.source_event_id,
        target_event_id=scored.edge.target_event_id,
        edge_kind=scored.edge.payload.edge_kind.value,
        reason=reason,
        detail=detail,
        lineage=lineage,
    )


def select(graph: CausalGraph, context: GraphBuildContext) -> PromotedGraph:
    """Build the stated causal view over one scored graph, with its rejection ledger.

    Deterministic end to end: every grouping is sorted, the competition key ends in the
    canonical sort key, and nothing reads a dictionary in insertion sequence.
    """
    events_by_id = context.events_by_id()
    index = _lineage_index(context.candidates)
    lineages: dict[EdgeKey, EdgeLineage] = {}
    typings: dict[EdgeKey, TypingRecord] = {}
    for scored in graph.edges:
        key = scored.sort_key()
        lineages[key] = _lineage_for(scored, index)
        typings[key] = type_edge(scored, context.rule_evaluation)

    reach = max((len(item.generator_ids) for item in lineages.values()), default=1)
    ceiling = context.parameters.diversity_credit_ceiling
    policy = context.parameters.competing_effect_policy

    by_target: dict[str, list[ScoredEdge]] = {}
    for scored in graph.edges:
        by_target.setdefault(scored.edge.target_event_id, []).append(scored)

    promoted: dict[EdgeKey, PromotedEdge] = {}
    demoted: dict[EdgeKey, DemotionRecord] = {}
    weights: dict[EdgeKey, PropagationWeight] = {}

    for target in sorted(by_target):
        incoming = tuple(sorted(by_target[target], key=lambda item: item.sort_key()))
        weights.update(weights_for_effect(incoming, context, events_by_id))

        admitted: list[tuple[ScoredEdge, str]] = []
        for scored in incoming:
            key = scored.sort_key()
            verdict = decide(scored, context.parameters, context.bands, events_by_id)
            if verdict.promotes and verdict.threshold_band is not None:
                admitted.append((scored, verdict.threshold_band))
            else:
                assert verdict.reason is not None  # noqa: S101 -- narrowing, not a check
                demoted[key] = _demotion(scored, verdict.reason, verdict.detail, lineages[key])

        if policy is CompetingEffectPolicy.RETAIN_TOP_N:
            retain = context.parameters.competing_retain_count
            ranked = sorted(
                admitted,
                key=lambda entry: _competition_key(
                    entry[0], lineages[entry[0].sort_key()], ceiling, reach
                ),
            )
            kept, dropped = ranked[: retain or 0], ranked[retain or 0 :]
            for scored, _band in dropped:
                key = scored.sort_key()
                demoted[key] = _demotion(
                    scored,
                    DemotionReason.LOST_COMPETITION,
                    (
                        f"cleared its threshold but placed outside the {retain} strongest "
                        f"cause(s) this pack retains per effect, of {len(admitted)} that "
                        "cleared. This is a judgement about relative standing under the "
                        "pack's declared policy, not a finding against the claim."
                    ),
                    lineages[key],
                )
            admitted = kept

        for scored, band in admitted:
            key = scored.sort_key()
            weight = weights.get(key)
            if weight is None:  # pragma: no cover -- every incoming edge is weighted above
                continue
            promoted[key] = promote(scored, weight, typings[key], band, lineages[key], events_by_id)

    groups = _resolve_joint_groups(graph.edges, promoted, demoted, lineages)

    return PromotedGraph(
        run_id=context.run_id,
        edges=tuple(sorted(promoted.values(), key=lambda item: item.sort_key())),
        demotions=tuple(sorted(demoted.values(), key=lambda item: item.sort_key())),
        joint_groups=tuple(sorted(groups, key=lambda item: item.sort_key())),
        claims_considered=len(graph.edges),
    )


def _resolve_joint_groups(
    scored_edges: tuple[ScoredEdge, ...],
    promoted: dict[EdgeKey, PromotedEdge],
    demoted: dict[EdgeKey, DemotionRecord],
    lineages: dict[EdgeKey, EdgeLineage],
) -> tuple[JointCauseGroup, ...]:
    """Apply all-or-nothing promotion to every joint cause group, in place.

    A group survives only when every one of its declared contributors was promoted on its
    own merits. Any shortfall -- a member below threshold, a member that lost the
    competition, or a declared co-cause that was never scored at all -- demotes the whole
    group, and each surviving member moves from `promoted` into `demoted` under
    `JOINT_GROUP_INCOMPLETE`.

    Promoting a subset is the failure this exists to prevent. prd.md §26's contributing
    cause asserts that several causes *jointly* produce the outcome and that none is
    sufficient alone; a promoted subset says the opposite to every consumer downstream, and
    module 13's counterfactual surgery and module 14's ranking both read exactly that.
    """
    groups = list(group_joint_causes(scored_edges))
    if not groups:
        return ()

    members_by_group: dict[tuple[str, str], list[EdgeKey]] = {}
    for scored in scored_edges:
        payload = scored.edge.payload
        if not isinstance(payload, ContributingCause):
            continue
        members_by_group.setdefault(
            (scored.edge.target_event_id, payload.joint_cause_group_id), []
        ).append(scored.sort_key())

    resolved: list[JointCauseGroup] = []
    for group in groups:
        key = (group.target_event_id, group.joint_cause_group_id)
        member_keys = sorted(members_by_group.get(key, []))
        held_sources = {member[0] for member in member_keys}
        complete = set(group.member_source_event_ids) == held_sources
        all_promoted = complete and all(member in promoted for member in member_keys)
        if all_promoted:
            resolved.append(group.model_copy(update={"promoted": True}))
            continue
        blocked = sorted(member for member in member_keys if member not in promoted)
        detail = (
            group.detail
            + (
                f" The group is NOT promoted: {len(blocked)} of {len(member_keys)} present "
                "member(s) did not clear promotion on their own merits"
                if blocked
                else " The group is NOT promoted: its declared membership exceeds what the "
                "graph holds"
            )
            + (
                ". Promotion is all or nothing, because promoting a subset would tell "
                "counterfactual and intervention analysis that removing any one member "
                "prevents the outcome -- the opposite of what a joint cause asserts "
                "(prd.md §26, ADR-0054)."
            )
        )
        for member in member_keys:
            if member in promoted:
                del promoted[member]
                demoted[member] = DemotionRecord(
                    source_event_id=member[0],
                    target_event_id=member[1],
                    edge_kind=member[2],
                    reason=DemotionReason.JOINT_GROUP_INCOMPLETE,
                    detail=(
                        f"this contributor cleared its own threshold, but joint cause group "
                        f"{group.joint_cause_group_id} could not be promoted in full. " + detail
                    ),
                    lineage=lineages[member],
                )
        resolved.append(group.model_copy(update={"promoted": False, "detail": detail}))
    return tuple(resolved)
