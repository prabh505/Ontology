"""The Candidate Graph Report: what each generator proposed, and what the gate refused.

A first-class output, matching the `DataQualityReport` / `EventQualityReport` /
`TimelineQualityReport` precedent. It exists because of one specific failure mode the task
this module was built for names outright: **a generator producing everything or nothing is
broken, and the report should make that obvious.** A silent generator and a runaway one both
look fine from the candidate count alone; they only look wrong beside the other six.

THREE DISTINCTIONS THE REPORT REFUSES TO COLLAPSE
-------------------------------------------------
1. `NOT_RUNNABLE` vs. zero. A generator whose declared parameter is absent did not run.
   Reporting it as `0 candidates` is the failure `ontology_runtime`'s third severity exists
   to prevent, and it is the failure OQ-014 and DEF-0001 are both instances of.
2. `UNDETERMINED` vs. `temporally_unverifiable`. The data placed both events and could not
   separate them, versus the data never placed one of them. Both block promotion; they are
   different findings about the dataset and are never summed.
3. Truncated vs. rejected. A candidate dropped by the cap was admissible and is reported
   as lost to a bound; a rejected one was never admissible. Merging them would make the cap
   look like a data-quality problem.

NOTHING HERE IS A JUDGEMENT
---------------------------
Every number is a count, a ratio of counts, or a bound. `looks_degenerate` is the one
derived flag, and it is derived from *coverage of the pair space*, not from whether the
candidates seem plausible -- it fires on a generator that proposed nothing while others
proposed, or one that proposed over essentially every sequenced pair available to it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.causal_engine.candidate_cause_generator.confounding import (
    CONFOUNDING_UNRESOLVED_NOTICE,
    ConfoundingFlag,
)
from causalog.causal_engine.candidate_cause_generator.context import GeneratorStatus
from causalog.causal_engine.candidate_cause_generator.gate import RejectionTally
from causalog.causal_engine.candidate_cause_generator.graph import TruncationRecord
from causalog.core.identifiers import format_float
from causalog.core.run import OutputEnvelope

__all__ = [
    "CANDIDATE_GRAPH_SCHEMA_VERSION",
    "SATURATION_SHARE",
    "CandidateGraphReport",
    "GeneratorTally",
    "PerEffectDistribution",
    "render_markdown",
]

#: This report's own shape. It does NOT participate in `run_id`: the report describes a
#: run, it is not an input to one (`CONTEXT.md` §7).
CANDIDATE_GRAPH_SCHEMA_VERSION = "1.1.0"

#: The share of available sequenced pairs above which a generator is called saturated. A
#: generator proposing over ninety per cent of everything it could see is not discriminating
#: between pairs, which makes its evidence worth nothing to module 10 -- it would contribute
#: a component that is present on almost every edge. This is an engine-level diagnostic
#: threshold on the module's OWN behaviour, not a domain policy about the data, which is why
#: it lives here and not in the pack.
SATURATION_SHARE = 0.9

#: How many truncation rows the MARKDOWN rendering prints. The report VALUE carries every
#: record and the JSON beside it holds them all; this bounds only what a human is asked to
#: scroll. The rendering states how many it elided and their total, so the cut is visible --
#: an unstated "top 40" reads as "there were 40", which is the same silent-truncation defect
#: the per-effect cap exists to report rather than commit.
RENDERED_TRUNCATION_ROWS = 40

#: Effects printed in the per-effect rejection table, worst first. The population is
#: every effect the run refused anything for, which on the reference slice is most of
#: them; the table is a way in, and the complete counts stay on the graph.
RENDERED_REJECTION_ROWS = 40

#: How many confounding flags the REPORT carries. The full set stays on
#: `GenerationResult.confounding_flags` for module 10, which needs all of them; the report is
#: a document, and a document carrying 68,580 flags is one nobody opens -- measured, on a
#: 150-row slice of the reference dataset. `confounding_flag_total` carries the real count
#: beside the sample, so the bound is stated rather than mistaken for the total.
SAMPLED_CONFOUNDING_FLAGS = 50


class GeneratorTally(BaseModel):
    """One generator's whole story: did it run, what did it propose, what was refused.

    `proposed_count` is what the generator emitted; `admitted_count` is what survived the
    gate; `retained_count` is what survived the cap as well. Three numbers rather than one,
    because the difference between them is the diagnostic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generator_id: str
    status: GeneratorStatus
    #: Populated only when `status` is `NOT_RUNNABLE`: what the pack or caller must supply.
    requirement: str | None = None
    proposed_count: int = 0
    #: Proposals folded into another making the IDENTICAL claim -- same pair, same generator,
    #: same payload -- with their evidence attached to it. Reported rather than absorbed, so
    #: `proposed == merged + admitted + rejected` holds and a reader can see that a rule-heavy
    #: pack produced many justifications for few hypotheses rather than many hypotheses.
    merged_count: int = 0
    admitted_count: int = 0
    retained_count: int = 0
    rejections: RejectionTally = RejectionTally()
    #: Sequenced event pairs this generator could in principle have proposed over, given
    #: timelines it was handed. The denominator `looks_degenerate` reads.
    available_pair_count: int = 0

    @property
    def looks_degenerate(self) -> bool:
        """Return whether this generator's output is suspicious on its face.

        True when it ran and proposed nothing, or when it ran and proposed over at least
        `SATURATION_SHARE` of the pairs available to it. Both are the shape of a defect
        rather than a finding, and both are invisible without the comparison.

        A `NOT_RUNNABLE` generator is never degenerate: it did not run, so there is nothing
        to call broken.
        """
        if self.status is not GeneratorStatus.RAN:
            return False
        if self.proposed_count == 0:
            return True
        if self.available_pair_count == 0:
            return False
        return self.proposed_count >= SATURATION_SHARE * self.available_pair_count

    @property
    def degeneracy_note(self) -> str | None:
        """Return why this generator looks degenerate, or None if it does not."""
        if not self.looks_degenerate:
            return None
        if self.proposed_count == 0:
            return (
                "ran and proposed nothing while other generators proposed. Either its "
                "declared parameters admit no pair in this data, or it has a pairing defect."
            )
        return (
            f"proposed over {self.proposed_count} of {self.available_pair_count} available "
            "sequenced pairs. A generator that proposes over almost everything is not "
            "discriminating between pairs, and its evidence would appear on nearly every "
            "edge module 10 scores."
        )


