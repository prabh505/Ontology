"""The Timeline Quality Report: what a run's timelines contain, and how they deviate.

A first-class output, matching the `EventQualityReport`/`ReconciliationReport` precedent
from modules 3/4 (`docs/architecture.md`). Conformance and deviation are properties of
*this module's own responsibility* -- comparing an observed sequence to the pack's declared
`canonical_sequence` -- computed the same way `ProcessCoverage` already is in the Event
Generator: structural bookkeeping against a pack-declared sequence, not domain-metric
arithmetic (`scripts/check_metrics_are_declared.py` scopes the latter, not the former).

Nothing here corrects anything. A deviation is reported, never resorted into a shape that
looks conformant (`CONTEXT.md`: "deviation is signal").
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.run import OutputEnvelope

__all__ = [
    "TIMELINE_QUALITY_SCHEMA_VERSION",
    "ProcessDefinitionConformance",
    "SequenceViolation",
    "SequenceViolationKind",
    "TimelineQualityReport",
    "render_markdown",
]

#: This report's own shape. It does NOT participate in `run_id`: the report describes a
#: run, it is not an input to one (`CONTEXT.md` §7).
TIMELINE_QUALITY_SCHEMA_VERSION = "1.0.0"


class SequenceViolationKind(str, Enum):
    """How an adjacent pair of events departed from the declared canonical sequence."""

    OUT_OF_SEQUENCE = "OUT_OF_SEQUENCE"
    """Both event types belong to the canonical sequence; they appeared reversed."""

    IMPOSSIBLE = "IMPOSSIBLE"
    """At least one event type is not part of the process definition's declared vocabulary
    at all -- a stronger anomaly than a reordering of known steps."""


class SequenceViolation(BaseModel):
    """One adjacent pair of events that departed from the declared canonical sequence.

    Never corrected. The instance's timeline keeps the observed sequence; this is the finding
    that records the departure was observed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SequenceViolationKind
    process_definition_id: str
    anchor_entity_id: str
    earlier_event_id: str
    earlier_event_type: str
    later_event_id: str
    later_event_type: str


class ProcessDefinitionConformance(BaseModel):
    """One process definition's conformance statistics across every instance it grouped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    process_definition_id: str
    instances: int = Field(ge=0)
    """Distinct anchor entities grouped under this definition."""
    required_steps: int = Field(ge=0)
    """`canonical_sequence` steps not in `optional_steps`."""
    gap_witnessable: int = Field(ge=0)
    """Required-step gaps where the event type IS produced elsewhere in this run -- missing
    on this instance specifically."""
    gap_unwitnessable: int = Field(ge=0)
    """Required-step gaps where the event type is produced NOWHERE in this run's event
    set -- no record could ever have witnessed it (mirrors `ProcessCoverage`'s two tiers)."""
    sequence_violations: int = Field(ge=0)
    unterminated_instances: int = Field(ge=0)
    """Instances that never reached the last required step and have no later event."""
    conformance_scores: tuple[float, ...] = ()
    """One score per instance: matched required steps / total required steps. A process
    definition declaring zero required steps is never scored (division by zero is not
    silently defaulted to 1.0 or 0.0 -- it is simply not asked)."""

    @property
    def mean_conformance(self) -> float | None:
        """Return the dataset-wide mean conformance score, or `None` if none were scored."""
        if not self.conformance_scores:
            return None
        return sum(self.conformance_scores) / len(self.conformance_scores)


class TimelineQualityReport(BaseModel):
    """Every statement one timeline-building run makes about the timelines it produced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = TIMELINE_QUALITY_SCHEMA_VERSION
    envelope: OutputEnvelope
    events_read: int = Field(ge=0)
    timelines_built: int = Field(ge=0)
    entity_view_timelines: int = Field(ge=0)
    process_instance_timelines: int = Field(ge=0)
    uncertain_sequence_timelines: int = Field(ge=0)
    """Timelines containing at least one adjacency whose `sequence_provenance` is
    `ASSUMED` -- internal sequencing that could not be verified from the data."""
    per_process_definition: tuple[ProcessDefinitionConformance, ...] = ()
    violations: tuple[SequenceViolation, ...] = ()
    not_checked: tuple[str, ...] = ()

    @property
    def sequence_violations_total(self) -> int:
        """Return the count of `violations` -- a convenience, `violations` stays authoritative."""
        return len(self.violations)


def render_markdown(report: TimelineQualityReport) -> str:
    """Render the report as committed markdown, deterministically.

    No wall clock, no host name, no absolute path -- the file is compared byte-for-byte by
    the determinism test.
    """
    lines = [
        "# Timeline Quality Report",
        "",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- `dataset_version`: `{report.envelope.dataset_version}`",
        f"- `ontology_hash`: `{report.envelope.ontology_hash}`",
        f"- `engine_version`: `{report.envelope.engine_version}`",
        "",
        "## Summary",
        "",
        f"Events read: **{report.events_read:,}**. Timelines built: "
        f"**{report.timelines_built:,}** ({report.process_instance_timelines:,} "
        f"process-instance, {report.entity_view_timelines:,} entity). Timelines with at "
        f"least one internally-unverifiable adjacency: "
        f"**{report.uncertain_sequence_timelines:,}**.",
        "",
        "## Process definition conformance",
        "",
        "| Process definition | Instances | Required steps | Gaps (witnessable) | "
        "Gaps (unwitnessable) | Sequence violations | Unterminated | Mean conformance |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report.per_process_definition:
        mean = "n/a" if item.mean_conformance is None else f"{item.mean_conformance:.3f}"
        lines.append(
            f"| `{item.process_definition_id}` | {item.instances:,} | "
            f"{item.required_steps:,} | {item.gap_witnessable:,} | "
            f"{item.gap_unwitnessable:,} | {item.sequence_violations:,} | "
            f"{item.unterminated_instances:,} | {mean} |"
        )
    lines.extend(["", "## Sequence violations", ""])
    if not report.violations:
        lines.append("No adjacent pair departed from any declared canonical sequence.")
    else:
        lines.append(
            f"**{report.sequence_violations_total:,}** violation(s), never corrected -- the "
            "observed sequence is kept and the departure is recorded here instead."
        )
        lines.append("")
        for violation in report.violations:
            lines.append(
                f"- `{violation.kind.value}` in `{violation.process_definition_id}` "
                f"(anchor `{violation.anchor_entity_id}`): `{violation.earlier_event_type}` "
                f"(`{violation.earlier_event_id}`) precedes "
                f"`{violation.later_event_type}` (`{violation.later_event_id}`)"
            )
    lines.extend(["", "## What this run did NOT check", ""])
    lines.extend(f"- {item}" for item in report.not_checked)
    return "\n".join(lines) + "\n"
