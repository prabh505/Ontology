"""`StructuralPatternReport` -- what recurs across a run, and what did not get looked for.

The first section is what the report does not contain, as every report in this engine
begins. Here it carries the finding a reader of a pattern report is most likely to get wrong:
**an empty pattern list is not a finding that there are no patterns.** It may mean the pack
declared no support threshold, in which case nothing was looked for; or that the threshold
was not reached, in which case something was. Those are different, and the report separates
them by carrying a stated reason with every absence rather than an empty list on its own.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.propagation_analyzer.view import (
    DIAGNOSTIC_NOT_STATED_NOTICE,
    GraphStanding,
)
from causalog.core.errors import ContractViolationError
from causalog.core.run import OutputEnvelope

__all__ = [
    "PATTERN_REPORT_SCHEMA_VERSION",
    "Bottleneck",
    "Motif",
    "StructuralPatternReport",
    "build_report",
    "render_markdown",
]

PATTERN_REPORT_SCHEMA_VERSION = "1.0.0"

#: The most rows rendered into the markdown. The JSON carries every one.
RENDERED_ROWS = 30


class Motif(BaseModel):
    """One recurring type-level shape, with the span that says whether it is systemic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cause_event_type: str = Field(min_length=1)
    effect_event_type: str = Field(min_length=1)
    occurrences: int = Field(ge=1)
    #: How many distinct process instances the occurrences span. Reported BESIDE the count
    #: and never folded into it: one shape repeating inside one instance is a local
    #: pathology and the same count across many instances is systemic.
    instance_span: int = Field(ge=0)
    minimum_support: int = Field(ge=1)
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[int, str, str]:
        """Return the canonical sequence key: most frequent first, then by type names."""
        return (-self.occurrences, self.cause_event_type, self.effect_event_type)


class Bottleneck(BaseModel):
    """One chronically busy type, with its two degrees kept apart."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: str = Field(min_length=1)
    #: How many distinct types are claimed to cause this one. Never summed with `out_degree`.
    in_degree: int = Field(ge=0)
    #: How many distinct types this one is claimed to cause.
    out_degree: int = Field(ge=0)
    claims_touching: int = Field(ge=0)
    minimum_degree: int = Field(ge=1)
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[int, str]:
        """Return the canonical sequence key: busiest first, then by type name."""
        return (-max(self.in_degree, self.out_degree), self.event_type)


class StructuralPatternReport(BaseModel):
    """What recurs across one run, and the account of what was not looked for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = PATTERN_REPORT_SCHEMA_VERSION
    envelope: OutputEnvelope
    standing: GraphStanding
    motifs: tuple[Motif, ...] = ()
    #: Non-None exactly when `motifs` is empty. An empty list on its own would be read as a
    #: finding that there are no patterns, and it may instead mean nothing was looked for.
    motifs_absent_because: str | None = None
    bottlenecks: tuple[Bottleneck, ...] = ()
    bottlenecks_absent_because: str | None = None
    #: How many distinct type-level shapes existed to examine. The denominator behind every
    #: figure above, without which "three motifs" cannot be read.
    shapes_examined: int = Field(ge=0)
    links_examined: int = Field(ge=0)
    #: The longest motif this version actually enumerates, stated so nobody infers that
    #: longer ones were searched for and not found.
    maximum_motif_length_enumerated: int = Field(ge=2)
    declared_motif_maximum_length: int | None = None
    diagnostic: bool = False

    @property
    def notice(self) -> str | None:
        """Return the disowning notice for a diagnostic report, or None for a stated one."""
        if self.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC:
            return DIAGNOSTIC_NOT_STATED_NOTICE
        return None

    @model_validator(mode="after")
    def _check_absences(self) -> StructuralPatternReport:
        """Refuse an empty finding with no stated reason, in either section."""
        for values, reason, name in (
            (self.motifs, self.motifs_absent_because, "motifs"),
            (self.bottlenecks, self.bottlenecks_absent_because, "bottlenecks"),
        ):
            if not values and reason is None:
                raise ContractViolationError(
                    f"StructuralPatternReport.{name} is empty with no stated reason. An "
                    "empty list reads as 'there are none'; it may instead mean nothing was "
                    "looked for, and the two are different findings."
                )
            if values and reason is not None:
                raise ContractViolationError(
                    f"StructuralPatternReport.{name} carries both results and a reason for "
                    "having none. One of the two is wrong and a reader cannot tell which."
                )
        return self