class PerEffectDistribution(BaseModel):
    """How candidates are spread across effect events.

    Bucketed rather than listed. The list is `CandidateGraph.candidates_per_effect()` and
    is available to anyone who wants it; what a reader needs from a report is the shape,
    and specifically whether a handful of effects hold most of the graph.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    effects_with_candidates: int
    minimum: int
    median: int
    maximum: int
    #: (upper bound inclusive, number of effects at or below it and above the previous
    #: bound), in ascending sequence. The final bucket's bound is the observed maximum.
    histogram: tuple[tuple[int, int], ...]

    @classmethod
    def of(cls, per_effect: tuple[tuple[str, int], ...]) -> PerEffectDistribution:
        """Return the distribution over one graph's per-effect counts."""
        if not per_effect:
            return cls(effects_with_candidates=0, minimum=0, median=0, maximum=0, histogram=())
        counts = sorted(count for _, count in per_effect)
        middle = len(counts) // 2
        median = (
            counts[middle] if len(counts) % 2 == 1 else (counts[middle - 1] + counts[middle]) // 2
        )
        bounds = [1, 2, 5, 10, 20, 50]
        top = counts[-1]
        if top > bounds[-1]:
            bounds.append(top)
        buckets: list[tuple[int, int]] = []
        previous = 0
        for bound in bounds:
            if previous >= top:
                break
            buckets.append((bound, sum(1 for count in counts if previous < count <= bound)))
            previous = bound
        return cls(
            effects_with_candidates=len(counts),
            minimum=counts[0],
            median=median,
            maximum=top,
            histogram=tuple(buckets),
        )


