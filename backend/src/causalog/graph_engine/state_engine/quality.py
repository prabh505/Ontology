"""The State Quality Report: what state replay produced, and what it refused.

Same precedent as `TimelineQualityReport`/`EventQualityReport`/`ReconciliationReport`: a
first-class output, not a log line. An illegal transition is a hard-error *finding* here
(`docs/architecture.md` §Module 6) -- the individual instance's replay stops at the
offending event, but the run as a whole keeps going and the finding says exactly where and
why.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.run import OutputEnvelope

__all__ = [
    "STATE_QUALITY_SCHEMA_VERSION",
    "DurationStatistic",
    "IllegalTransitionFinding",
    "StateQualityReport",
    "render_markdown",
]

#: This report's own shape. It does NOT participate in `run_id` (`CONTEXT.md` §7).
STATE_QUALITY_SCHEMA_VERSION = "1.0.0"


class IllegalTransitionFinding(BaseModel):
    """One event that fired a transition the entity's lifecycle does not permit.

    Recorded, not corrected: replay for this entity stops here (no further state is
    derived past the offending event), and every other entity's replay is unaffected.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: str
    offending_event_id: str
    event_type: str
    attempted_from_state: str | None
    declared_from_states: tuple[str, ...]
    attempted_to_state: str


class DurationStatistic(BaseModel):
    """One pack-declared `DURATION`/`DELAY` measurement, evaluated over this run's data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    measurement_id: str
    unit: str
    samples: int = Field(ge=0)
    minimum_seconds: int | None = None
    maximum_seconds: int | None = None
    mean_seconds: float | None = None


class StateQualityReport(BaseModel):
    """Every statement one state-derivation run makes about the states it produced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = STATE_QUALITY_SCHEMA_VERSION
    envelope: OutputEnvelope
    timelines_read: int = Field(ge=0)
    states_produced: int = Field(ge=0)
    transitions_produced: int = Field(ge=0)
    assumed_initial_states: int = Field(ge=0)
    """Entities whose first observed event was mid-lifecycle -- `docs/architecture.md`:
    the assumption is recorded as an evidence record, and counted here."""
    uncertain_boundary_states: int = Field(ge=0)
    """States whose `held_over` was widened, rather than pinned, because the sequencing of
    the transitions bounding it was `UNDETERMINED` -- the uncertainty is carried on the
    state's own interval and provenance rather than raised as a contradiction."""
    illegal_transitions: tuple[IllegalTransitionFinding, ...] = ()
    by_entity_type: tuple[tuple[str, int], ...] = ()
    """States produced per entity type, sorted by entity type."""
    duration_statistics: tuple[DurationStatistic, ...] = ()
    not_checked: tuple[str, ...] = ()


def render_markdown(report: StateQualityReport) -> str:
    """Render the report as committed markdown, deterministically."""
    lines = [
        "# State Quality Report",
        "",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- `dataset_version`: `{report.envelope.dataset_version}`",
        f"- `ontology_hash`: `{report.envelope.ontology_hash}`",
        f"- `engine_version`: `{report.envelope.engine_version}`",
        "",
        "## Summary",
        "",
        f"Timelines read: **{report.timelines_read:,}**. States produced: "
        f"**{report.states_produced:,}**. Transitions produced: "
        f"**{report.transitions_produced:,}**. Assumed initial states (mid-lifecycle "
        f"entities): **{report.assumed_initial_states:,}**. States with a widened, "
        f"uncertain boundary: **{report.uncertain_boundary_states:,}**.",
        "",
        "## States by entity type",
        "",
        "| Entity type | States |",
        "|---|---:|",
    ]
    for entity_type, count in report.by_entity_type:
        lines.append(f"| `{entity_type}` | {count:,} |")
    lines.extend(["", "## Illegal transitions", ""])
    if not report.illegal_transitions:
        lines.append("No event fired a transition the active ontology does not permit.")
    else:
        lines.append(
            f"**{len(report.illegal_transitions):,}** illegal transition(s) -- an "
            "ontology-or-event-stream contradiction, never silently corrected."
        )
        lines.append("")
        for finding in report.illegal_transitions:
            lines.append(
                f"- `{finding.entity_type}` `{finding.entity_id}`: event "
                f"`{finding.offending_event_id}` (`{finding.event_type}`) attempted "
                f"`{finding.attempted_from_state}` -> `{finding.attempted_to_state}`; "
                f"declared from-state(s): {list(finding.declared_from_states)}"
            )
    lines.extend(["", "## Duration statistics", ""])
    if not report.duration_statistics:
        lines.append("No `DURATION`/`DELAY` measurement was declared, or none could be evaluated.")
    else:
        lines.append("| Measurement | Unit | Samples | Min (s) | Max (s) | Mean (s) |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for stat in report.duration_statistics:
            lines.append(
                f"| `{stat.measurement_id}` | {stat.unit} | {stat.samples:,} | "
                f"{stat.minimum_seconds if stat.minimum_seconds is not None else 'n/a'} | "
                f"{stat.maximum_seconds if stat.maximum_seconds is not None else 'n/a'} | "
                f"{f'{stat.mean_seconds:.1f}' if stat.mean_seconds is not None else 'n/a'} |"
            )
    lines.extend(["", "## What this run did NOT check", ""])
    lines.extend(f"- {item}" for item in report.not_checked)
    return "\n".join(lines) + "\n"
