"""The Graph Quality Report: what the stated causal graph does NOT contain, first.

Section sequence is the argument. Module 10's confidence report opens with what is not
calibrated; this one opens with what is not in the graph and which policies never ran,
because on any honest run of this pipeline those are the largest facts about the artifact.
A report that led with edge counts would invite a reader to treat a small number as a
finding about the domain when it is usually a finding about the source or the pack.

Every count here is over the run it describes. Nothing is compared against a prior run,
because a `run_id` change re-dates every artifact (ADR-0013) and a cross-run delta printed
without that context reads as a change in the world.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.causal_graph_builder.cycles import (
    GAIN_CEILING_NOTICE,
    DetectionStatus,
    LoopClassification,
    LoopDetectionResult,
)
from causalog.causal_engine.causal_graph_builder.graph import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE,
    DemotionReason,
    PromotedGraph,
    TypingBasis,
    WeightBasis,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope

__all__ = [
    "GRAPH_QUALITY_SCHEMA_VERSION",
    "RENDERED_ARTIFACT_CIRCUITS",
    "STATED_VIEW_NOTICE",
    "ContradictionFinding",
    "GraphQualityReport",
    "OrphanEffect",
    "PolicyGap",
    "render_markdown",
]

GRAPH_QUALITY_SCHEMA_VERSION = "1.0.0"

#: How many non-genuine circuits to spell out. Module 9's `SAMPLED_CONFOUNDING_FLAGS` idiom:
#: a bounded sample plus the total, because two hundred near-identical paragraphs are not
#: more informative than twenty-five and a count -- they are less, because nobody reads them.
#: The full set is in the JSON beside this report.
RENDERED_ARTIFACT_CIRCUITS = 25

#: Fixed text. The one thing every reader of this artifact must understand about it.
STATED_VIEW_NOTICE = (
    "THIS IS THE ENGINE'S STATED VIEW, AND IT IS SMALLER THAN THE TRUTH. Every edge below "
    "cleared a threshold the rule pack declares; every claim that did not is in the "
    "rejection ledger with the reason. A cause absent from this graph was not ruled out -- "
    "it was never proposed, never measured, or never cleared. The graph asserts what it "
    "contains. It asserts nothing about what it omits."
)


class PolicyGap(BaseModel):
    """One declaration the pack did not make, and what it cost.

    ADR-0049's rule made structural: an absent declaration is reported as NOT RUNNABLE with
    its requirement named, never silently defaulted and never reported as a clean zero.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: str = Field(min_length=1)
    requirement: str = Field(min_length=1)
    consequence: str = Field(min_length=1)