def build_report(
    *,
    envelope: OutputEnvelope,
    standing: GraphStanding,
    motifs: tuple[Motif, ...],
    motifs_absent_because: str | None,
    bottlenecks: tuple[Bottleneck, ...],
    bottlenecks_absent_because: str | None,
    shapes_examined: int,
    links_examined: int,
    maximum_motif_length_enumerated: int,
    declared_motif_maximum_length: int | None,
    diagnostic: bool,
) -> StructuralPatternReport:
    """Assemble the report. Keyword-only, because ten positional arguments is a trap."""
    return StructuralPatternReport(
        envelope=envelope,
        standing=standing,
        motifs=motifs,
        motifs_absent_because=motifs_absent_because,
        bottlenecks=bottlenecks,
        bottlenecks_absent_because=bottlenecks_absent_because,
        shapes_examined=shapes_examined,
        links_examined=links_examined,
        maximum_motif_length_enumerated=maximum_motif_length_enumerated,
        declared_motif_maximum_length=declared_motif_maximum_length,
        diagnostic=diagnostic,
    )


def render_markdown(report: StructuralPatternReport) -> str:
    """Render the report as markdown. Returns a string; writing it belongs in `scripts/`."""
    lines: list[str] = [
        "# Structural Pattern Report",
        "",
        "For the reader who wants the shape of the run rather than one incident "
        "(prd.md §10, Executive Leadership).",
        "",
        f"- standing: `{report.standing.value}`",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        f"- links examined: {report.links_examined}",
        f"- distinct type-level shapes examined: {report.shapes_examined}",
        "",
    ]
    if report.notice is not None:
        lines.extend([f"> **{report.notice}**", ""])
    lines.extend(
        [
            "## What this report does not contain",
            "",
            "**An empty list below is not a finding that there are no patterns.** It may "
            "mean the pack declared no threshold, in which case nothing was looked for; or "
            "that the threshold was not reached, in which case something was. Every empty "
            "section carries a sentence saying which.",
            "",
            f"Motifs are enumerated to length "
            f"**{report.maximum_motif_length_enumerated}** at this version"
            + (
                f", against a declared `motif_maximum_length` of "
                f"{report.declared_motif_maximum_length}"
                if report.declared_motif_maximum_length is not None
                else ", and the pack declares no `motif_maximum_length`"
            )
            + ". Longer shapes were not searched for, so their absence here is not evidence "
            "of their absence in the run.",
            "",
            "Everything below is measured over the **event-type projection**, never over "
            "event instances. A claim about instances is unique by construction, so a "
            "recurrence counter running at that level could only ever return one. The cost "
            "of that choice is stated rather than hidden: a shape reported here may be "
            "carried by a single instance repeating, which is why every row carries the "
            "number of process instances it spans beside its raw count.",
            "",
            "## Recurring motifs",
            "",
        ]
    )
    if report.motifs_absent_because is not None:
        lines.extend([f"**None reported.** {report.motifs_absent_because}", ""])
    else:
        lines.extend(
            [
                "| cause type | effect type | claims | instances spanned | support floor |",
                "|---|---|---:|---:|---:|",
            ]
        )
        lines.extend(
            f"| `{motif.cause_event_type}` | `{motif.effect_event_type}` | "
            f"{motif.occurrences} | {motif.instance_span} | {motif.minimum_support} |"
            for motif in report.motifs[:RENDERED_ROWS]
        )
        if len(report.motifs) > RENDERED_ROWS:
            lines.append(
                f"| ... | {len(report.motifs) - RENDERED_ROWS} further row(s) in the JSON "
                "artifact | | | |"
            )
        lines.append("")
    lines.extend(["## Chronic bottlenecks", ""])
    if report.bottlenecks_absent_because is not None:
        lines.extend([f"**None reported.** {report.bottlenecks_absent_because}", ""])
    else:
        lines.extend(
            [
                "In-degree and out-degree are separate columns and are never summed. A type "
                "consequence collects at and a type consequence originates from are "
                "different structures needing different responses.",
                "",
                "| type | caused by (types) | causes (types) | claims touching | floor |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        lines.extend(
            f"| `{item.event_type}` | {item.in_degree} | {item.out_degree} | "
            f"{item.claims_touching} | {item.minimum_degree} |"
            for item in report.bottlenecks[:RENDERED_ROWS]
        )
        if len(report.bottlenecks) > RENDERED_ROWS:
            lines.append(
                f"| ... | {len(report.bottlenecks) - RENDERED_ROWS} further row(s) in the "
                "JSON artifact | | | |"
            )
        lines.append("")
    return "\n".join(lines)
