"""The Event Quality Report: what the reconstructed event log has, and what it does not.

A first-class output, and the one this module exists to make possible. The causal
engine's honesty depends on knowing what it does not have: a graph built on an event log
whose gaps are unmeasured looks exactly like a graph built on a complete one, and the
difference only surfaces as a confident wrong answer.

Everything here is a count from the run that produced it. There is no target, no threshold
and no grade -- a report that scored itself would invite tuning the score.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.run import OutputEnvelope
from causalog.extraction.event_generator.coverage import ProcessCoverage

__all__ = [
    "EVENT_QUALITY_SCHEMA_VERSION",
    "EventQualityReport",
    "EventTypeTally",
    "render_markdown",
]

#: This report's own shape. It does NOT participate in `run_id`: the report describes a run,
#: it is not an input to one (`CONTEXT.md` §7).
EVENT_QUALITY_SCHEMA_VERSION = "1.0.0"


class EventTypeTally(BaseModel):
    """What one event type produced, and what stopped it producing more."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: str
    observation_mode: str
    provenance_class: str
    has_emission_rule: bool
    events: int = Field(ge=0)
    """Distinct OCCURRENCES materialised. One event per occurrence, however many records
    witnessed it."""
    records_witnessing: int = Field(ge=0)
    """Record-level firings. Larger than `events` exactly where several records corroborate
    one occurrence, and the ratio between the two is the source's line-item fan-out."""
    suppressed_missing_participant: int = Field(ge=0)
    orphaned: int = Field(ge=0)

    @property
    def corroboration_ratio(self) -> float:
        """Return records per occurrence, or zero when nothing fired."""
        if not self.events:
            return 0.0
        return self.records_witnessing / self.events


