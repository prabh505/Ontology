"""`PropagationReport` -- prd.md §30's seven measures, and what was not measured.

The first section is what the report does NOT contain. That is the habit every report in
this engine keeps, and here it earns its place twice over: a traversal that hit its depth
bound has measured the first part of propagation rather than propagation, and a reader who
sees the depth figure before the truncation notice has already formed the wrong belief.

prd.md §30 lists seven things propagation includes. All seven are here and **none of them is
combined with another**: depth and breadth are separate fields, duration and economic
magnitude are separate rows keyed by the measurement that produced them, affected entities
and affected process instances are separate counts, and confidence is composed per route
under a named function with its length beside it. A single "propagation score" would be a
figure that rises for seven unrelated reasons and falls for none of them legibly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.propagation_analyzer.context import PropagationContext
from causalog.causal_engine.propagation_analyzer.graph import PropagationTree
from causalog.causal_engine.propagation_analyzer.view import (
    DIAGNOSTIC_NOT_STATED_NOTICE,
    GraphStanding,
)
from causalog.core.identifiers import format_float
from causalog.core.run import OutputEnvelope

__all__ = [
    "PROPAGATION_REPORT_SCHEMA_VERSION",
    "PolicyGap",
    "PropagationReport",
    "build_report",
    "render_markdown",
]

PROPAGATION_REPORT_SCHEMA_VERSION = "1.0.0"

#: The most nodes rendered into the markdown artifact. The JSON carries every one; the
#: markdown is for a human, and a table of five thousand rows is not read by anyone.
RENDERED_NODES = 40


class PolicyGap(BaseModel):
    """A declaration the pack does not make, with what it would have enabled.

    The same three fields the Causal Graph Builder's gap carries, because it is the same
    finding: an absent declaration reported, never defaulted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: str = Field(min_length=1)
    requirement: str = Field(min_length=1)
    consequence: str = Field(min_length=1)