class OrphanEffect(BaseModel):
    """An outcome with no promoted explanation. A coverage gap, reported as one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: str = Field(min_length=1)
    events: int = Field(ge=1)
    #: How many claims over effects of this type were considered and rejected.
    considered_and_rejected: int = Field(ge=0)
    #: The reasons those rejections carried, tallied. Empty means nothing was ever proposed,
    #: which is a different and more serious gap than a proposal that fell short.
    rejection_reasons: tuple[tuple[str, int], ...] = ()


class ContradictionFinding(BaseModel):
    """Two promoted edges that cannot both be acted on. Reported, never resolved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    first: str = Field(min_length=1)
    second: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class GraphQualityReport(BaseModel):
    """Everything measurable about one run's stated causal graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = GRAPH_QUALITY_SCHEMA_VERSION
    envelope: OutputEnvelope
    claims_considered: int = Field(ge=0)
    promoted_count: int = Field(ge=0)
    demoted_count: int = Field(ge=0)
    policy_gaps: tuple[PolicyGap, ...] = ()
    #: `(edge_kind, band_name, count)` over promoted edges, sorted.
    kind_band_counts: tuple[tuple[str, str, int], ...] = ()
    #: `(edge_kind, count)` over every claim considered, sorted. The denominator.
    considered_by_kind: tuple[tuple[str, int], ...] = ()
    demotions_by_reason: tuple[tuple[str, int], ...] = ()
    #: Reasons that occurred zero times. Listed so a zero is visible as a zero.
    unused_demotion_reasons: tuple[str, ...] = ()
    #: `(degree, event_count)` over promoted edges, sorted by degree.
    in_degree_histogram: tuple[tuple[int, int], ...] = ()
    out_degree_histogram: tuple[tuple[int, int], ...] = ()
    orphan_effects: tuple[OrphanEffect, ...] = ()
    orphan_effect_share: float = Field(default=0.0, ge=0.0, le=1.0)
    contradictions: tuple[ContradictionFinding, ...] = ()
    loops: LoopDetectionResult
    #: `(TypingBasis, count)` over promoted edges.
    typing_bases: tuple[tuple[str, int], ...] = ()
    typing_disagreements: int = Field(default=0, ge=0)
    #: `(WeightBasis, count)` over promoted edges.
    weight_bases: tuple[tuple[str, int], ...] = ()
    #: Effect types whose weights fell back to a share of belief, sorted.
    magnitude_fallback_effects: tuple[str, ...] = ()
    joint_groups_total: int = Field(default=0, ge=0)
    joint_groups_promoted: int = Field(default=0, ge=0)
    #: Promoted edges resting on at least one ASSUMED input, and the share.
    edges_on_assumed_inputs: int = Field(default=0, ge=0)
    assumed_input_share: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def graph_is_empty(self) -> bool:
        """Return whether the engine asserts nothing at all this run."""
        return self.promoted_count == 0

    def promotion_share(self) -> float:
        """Return the share of considered claims that became the stated view."""
        if self.claims_considered == 0:
            return 0.0
        return self.promoted_count / self.claims_considered


def build_report(
    graph: PromotedGraph,
    loops: LoopDetectionResult,
    envelope: OutputEnvelope,
    *,
    events_by_type: dict[str, int],
    considered_by_kind: tuple[tuple[str, int], ...],
    rejected_effect_types: dict[str, tuple[tuple[str, int], ...]],
    explained_effect_types: frozenset[str],
    policy_gaps: tuple[PolicyGap, ...],
) -> GraphQualityReport:
    """Assemble the report over a promoted graph and its detected loops."""
    kind_band: dict[tuple[str, str], int] = {}
    typing: dict[str, int] = {}
    weights: dict[str, int] = {}
    fallbacks: set[str] = set()
    disagreements = 0
    assumed = 0
    for edge in graph.edges:
        key = (edge.edge.payload.edge_kind.value, edge.lineage.band_name or "(no band)")
        kind_band[key] = kind_band.get(key, 0) + 1
        typing[edge.typing.basis.value] = typing.get(edge.typing.basis.value, 0) + 1
        disagreements += len(edge.typing.disagreements)
        weights[edge.weight.basis.value] = weights.get(edge.weight.basis.value, 0) + 1
        if edge.weight.basis is WeightBasis.CONFIDENCE_SHARE:
            fallbacks.add(edge.edge.target_event_id)
        if any(item.provenance_class is ProvenanceClass.ASSUMED for item in edge.edge.evidence):
            assumed += 1

    incoming: dict[str, int] = {}
    outgoing: dict[str, int] = {}
    for edge in graph.edges:
        incoming[edge.edge.target_event_id] = incoming.get(edge.edge.target_event_id, 0) + 1
        outgoing[edge.edge.source_event_id] = outgoing.get(edge.edge.source_event_id, 0) + 1

    def histogram(counts: dict[str, int]) -> tuple[tuple[int, int], ...]:
        tally: dict[int, int] = {}
        for value in counts.values():
            tally[value] = tally.get(value, 0) + 1
        return tuple(sorted(tally.items()))

    orphans = tuple(
        OrphanEffect(
            event_type=event_type,
            events=count,
            considered_and_rejected=sum(
                total for _reason, total in rejected_effect_types.get(event_type, ())
            ),
            rejection_reasons=rejected_effect_types.get(event_type, ()),
        )
        for event_type, count in sorted(events_by_type.items())
        if event_type not in explained_effect_types
    )
    orphan_share = len(orphans) / len(events_by_type) if events_by_type else 0.0

    observed_reasons = {reason for reason, _count in graph.demotions_by_reason()}
    unused = tuple(
        sorted(member.value for member in DemotionReason if member.value not in observed_reasons)
    )

    return GraphQualityReport(
        envelope=envelope,
        claims_considered=graph.claims_considered,
        promoted_count=len(graph.edges),
        demoted_count=len(graph.demotions),
        policy_gaps=policy_gaps,
        kind_band_counts=tuple(
            sorted((kind, band, count) for (kind, band), count in kind_band.items())
        ),
        considered_by_kind=considered_by_kind,
        demotions_by_reason=graph.demotions_by_reason(),
        unused_demotion_reasons=unused,
        in_degree_histogram=histogram(incoming),
        out_degree_histogram=histogram(outgoing),
        orphan_effects=orphans,
        orphan_effect_share=orphan_share,
        contradictions=_contradictions(graph),
        loops=loops,
        typing_bases=tuple(sorted(typing.items())),
        typing_disagreements=disagreements,
        weight_bases=tuple(sorted(weights.items())),
        magnitude_fallback_effects=tuple(sorted(fallbacks)),
        joint_groups_total=len(graph.joint_groups),
        joint_groups_promoted=sum(1 for group in graph.joint_groups if group.promoted),
        edges_on_assumed_inputs=assumed,
        assumed_input_share=(assumed / len(graph.edges)) if graph.edges else 0.0,
    )


def _contradictions(graph: PromotedGraph) -> tuple[ContradictionFinding, ...]:
    """Find promoted edge pairs that cannot both be acted on.

    Two shapes, and both are reported rather than resolved -- resolving one would require
    deciding which of two claims the engine already stands behind is wrong, which is not a
    decision a reporting function may make (the ADR-0051 idiom, again).
    """
    found: list[ContradictionFinding] = []
    by_pair: dict[tuple[str, str], list[str]] = {}
    for edge in graph.edges:
        by_pair.setdefault((edge.edge.source_event_id, edge.edge.target_event_id), []).append(
            edge.edge.payload.edge_kind.value
        )
    for (source, target), kinds in sorted(by_pair.items()):
        reverse = by_pair.get((target, source))
        if reverse is not None and source < target:
            found.append(
                ContradictionFinding(
                    first=f"{source} -> {target} ({', '.join(sorted(kinds))})",
                    second=f"{target} -> {source} ({', '.join(sorted(reverse))})",
                    detail=(
                        "Both directions are promoted between one pair of events. Both "
                        "cleared LAW-TIME, which means each was found to precede the other "
                        "-- impossible for two fixed intervals, so at least one stored "
                        "verdict does not describe the data. Reported, not resolved."
                    ),
                )
            )
        if "DIRECT" in kinds and "INHIBITING" in kinds:
            found.append(
                ContradictionFinding(
                    first=f"{source} -> {target} (DIRECT)",
                    second=f"{source} -> {target} (INHIBITING)",
                    detail=(
                        "One event is asserted both to produce the effect and to reduce "
                        "propagation through it. Not impossible -- a cause can have "
                        "opposing pathways -- but a reader acting on either claim alone "
                        "would be acting against the other, so both are surfaced together."
                    ),
                )
            )
    return tuple(found)


def _percent(value: float) -> str:
    return f"{value:.6f}"


def render_markdown(report: GraphQualityReport) -> str:
    """Render the report. Returns a string; writing it to a file belongs in `scripts/`."""
    lines: list[str] = ["# Graph Quality Report", ""]
    lines.append(f"- `report_schema_version`: `{report.report_schema_version}`")
    lines.append(f"- `run_id`: `{report.envelope.run_id}`")
    lines.append(f"- `rule_pack_version`: `{report.envelope.rule_pack_version}`")
    lines.append(f"- claims considered: {report.claims_considered}")
    lines.append(f"- promoted to `INFERRED`: **{report.promoted_count}**")
    lines.append(f"- considered and rejected: {report.demoted_count}")
    lines.append("")

    lines.append("## What this graph does not contain")
    lines.append("")
    lines.append(STATED_VIEW_NOTICE)
    lines.append("")
    if report.graph_is_empty:
        lines.append(
            "**THE STATED VIEW IS EMPTY.** Not one claim of the "
            f"{report.claims_considered} considered cleared the thresholds this pack "
            "declares. That is a finding about the source and the pack, and it is reported "
            "as one: the rejection ledger below says, per reason, exactly what stopped each "
            "claim. An empty graph published with its ledger is a more useful artifact than "
            "a populated graph produced by lowering a threshold until something appeared."
        )
        lines.append("")
    if report.policy_gaps:
        lines.append("### Policies that could not run")
        lines.append("")
        lines.append(
            "An absent declaration is reported, never defaulted. A default written into the "
            "engine would be a judgement wearing a schema default's clothes (ADR-0049)."
        )
        lines.append("")
        lines.append("| policy | needs | consequence |")
        lines.append("|---|---|---|")
        for gap in report.policy_gaps:
            lines.append(f"| `{gap.policy}` | {gap.requirement} | {gap.consequence} |")
        lines.append("")

    lines.append("## The rejection ledger — what was considered and rejected")
    lines.append("")
    lines.append(
        "Never summed into a single 'rejected' count. Each reason answers a different "
        "question, and a reader asking 'is the pack too strict?' needs a different row from "
        "one asking 'does this source support causal claims at all?'"
    )
    lines.append("")
    if report.demotions_by_reason:
        lines.append("| reason | claims | share of considered |")
        lines.append("|---|---:|---:|")
        for reason, count in report.demotions_by_reason:
            share = count / report.claims_considered if report.claims_considered else 0.0
            lines.append(f"| `{reason}` | {count} | {_percent(share)} |")
    else:
        lines.append("No claim was rejected.")
    lines.append("")
    if report.unused_demotion_reasons:
        lines.append(
            "Reasons that occurred **zero** times this run, listed so that a zero is "
            "visible rather than an absent row: "
            + ", ".join(f"`{reason}`" for reason in report.unused_demotion_reasons)
            + "."
        )
        lines.append("")

    lines.append("## Promoted edges by kind and band")
    lines.append("")
    if report.kind_band_counts:
        lines.append("| edge kind | band | edges |")
        lines.append("|---|---|---:|")
        for kind, band, count in report.kind_band_counts:
            lines.append(f"| `{kind}` | `{band}` | {count} |")
    else:
        lines.append("No edge was promoted, so there is nothing to break down by band.")
    lines.append("")
    if report.considered_by_kind:
        lines.append("Claims **considered** per kind, which is the denominator above:")
        lines.append("")
        lines.append("| edge kind | considered |")
        lines.append("|---|---:|")
        for kind, count in report.considered_by_kind:
            lines.append(f"| `{kind}` | {count} |")
        lines.append("")

    lines.append("## Degree distributions")
    lines.append("")
    for label, histogram in (
        ("in-degree (causes per effect)", report.in_degree_histogram),
        ("out-degree (effects per cause)", report.out_degree_histogram),
    ):
        lines.append(f"**{label}**")
        lines.append("")
        if histogram:
            lines.append("| degree | events |")
            lines.append("|---:|---:|")
            for degree, count in histogram:
                lines.append(f"| {degree} | {count} |")
        else:
            lines.append("Empty: no promoted edge touches any event.")
        lines.append("")

    lines.append("## Orphan effects — outcomes with no explanation")
    lines.append("")
    lines.append(
        "A coverage gap, and an honest one. An event type here has no promoted incoming "
        "edge: the engine offers no account of why events of that type occur. The rejection "
        "column separates 'nothing was ever proposed' from 'proposals were made and fell "
        "short', which are different problems with different fixes."
    )
    lines.append("")
    lines.append(
        f"**{len(report.orphan_effects)} of the event types in this run are orphans "
        f"({_percent(report.orphan_effect_share)} of them).**"
    )
    lines.append("")
    if report.orphan_effects:
        lines.append("| event type | events | considered and rejected | reasons |")
        lines.append("|---|---:|---:|---|")
        for orphan in report.orphan_effects:
            reasons = (
                ", ".join(f"`{reason}`: {count}" for reason, count in orphan.rejection_reasons)
                or "*nothing was ever proposed*"
            )
            lines.append(
                f"| `{orphan.event_type}` | {orphan.events} | "
                f"{orphan.considered_and_rejected} | {reasons} |"
            )
        lines.append("")

    lines.append("## Contradictory edge pairs")
    lines.append("")
    if report.contradictions:
        lines.append(
            "Reported, not resolved. Resolving one would mean deciding which of two claims "
            "the engine already stands behind is wrong, which is not a decision a report "
            "may make."
        )
        lines.append("")
        for finding in report.contradictions:
            lines.append(f"- `{finding.first}` **vs** `{finding.second}` — {finding.detail}")
    else:
        lines.append("None found among the promoted edges.")
    lines.append("")

    lines.extend(_render_loops(report))

    lines.append("## Propagation weights")
    lines.append("")
    lines.append(ATTRIBUTION_NOT_MEASUREMENT_NOTICE)
    lines.append("")
    if report.weight_bases:
        lines.append("| basis | edges |")
        lines.append("|---|---:|")
        for basis, count in report.weight_bases:
            lines.append(f"| `{basis}` | {count} |")
        lines.append("")
    else:
        lines.append("No promoted edge, so no weight was published.")
        lines.append("")
    if report.magnitude_fallback_effects:
        lines.append(
            f"**{len(report.magnitude_fallback_effects)} effect(s) fell back to a share of "
            "BELIEF** because no declared magnitude was available for them. A share of "
            "belief and a share of a quantity are different things wearing one number; they "
            "are separated here and on every edge rather than printed under one heading."
        )
        lines.append("")

    lines.append("## Edge typing")
    lines.append("")
    if report.typing_bases:
        lines.append("| basis | edges |")
        lines.append("|---|---:|")
        for basis, count in report.typing_bases:
            lines.append(f"| `{basis}` | {count} |")
        lines.append("")
        lines.append(
            f"`{TypingBasis.UNTYPED_DEFAULT.value}` is not evidence of directness. It means "
            "the edge is `DIRECT` because nothing qualified it, and its size is a coverage "
            "statement about the rule pack rather than a property of the graph."
        )
        lines.append("")
    else:
        lines.append("No promoted edge, so nothing was typed.")
        lines.append("")
    if report.typing_disagreements:
        lines.append(
            f"**{report.typing_disagreements} typing disagreement(s)** between a firing "
            "rule's kind and the edge's payload. Recorded on the edges and resolved by "
            "nobody: the payload's kind stands because it is in the content address."
        )
        lines.append("")

    lines.append("## Joint cause groups")
    lines.append("")
    lines.append(
        f"{report.joint_groups_promoted} of {report.joint_groups_total} group(s) promoted. "
        "Promotion is all-or-nothing: promoting a subset would tell counterfactual and "
        "intervention analysis that removing any one member prevents the outcome, which is "
        "the opposite of what a joint cause asserts (prd.md §26)."
    )
    lines.append("")

    lines.append("## How much of this graph rests on `ASSUMED` inputs")
    lines.append("")
    lines.append(
        f"**{report.edges_on_assumed_inputs} of {report.promoted_count} promoted edge(s) "
        f"({_percent(report.assumed_input_share)}) carry at least one evidence item whose "
        "provenance is `ASSUMED`.** An assumption is not a defect and is not hidden: "
        "LAW-PROVENANCE requires it to travel with the claim, and this line is where its "
        "weight in the whole graph becomes visible rather than being discoverable only by "
        "opening every edge."
    )
    lines.append("")
    return "\n".join(lines)


def _render_loops(report: GraphQualityReport) -> list[str]:
    """Render the feedback-loop sections, artifacts kept apart from findings."""
    lines: list[str] = ["## Feedback loops (prd.md §31)", ""]
    loops = report.loops
    if loops.status is DetectionStatus.NOT_RUNNABLE:
        lines.append(
            "**LOOP DETECTION DID NOT RUN.** This is not a report of zero loops. It needs: "
            f"{loops.requirement}"
        )
        lines.append("")
        return lines

    lines.append(
        "Circuits are enumerated over the event-TYPE projection, not over event instances. "
        "At the instance level a genuine loop is arithmetically impossible -- a `CERTAIN` "
        "verdict is a strict precedence relation and strict precedence admits no cycle "
        "-- so a detector "
        "running there could only ever find artifacts. prd.md §31's loop closes across "
        "process instances, which is what makes it a mechanism rather than a sorting error."
    )
    lines.append("")
    lines.append(
        f"Examined {loops.types_examined} event type(s) over {loops.projected_links} "
        "projected link(s)."
    )
    lines.append("")
    lines.append("| classification | circuits |")
    lines.append("|---|---:|")
    for name, count in loops.by_classification():
        lines.append(f"| `{name}` | {count} |")
    lines.append("")
    if loops.truncations:
        for truncation in loops.truncations:
            lines.append(
                f"**Enumeration truncated** at the declared cap of {truncation.cap} after "
                f"{truncation.enumerated} circuit(s) over "
                f"{len(truncation.component_event_types)} type(s). Circuit enumeration is "
                "exponential in the worst case; the bound is reported rather than silently "
                "applied."
            )
        lines.append("")

    genuine = [loop for loop in loops.loops if loop.classification is LoopClassification.GENUINE]
    lines.append("### Genuine reinforcing loops")
    lines.append("")
    if not genuine:
        lines.append(
            "**None.** No circuit had temporally sound, promoted support on every link "
            "across more than one process instance. On a source recorded at day "
            "granularity this is the expected result and is a finding about the source "
            "(CONTEXT.md R-14) rather than evidence that the domain contains no loops."
        )
        lines.append("")
    else:
        lines.append(GAIN_CEILING_NOTICE)
        lines.append("")
        for loop in genuine:
            lines.append(f"#### {' -> '.join(loop.participants)} -> {loop.participants[0]}")
            lines.append("")
            lines.append(
                f"- loop gain: {loop.loop_gain:.6f}"
                if loop.loop_gain is not None
                else "- loop gain: not computable"
            )
            lines.append(f"- process instances involved: {len(loop.process_instance_ids)}")
            if loop.weakest_link_index is not None:
                weakest = loop.members[loop.weakest_link_index]
                lines.append(
                    f"- **weakest link**: `{weakest.source_event_type} -> "
                    f"{weakest.target_event_type}` at weight {weakest.weight:.6f}. This is "
                    "the cheapest place to break the circuit *in propagation terms only*. "
                    "What it would COST to break is module 14's `CostModel`, not this "
                    "number."
                )
            lines.append("")
            lines.append("| link | kind | supporting claims | sound | promoted | weight |")
            lines.append("|---|---|---:|---:|---:|---:|")
            for member in loop.members:
                lines.append(
                    f"| `{member.source_event_type} -> {member.target_event_type}` | "
                    f"`{member.edge_kind}` | {len(member.supporting_pairs)} | "
                    f"{member.temporally_sound_count} | {member.promoted_count} | "
                    f"{member.weight:.6f} |"
                )
            lines.append("")

    artifacts = [
        loop for loop in loops.loops if loop.classification is not LoopClassification.GENUINE
    ]
    lines.append("### Circuits that are NOT feedback loops")
    lines.append("")
    if not artifacts:
        lines.append("None.")
        lines.append("")
        return lines
    lines.append(
        "Kept in their own section deliberately. A circuit resting on unresolvable precedence "
        "is a statement about the source's timestamps; presenting it beside a genuine loop "
        "would let a reader act on a data artifact."
    )
    lines.append("")
    for loop in artifacts[:RENDERED_ARTIFACT_CIRCUITS]:
        lines.append(
            f"- **`{loop.classification.value}`** — "
            f"{' -> '.join(loop.participants)} -> {loop.participants[0]}. "
            f"{loop.classification_reason}"
        )
    if len(artifacts) > RENDERED_ARTIFACT_CIRCUITS:
        lines.append("")
        lines.append(
            f"*{len(artifacts) - RENDERED_ARTIFACT_CIRCUITS} further circuit(s) are not "
            f"spelled out here; {len(artifacts)} were found in total and all of them are in "
            "the JSON beside this report. The sample is bounded because near-identical "
            "paragraphs do not become more informative by repetition.*"
        )
    lines.append("")
    return lines