class EventQualityReport(BaseModel):
    """Every statement one generation run makes about the event log it produced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = EVENT_QUALITY_SCHEMA_VERSION
    envelope: OutputEnvelope
    missing_event_policy: str
    conflict_policy: str
    """Module 3's policy, carried here because the events name the entities it resolved. A
    consumer holding this report alone must be able to tell how identity was settled."""

    records_read: int = Field(ge=0)
    events_total: int = Field(ge=0)
    gap_markers_emitted: int = Field(ge=0)

    by_event_type: tuple[EventTypeTally, ...] = ()
    by_provenance_class: tuple[tuple[str, int], ...] = ()
    by_precision: tuple[tuple[str, int], ...] = ()
    by_timestamp_kind: tuple[tuple[str, int], ...] = ()
    orphan_events: int = Field(ge=0)
    unevaluable_conditions: tuple[tuple[str, str, int], ...] = ()
    """`(event_type, address, count)`: comparisons that read a value the record did not
    supply. A rule that never fires with a large count here has a coverage problem; one with
    a zero count has a condition the dataset genuinely never met."""

    process_coverage: tuple[ProcessCoverage, ...] = ()
    event_types_never_emitted: tuple[str, ...] = ()
    not_checked: tuple[str, ...] = ()

    @property
    def observed_events(self) -> int:
        """Return the number of events whose occurrence a column recorded directly."""
        return dict(self.by_provenance_class).get("OBSERVED", 0)

    @property
    def unplaced_events(self) -> int:
        """Return the events carrying the unbounded UNKNOWN interval.

        These may sit on a timeline and may never participate in an `INFERRED` causal edge
        (`CONVENTIONS.md` §10). The number is therefore a direct bound on how much of the
        log the causal engine can reason over at all.
        """
        return dict(self.by_precision).get("UNKNOWN", 0)


def _table(rows: tuple[tuple[str, int], ...], total: int, label: str) -> list[str]:
    """Render a name/count table with a share column."""
    lines = [f"| {label} | Events | Share |", "|---|---:|---:|"]
    for name, count in rows:
        share = f"{count / total:.2%}" if total else "n/a"
        lines.append(f"| `{name}` | {count:,} | {share} |")
    return lines


def render_markdown(report: EventQualityReport) -> str:
    """Render the report as committed markdown, deterministically.

    No wall clock, no host name, no absolute path: the file is compared byte-for-byte by the
    determinism test, and anything ambient in it would make an identical run look changed.
    """
    total = report.events_total
    lines = [
        "# Event Quality Report",
        "",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- `dataset_version`: `{report.envelope.dataset_version}`",
        f"- `ontology_hash`: `{report.envelope.ontology_hash}`",
        f"- `engine_version`: `{report.envelope.engine_version}`",
        f"- missing-event policy: **{report.missing_event_policy}** (ADR-0040)",
        f"- identity conflict policy: **{report.conflict_policy}**",
        "",
        "## Totals",
        "",
        f"Records read: **{report.records_read:,}**. "
        f"Events: **{total:,}**. "
        f"Gap markers: **{report.gap_markers_emitted:,}**. "
        f"Orphan events: **{report.orphan_events:,}**.",
        "",
        "## By provenance class",
        "",
    ]
    lines.extend(_table(report.by_provenance_class, total, "Provenance"))
    lines.extend(
        [
            "",
            f"**{report.observed_events:,}** of {total:,} events have an occurrence a column "
            "recorded directly. Every other event is a reconstruction, and its provenance "
            "class says so; none of them may be read as an observation (LAW-PROVENANCE, "
            "ADR-0029).",
            "",
            "## By event type",
            "",
            "| Event type | Mode | Provenance | Rule | Events | Records | Records/event | "
            "No participant | Orphaned |",
            "|---|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for tally in report.by_event_type:
        lines.append(
            f"| `{tally.event_type}` | {tally.observation_mode} | {tally.provenance_class} | "
            f"{'yes' if tally.has_emission_rule else '**NO**'} | {tally.events:,} | "
            f"{tally.records_witnessing:,} | {tally.corroboration_ratio:.2f} | "
            f"{tally.suppressed_missing_participant:,} | {tally.orphaned:,} |"
        )
    lines.extend(["", "## Timestamp precision", ""])
    lines.extend(_table(report.by_precision, total, "Precision"))
    lines.extend(["", "### Timestamp kind", ""])
    lines.extend(_table(report.by_timestamp_kind, total, "Kind"))
    lines.extend(
        [
            "",
            f"**{report.unplaced_events:,}** events carry the unbounded UNKNOWN interval. "
            "Those events may sit on a timeline and may NEVER participate in an INFERRED "
            "causal edge (`CONVENTIONS.md` §10). An INFERRED interval never yields a CERTAIN "
            "verdict either (ADR-0021), so the count of OBSERVED-provenance intervals above "
            "is the ceiling on what LAW-TIME can certify.",
            "",
            "## Process coverage",
            "",
        ]
    )
    for coverage in report.process_coverage:
        lines.extend(
            [
                f"### `{coverage.process_id}` (anchor `{coverage.anchor_entity_type}`)",
                "",
                f"{coverage.anchors:,} instance(s). Measured against the declared sequence "
                "each instance best matches: "
                + ", ".join(f"`{name}` {count:,}" for name, count in coverage.anchors_by_sequence)
                + ".",
                "",
                "| Step | Attributable | Witnessable | Optional | Expecting | Missing | "
                "Miss rate |",
                "|---|---|---|---|---:|---:|---:|",
            ]
        )
        for step in coverage.steps:
            counts = (
                f"{step.anchors_expecting:,} | {step.anchors_missing:,} | " f"{step.miss_rate:.2%}"
                if step.attributable
                else "n/a | n/a | n/a"
            )
            lines.append(
                f"| `{step.event_type}` | {'yes' if step.attributable else '**NO**'} | "
                f"{'yes' if step.witnessable else '**NO**'} | "
                f"{'yes' if step.optional else 'no'} | {counts} |"
            )
        unwitnessable = coverage.unwitnessable_steps
        unattributable = coverage.unattributable_steps
        lines.append("")
        if unattributable:
            lines.append(
                "**NOT MEASURED against this anchor, and therefore NOT reported as missing:** "
                + ", ".join(f"`{name}`" for name in unattributable)
                + ". These event types name no participant of the anchor's type, so an event "
                "of one cannot be connected to an instance here. They may be firing on every "
                "instance or on none; this report cannot tell, and says so rather than "
                "printing a rate it did not count. Connecting them needs the structural "
                "relationship module 7 builds."
            )
            lines.append("")
        if unwitnessable:
            lines.append(
                "**Systematically absent from the dataset, not from these instances:** "
                + ", ".join(f"`{name}`" for name in unwitnessable)
                + ". No emission rule can produce them, so no instance of this process can "
                "ever carry them. This bounds every conclusion drawn about the steps around "
                "them."
            )
        else:
            lines.append("Every declared step of this process is witnessable from this dataset.")
        lines.append("")
    if report.event_types_never_emitted:
        lines.extend(
            [
                "## Event types that produced nothing",
                "",
                ", ".join(f"`{name}`" for name in report.event_types_never_emitted),
                "",
            ]
        )
    if report.unevaluable_conditions:
        lines.extend(
            [
                "## Conditions that could not be evaluated",
                "",
                "| Event type | Address | Records |",
                "|---|---|---:|",
            ]
        )
        lines.extend(
            f"| `{event_type}` | `{address}` | {count:,} |"
            for event_type, address, count in report.unevaluable_conditions
        )
        lines.append("")
    lines.extend(["## What this run did NOT check", ""])
    lines.extend(f"- {item}" for item in report.not_checked)
    return "\n".join(lines) + "\n"