class CandidateGraphReport(BaseModel):
    """Everything one generation produced, as data rather than as a log."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = CANDIDATE_GRAPH_SCHEMA_VERSION
    envelope: OutputEnvelope
    events_examined: int
    timelines_examined: int
    generators: tuple[GeneratorTally, ...] = Field(min_length=1)
    retained_count: int
    undetermined_count: int
    unverifiable_count: int
    promotable_count: int
    distribution: PerEffectDistribution
    truncations: tuple[TruncationRecord, ...]
    #: `(effect_event_id, rejection count)` over every rejection that named an effect,
    #: COMPLETE and sorted. The tail is elided when rendered, never when counted.
    rejections_per_effect: tuple[tuple[str, int], ...] = ()
    #: Rejections that named an effect. Excludes `GENERATOR_NOT_RUNNABLE`, which names none.
    rejection_total: int = 0
    #: A bounded SAMPLE, in canonical sequence. `confounding_flag_total` and
    #: `confounding_flags_by_structure` carry the real counts; the full set lives on
    #: `GenerationResult.confounding_flags`.
    confounding_flags: tuple[ConfoundingFlag, ...]
    confounding_flag_total: int = 0
    #: (structure, count) over EVERY flag, not only the sampled ones. Sorted by structure.
    confounding_flags_by_structure: tuple[tuple[str, int], ...] = ()

    @property
    def total_rejections(self) -> RejectionTally:
        """Return every generator's rejections, summed element-wise."""
        total = RejectionTally()
        for tally in self.generators:
            total = total.plus(tally.rejections)
        return total

    @property
    def degenerate_generators(self) -> tuple[GeneratorTally, ...]:
        """Return every generator whose output is suspicious on its face."""
        return tuple(tally for tally in self.generators if tally.looks_degenerate)

    @property
    def not_runnable_generators(self) -> tuple[GeneratorTally, ...]:
        """Return every generator that could not run for want of a declaration."""
        return tuple(
            tally for tally in self.generators if tally.status is GeneratorStatus.NOT_RUNNABLE
        )

    def undetermined_share(self) -> float:
        """Return the `UNDETERMINED` share of retained candidates, or 0.0 if empty.

        Reported rather than acted on. `CONTEXT.md` R-14 predicts this may dominate on a
        day-granular source and states that a dominant value is a finding about the
        dataset, never something to tune away by loosening the test.
        """
        if self.retained_count == 0:
            return 0.0
        return self.undetermined_count / self.retained_count

    def flag_density(self) -> float:
        """Return confounding flags per retained candidate, or 0.0 over an empty graph."""
        if self.retained_count == 0:
            return 0.0
        return self.confounding_flag_total / self.retained_count

    def unverifiable_share(self) -> float:
        """Return the temporally unverifiable share of retained candidates."""
        if self.retained_count == 0:
            return 0.0
        return self.unverifiable_count / self.retained_count