class PropagationReport(BaseModel):
    """One seed's propagation, measured -- and the account of what was not measured."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = PROPAGATION_REPORT_SCHEMA_VERSION
    envelope: OutputEnvelope
    standing: GraphStanding
    seed_event_id: str = Field(min_length=1)
    #: prd.md §30's two structural measures, as two fields. Never averaged.
    depth: int = Field(ge=0)
    breadth: int = Field(ge=0)
    consequence_count: int = Field(ge=0)
    #: prd.md §30's "affected entities", and the process instances beside it. Two counts,
    #: because one entity in forty instances and forty entities in one instance are
    #: different situations with different responses.
    affected_entity_count: int = Field(ge=0)
    affected_instance_count: int = Field(ge=0)
    #: `(depth, consequences at that depth)`, sorted. The shape behind the two headline
    #: numbers, so a reader can see whether the breadth is one wide level or many even ones.
    consequences_per_depth: tuple[tuple[int, int], ...] = ()
    #: `(event_type, count)`, sorted. What kind of thing the consequence set is made of.
    consequences_by_type: tuple[tuple[str, int], ...] = ()
    #: The headline magnitude: its measurement, unit, declared combination and value.
    measurement_id: str | None = None
    unit: str | None = None
    combination: str | None = None
    combined_magnitude: float | None = None
    #: How many consequences the total rests on, against how many exist. A total over three
    #: of forty is a different claim from a total over forty.
    measured_member_count: int = Field(default=0, ge=0)
    magnitude_absent_because: str | None = None
    #: Every consequence whose declared magnitude could not be evaluated, with its reason.
    #: Named individually rather than counted, because each names a different gap.
    unvalued_consequences: tuple[tuple[str, str], ...] = ()
    #: `(composition_name, node_count)`. Which function composed each route's confidence.
    composition: str | None = None
    #: The weakest and strongest composed route confidence in the tree, and the shape
    #: between them. Two runs of one input produce one histogram.
    composed_histogram: tuple[tuple[str, int], ...] = ()
    #: Distinct composed values over distinct routes. Reported because a PLATEAU is not a
    #: ranking: where every route composes to one value the engine cannot separate them, and
    #: module 11 must say so rather than breaking the tie on something arbitrary.
    distinct_composed_values: int = Field(default=0, ge=0)
    #: `(reason, count)`, sorted. Never summed into one "truncated" figure: a depth bound
    #: and a circuit are different findings and a reader asking "is my bound too tight?"
    #: needs a different row from one asking "does this domain contain loops?".
    truncations_by_reason: tuple[tuple[str, int], ...] = ()
    truncated: bool = False
    policy_gaps: tuple[PolicyGap, ...] = ()
    links_available: int = Field(default=0, ge=0)
    not_runnable_because: str | None = None

    @property
    def notice(self) -> str | None:
        """Return the disowning notice for a diagnostic report, or None for a stated one."""
        if self.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC:
            return DIAGNOSTIC_NOT_STATED_NOTICE
        return None


def _policy_gaps(context: PropagationContext) -> tuple[PolicyGap, ...]:
    """Collect every declaration the pack does not make, sorted by policy name."""
    gaps: list[PolicyGap] = []
    parameters = context.parameters
    if parameters.maximum_depth is None:
        gaps.append(
            PolicyGap(
                policy="propagation_analysis.maximum_depth",
                requirement="a positive integer bounding how far the traversal walks",
                consequence=(
                    "no traversal ran and no consequence was measured. This is reported "
                    "rather than defaulted: how far consequence travels before it stops "
                    "being consequence is a domain judgement, and a bound written into the "
                    "engine would be this engine's opinion about someone else's domain."
                ),
            )
        )
    if parameters.traversal_node_cap is None:
        gaps.append(
            PolicyGap(
                policy="propagation_analysis.traversal_node_cap",
                requirement="a positive integer bounding how many consequences one walk visits",
                consequence=(
                    "the walk is bounded by depth alone. On a wide graph that is a weaker "
                    "bound than it looks, because a single level can hold arbitrarily many "
                    "consequences."
                ),
            )
        )
    if not parameters.impact_aggregation:
        gaps.append(
            PolicyGap(
                policy="propagation_analysis.impact_aggregation",
                requirement="one entry per measurement, naming how two readings combine",
                consequence=(
                    "no total is produced for any measurement. Each consequence's own "
                    "magnitude is still read and reported; only the combination is absent, "
                    "and it is absent rather than assumed because whether two readings add "
                    "is domain policy."
                ),
            )
        )
    if parameters.path_confidence_composition is None:
        gaps.append(
            PolicyGap(
                policy="propagation_analysis.path_confidence_composition",
                requirement=("the name of a function registered in causalog.core.composition"),
                consequence=(
                    "routes are composed under the engine's default and the report says "
                    "which. The per-link values are carried whatever the pack declares, so "
                    "nothing is lost -- but the pack has not stated which composition its "
                    "numbers should be read under."
                ),
            )
        )
    return tuple(sorted(gaps, key=lambda gap: gap.policy))


def build_report(
    tree: PropagationTree, context: PropagationContext, envelope: OutputEnvelope
) -> PropagationReport:
    """Assemble the report over one finished tree. Pure: it measures and decides nothing."""
    per_depth: dict[int, int] = {}
    per_type: dict[str, int] = {}
    entities: set[str] = set()
    instances: set[str] = set()
    unvalued: list[tuple[str, str]] = []
    buckets: dict[str, int] = {}
    distinct: set[str] = set()
    for node in tree.nodes:
        per_depth[node.depth] = per_depth.get(node.depth, 0) + 1
        per_type[node.event_type] = per_type.get(node.event_type, 0) + 1
        entities.update(node.entity_ids)
        instances.update(node.process_instance_ids)
        if node.magnitude.unavailable_because is not None:
            unvalued.append((node.event_id, node.magnitude.unavailable_because))
        label = format_float(node.path_confidence.composed)
        buckets[label] = buckets.get(label, 0) + 1
        distinct.add(label)
    reasons: dict[str, int] = {}
    for record in tree.truncations:
        reasons[record.reason.value] = reasons.get(record.reason.value, 0) + 1
    consequences = tree.consequences
    return PropagationReport(
        envelope=envelope,
        standing=tree.standing,
        seed_event_id=tree.seed_event_id,
        depth=tree.depth,
        breadth=tree.breadth,
        consequence_count=len(tree.nodes),
        affected_entity_count=len(entities),
        affected_instance_count=len(instances),
        consequences_per_depth=tuple(sorted(per_depth.items())),
        consequences_by_type=tuple(sorted(per_type.items())),
        measurement_id=consequences.measurement_id,
        unit=consequences.unit,
        combination=consequences.combination,
        combined_magnitude=consequences.combined,
        measured_member_count=consequences.measured_member_count,
        magnitude_absent_because=consequences.combination_absent_because,
        unvalued_consequences=tuple(sorted(unvalued)),
        composition=(tree.nodes[0].path_confidence.composition if tree.nodes else None),
        composed_histogram=tuple(sorted(buckets.items())),
        distinct_composed_values=len(distinct),
        truncations_by_reason=tuple(sorted(reasons.items())),
        truncated=tree.truncated,
        policy_gaps=_policy_gaps(context),
        links_available=context.view.link_count(),
        not_runnable_because=tree.not_runnable_because,
    )


def _standing_heading(report: PropagationReport) -> list[str]:
    """Render the standing block. Always present, so its absence can never be an oversight."""
    lines = [f"- standing: `{report.standing.value}`"]
    if report.notice is not None:
        lines.extend(["", f"> **{report.notice}**"])
    else:
        lines.extend(
            [
                "",
                "> Every link walked below is one the engine asserts. It is still not proof "
                "of causation: this engine measures support, and no part of it identifies a "
                "causal effect.",
            ]
        )
    return lines


def render_markdown(report: PropagationReport) -> str:
    """Render the report as markdown. Returns a string; writing it belongs in `scripts/`."""
    lines: list[str] = ["# Propagation Report", ""]
    lines.extend(_standing_heading(report))
    lines.extend(
        [
            "",
            f"- `report_schema_version`: `{report.report_schema_version}`",
            f"- `run_id`: `{report.envelope.run_id}`",
            f"- seed: `{report.seed_event_id}`",
            f"- links available in this view: {report.links_available}",
            "",
            "## What this report does not contain",
            "",
        ]
    )
    if report.not_runnable_because is not None:
        lines.extend(
            [
                f"**THE TRAVERSAL DID NOT RUN.** {report.not_runnable_because}",
                "",
                "Every figure below is therefore absent rather than zero.",
                "",
            ]
        )
    elif report.truncated:
        lines.extend(
            [
                "**THIS TRAVERSAL WAS TRUNCATED.** It measured the first part of "
                "propagation, not propagation. Every figure below is a LOWER BOUND: "
                "consequences exist beyond the frontier and were not walked. The reasons "
                "are broken out below and are never summed into one figure, because a "
                "depth bound and a circuit are different findings.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The traversal ran to exhaustion within its declared bounds. That is a "
                "statement about this graph and these bounds, not about the world: a "
                "consequence the graph never claimed is a consequence this report cannot "
                "see, and the graph is smaller than the truth.",
                "",
            ]
        )
    if report.unvalued_consequences:
        lines.append(
            f"{len(report.unvalued_consequences)} of {report.consequence_count} "
            "consequence(s) could not be valued and are excluded from the total below, "
            "never counted as zero. Each one's reason is listed under 'Consequences "
            "without a magnitude'."
        )
        lines.append("")
    if report.policy_gaps:
        lines.extend(
            [
                "### Policies that could not run",
                "",
                "An absent declaration is reported, never defaulted (ADR-0049).",
                "",
                "| policy | needs | consequence |",
                "|---|---|---|",
            ]
        )
        lines.extend(
            f"| `{gap.policy}` | {gap.requirement} | {gap.consequence} |"
            for gap in report.policy_gaps
        )
        lines.append("")
    lines.extend(
        [
            "## Depth and breadth",
            "",
            "prd.md §30's two structural measures, as two numbers. They are never averaged: "
            "a deep narrow chain and a shallow wide fan-out are different problems and one "
            "figure could not tell them apart.",
            "",
            f"- propagation depth: **{report.depth}**",
            f"- propagation breadth (widest single level): **{report.breadth}**",
            f"- consequences reached: **{report.consequence_count}**",
            f"- affected entities: **{report.affected_entity_count}**",
            f"- affected process instances: **{report.affected_instance_count}**",
            "",
        ]
    )
    if report.consequences_per_depth:
        lines.extend(["| depth | consequences |", "|---:|---:|"])
        lines.extend(f"| {depth} | {count} |" for depth, count in report.consequences_per_depth)
        lines.append("")
    lines.extend(["## Magnitude", "", f"> {report.notice or ''}" if report.notice else "", ""])
    if report.combined_magnitude is None:
        lines.extend(
            [
                "**No total.** " + (report.magnitude_absent_because or "reason unrecorded."),
                "",
                "This is an absence, not a figure of zero.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- measurement: `{report.measurement_id}` ({report.unit})",
                f"- combined under: `{report.combination}` "
                "-- declared by the pack, never assumed by the engine",
                f"- combined magnitude: **{format_float(report.combined_magnitude)}** "
                f"{report.unit}",
                f"- resting on {report.measured_member_count} of {report.consequence_count} "
                "consequence(s); the rest could not be valued and are excluded rather than "
                "counted as zero",
                "",
            ]
        )
    if report.unvalued_consequences:
        lines.extend(
            [
                "### Consequences without a magnitude",
                "",
                "| consequence | why |",
                "|---|---|",
            ]
        )
        lines.extend(
            f"| `{event_id}` | {reason} |"
            for event_id, reason in report.unvalued_consequences[:RENDERED_NODES]
        )
        if len(report.unvalued_consequences) > RENDERED_NODES:
            lines.append(
                f"| ... | {len(report.unvalued_consequences) - RENDERED_NODES} further "
                "row(s) in the JSON artifact |"
            )
        lines.append("")
    lines.extend(
        [
            "## Route confidence",
            "",
            f"Composed under `{report.composition or 'nothing -- no route was composed'}`. "
            "A chain is only as strong as its weakest link; the length-sensitive product is "
            "carried beside every composed value in the JSON artifact and is never blended "
            "with it.",
            "",
        ]
    )
    if report.distinct_composed_values <= 1 and report.consequence_count > 1:
        lines.extend(
            [
                "**THIS IS A PLATEAU, NOT A RANKING.** Every route composes to one value, "
                "so the engine cannot separate these consequences by confidence. Any "
                "sequencing imposed on them would be arbitrary, and module 11 reports the tie "
                "rather than breaking it.",
                "",
            ]
        )
    if report.composed_histogram:
        lines.extend(["| composed confidence | routes |", "|---|---:|"])
        lines.extend(f"| {value} | {count} |" for value, count in report.composed_histogram)
        lines.extend(["", f"distinct composed values: **{report.distinct_composed_values}**", ""])
    lines.extend(["## Where the traversal stopped", ""])
    if report.truncations_by_reason:
        lines.extend(
            [
                "Never summed into one figure. Each reason answers a different question.",
                "",
                "| reason | occurrences |",
                "|---|---:|",
            ]
        )
        lines.extend(f"| `{reason}` | {count} |" for reason, count in report.truncations_by_reason)
        lines.append("")
    else:
        lines.extend(["Nowhere: the traversal ran to exhaustion within its bounds.", ""])
    if report.consequences_by_type:
        lines.extend(["## Consequences by type", "", "| type | count |", "|---|---:|"])
        lines.extend(f"| `{name}` | {count} |" for name, count in report.consequences_by_type)
        lines.append("")
    return "\n".join(lines)