def render_markdown(report: CandidateGraphReport) -> str:
    """Return the report as Markdown, for `docs/reports/<dataset>/candidate-graph.md`.

    Sequenced so the two things most likely to be wrong come first: generators that could
    not run, and generators whose output is degenerate. A reader who stops after the first
    screen has seen the findings rather than the totals.
    """
    lines: list[str] = [
        "# Candidate Graph Report",
        "",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- events examined: {report.events_examined}",
        f"- process instances (timelines) examined: {report.timelines_examined}",
        f"- candidates retained: {report.retained_count}",
        "",
        "This module proposes hypotheses. It assigns no confidence, performs no ranking,",
        "and prunes nothing on plausibility. Every number below is a count.",
        "",
    ]

    not_runnable = report.not_runnable_generators
    lines.append("## Generators that could not run")
    lines.append("")
    if not not_runnable:
        lines.append("None. Every generator had what it needed.")
    else:
        lines.append("These did **not** run. That is not the same as running and finding nothing,")
        lines.append("and it is reported separately for exactly that reason.")
        lines.append("")
        for tally in not_runnable:
            lines.append(f"- **`{tally.generator_id}`** needs: {tally.requirement}")
    lines.append("")

    degenerate = report.degenerate_generators
    lines.append("## Generators whose output looks degenerate")
    lines.append("")
    if not degenerate:
        lines.append("None. Every generator that ran proposed something, and none saturated.")
    else:
        for tally in degenerate:
            lines.append(f"- **`{tally.generator_id}`** {tally.degeneracy_note}")
    lines.append("")

    lines.extend(
        [
            "## Candidates by generator",
            "",
            "| generator | status | proposed | merged | admitted | retained | " "available pairs |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for tally in report.generators:
        lines.append(
            f"| `{tally.generator_id}` | {tally.status.value} | {tally.proposed_count} | "
            f"{tally.merged_count} | {tally.admitted_count} | {tally.retained_count} | "
            f"{tally.available_pair_count} |"
        )
    lines.extend(
        [
            "",
            "`merged` counts proposals folded into another making the identical claim -- same",
            "pair, same generator, same payload -- with their evidence carried across. A large",
            "value means the pack justifies few hypotheses many ways, not that candidates were",
            "lost: `proposed == merged + admitted + rejected`.",
            "",
        ]
    )

    lines.extend(
        [
            "## Rejections per effect event",
            "",
        ]
    )
    if not report.rejections_per_effect:
        lines.append(
            "No claim was refused for any effect event in this run. On a graph of any size "
            "that is unusual rather than good: it means no proposal violated precedence, "
            "none was prohibited, and no effect reached the cap."
        )
        lines.append("")
    else:
        ranked = sorted(report.rejections_per_effect, key=lambda row: (-row[1], row[0]))
        worst = ranked[:RENDERED_REJECTION_ROWS]
        lines.append(
            f"**{report.rejection_total:,} claim(s) were refused across "
            f"{len(report.rejections_per_effect):,} effect event(s)**, worst first. Each "
            "row is one outcome nothing was kept against, or was nearly not kept against. "
            "Read it beside the retained counts above: an effect near the top of this table "
            "and absent from the graph was not overlooked, it was considered and refused, "
            "and the reasons are on the graph's own rejection records."
        )
        lines.append("")
        lines.append("| effect | claims refused |")
        lines.append("|---|---:|")
        for effect_id, count in worst:
            lines.append(f"| `{effect_id}` | {count} |")
        lines.append("")
        if len(ranked) > len(worst):
            unprinted = ranked[len(worst) :]
            lines.append(
                f"{len(unprinted):,} further effect(s) are not printed here, accounting for "
                f"{sum(count for _effect, count in unprinted):,} more refusal(s). The counts "
                "above are complete; only this rendering is bounded."
            )
            lines.append("")
        lines.append(
            "A refusal is not a judgement about the outcome. Three of the reasons are "
            "properties of the DATA -- precedence that could not be established, a pair the "
            "pack prohibits -- and one, the per-effect cap, is a bound this run declared on "
            "itself. An effect whose refusals are mostly capped ones had more hypotheses "
            "than the cap admits, which is a different finding from one with none."
        )
        lines.append("")

    lines.extend(
        [
            "## Rejections by reason",
            "",
            "| generator | temporal violation | self edge | constraint | truncated by cap |"
            " not runnable |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for tally in report.generators:
        rejections = tally.rejections
        lines.append(
            f"| `{tally.generator_id}` | {rejections.temporal_violation} | "
            f"{rejections.self_edge} | {rejections.constraint_suppressed} | "
            f"{rejections.truncated_by_cap} | {rejections.generator_not_runnable} |"
        )
    total = report.total_rejections
    lines.append(
        f"| **total** | {total.temporal_violation} | {total.self_edge} | "
        f"{total.constraint_suppressed} | {total.truncated_by_cap} | "
        f"{total.generator_not_runnable} |"
    )
    lines.extend(
        [
            "",
            "A large `temporal violation` count is a finding about the declared windows.",
            "A large `constraint` count is a finding about the rule pack.",
            "",
        ]
    )

    distribution = report.distribution
    lines.extend(
        [
            "## Candidates per effect event",
            "",
            f"- effects holding at least one candidate: {distribution.effects_with_candidates}",
            f"- minimum: {distribution.minimum} · median: {distribution.median} · "
            f"maximum: {distribution.maximum}",
            "",
            "| candidates per effect (up to) | effects |",
            "|---:|---:|",
        ]
    )
    for bound, count in distribution.histogram:
        lines.append(f"| {bound} | {count} |")
    lines.append("")

    lines.extend(
        [
            "## Temporal standing",
            "",
            "Two counts, never summed. They are different findings about the dataset",
            "(`docs/contracts.md` §3).",
            "",
            f"- **`UNDETERMINED`**: {report.undetermined_count} "
            f"({format_float(report.undetermined_share())} of retained). The data placed "
            "both events and could not separate them.",
            f"- **temporally unverifiable**: {report.unverifiable_count} "
            f"({format_float(report.unverifiable_share())} of retained). The data never "
            "placed one of them.",
            f"- **promotable to `INFERRED`**: {report.promotable_count}. Neither of the "
            "above; LAW-TIME does not block promotion. Whether any of them IS promoted is "
            "module 10's decision, not this module's.",
            "",
            "A dominant `UNDETERMINED` share is a finding about the source's granularity",
            "(`CONTEXT.md` R-14). It is never resolved by loosening the test.",
            "",
        ]
    )

    lines.append("## Truncation")
    lines.append("")
    if not report.truncations:
        lines.append("No effect event exceeded the declared per-effect cap.")
    else:
        dropped = sum(record.dropped_count for record in report.truncations)
        lines.append(
            f"{len(report.truncations)} effect event(s) exceeded the cap; {dropped} "
            "candidate(s) were truncated. Selection is round-robin across generators in "
            "canonical sequence -- fair allocation, never a plausibility ranking."
        )
        lines.append("")
        shown = report.truncations[:RENDERED_TRUNCATION_ROWS]
        elided = report.truncations[RENDERED_TRUNCATION_ROWS:]
        lines.append("")
        lines.append("| effect | cap | proposed | retained | dropped by generator |")
        lines.append("|---|---:|---:|---:|---|")
        for record in shown:
            dropped_text = ", ".join(
                f"`{generator_id}`: {count}" for generator_id, count in record.dropped_by_generator
            )
            lines.append(
                f"| `{record.effect_event_id}` | {record.cap} | {record.proposed_count} | "
                f"{record.retained_count} | {dropped_text} |"
            )
        if elided:
            lines.append("")
            lines.append(
                f"{len(elided)} further truncated effect(s) are not printed here, losing "
                f"{sum(record.dropped_count for record in elided)} candidate(s) between them. "
                "**They are not omitted from the report** -- `candidate-graph.json` beside "
                "this file carries every record. Only the rendering is bounded, and it says "
                "so, because an unstated cut reads as a complete list."
            )
    lines.append("")

    lines.append("## Confounding structures made visible")
    lines.append("")
    if not report.confounding_flag_total:
        lines.append(
            "No mediation or common-cause triangle appears in the candidate graph. "
            "**This is not a finding of no confounding.** An unobserved common cause "
            "leaves no shape in a graph built from observed events (prd.md §59, "
            "`CONTEXT.md` R-05)."
        )
    else:
        for structure, count in report.confounding_flags_by_structure:
            lines.append(f"- `{structure}`: {count}")
        lines.append(f"- **total**: {report.confounding_flag_total}")
        lines.append("")
        lines.append(CONFOUNDING_UNRESOLVED_NOTICE)
        lines.append("")
        if report.flag_density() >= 1.0:
            lines.append(
                f"**Density note.** There are {report.flag_density():.2f} flags per retained "
                "candidate. At that rate nearly every candidate sits in some triangle, and a "
                "flag stops distinguishing anything -- it is a property of a dense graph "
                "rather than a finding about particular claims. Read it as a statement about "
                "this graph's shape, and expect the per-effect cap and the pack's declared "
                "windows to govern it more than the data does."
            )
            lines.append("")
        if len(report.confounding_flags) < report.confounding_flag_total:
            lines.append(
                f"The report carries {len(report.confounding_flags)} flag(s) as a sample; "
                f"all {report.confounding_flag_total} are returned on "
                "`GenerationResult.confounding_flags` for module 10. The bound is on this "
                "document, not on the detection."
            )
    lines.append("")
    return "\n".join(lines)
