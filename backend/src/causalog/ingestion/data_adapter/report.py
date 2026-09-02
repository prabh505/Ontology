"""The Data Quality Report: machine-readable, human-readable, and the same report.

One model, two renderings. The JSON is canonical (`core.serialization.to_canonical_json`) so
two runs over the same input produce the same bytes and the same `report_sha256`; the
Markdown is generated from the same object, so the two cannot drift into disagreeing about
what was found.

The headline is not buried
--------------------------
`headline_constraints` is the first field rendered in both forms, and it exists as a field
rather than as a convention about where to put important text. A limitation that bounds
every causal claim the engine can ever make about a dataset -- date-only timestamps, say --
belongs above the column tables, not in finding 47 of 63. The requirement in the module
brief was that such a limitation be "stated loudly, not buried", and a field that renders
first is the only version of that which survives the next person editing the renderer.

`report_sha256` is not an `IdentifierPrefix` address
-----------------------------------------------------
Content addressing under `CONVENTIONS.md` §9 mints identifiers for engine artifacts from a
closed prefix enum. A report is a document about a run, not an artifact inside one, so it
carries a plain digest of its own canonical bytes under a name that says exactly that.
Borrowing a prefix from the enum would assert a kind of identity this does not have.
"""

from __future__ import annotations

import hashlib
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.ports.source import SourceDescription
from causalog.core.serialization import to_canonical_json
from causalog.ingestion.data_adapter.cleaning import CleaningAction
from causalog.ingestion.data_adapter.findings import Finding
from causalog.ingestion.data_adapter.profile import DatasetProfile
from causalog.ingestion.data_adapter.validate import DerivationResult
from causalog.ingestion.schema_mapper.coverage import CoverageReport
from causalog.ontology_runtime.diagnostics import Severity

__all__ = [
    "REPORT_SCHEMA_VERSION",
    "DataQualityReport",
    "HeadlineConstraint",
    "RowReconciliation",
    "render_markdown",
    "report_sha256",
]

#: This document's own version. Bumped when the report's SHAPE changes, which invalidates
#: comparison with reports written under a prior shape.
REPORT_SCHEMA_VERSION: Final[str] = "1.0.0"

_SEVERITY_SEQUENCE: Final[dict[Severity, int]] = {
    Severity.ERROR: 0,
    Severity.NOT_RUNNABLE: 1,
    Severity.WARNING: 2,
}


class HeadlineConstraint(BaseModel):
    """A limitation that bounds what any downstream conclusion may claim.

    Distinct from a finding: a finding says something is wrong with the data, a headline
    constraint says something is permanently true about what this data can support. A user
    can fix a finding. Nobody can fix a headline constraint -- they can only know about it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    measurement: str = Field(min_length=1)
    """The number behind the statement. A constraint asserted without one is an opinion."""
    consequence: str = Field(min_length=1)


class RowReconciliation(BaseModel):
    """The count that proves nothing was dropped silently."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rows_read: int
    rows_clean: int
    rows_quarantined: int

    @property
    def reconciles(self) -> bool:
        """Return whether every row read is accounted for exactly once."""
        return self.rows_read == self.rows_clean + self.rows_quarantined


class DataQualityReport(BaseModel):
    """Everything one import measured, in the sequence a reader needs it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = REPORT_SCHEMA_VERSION

    dataset_id: str
    dataset_version: str
    engine_version: str
    ontology_pack: str
    ontology_version: str
    ontology_hash: str
    mapping_id: str
    mapping_version: str
    mapping_hash: str

    headline_constraints: tuple[HeadlineConstraint, ...] = ()
    source: SourceDescription
    source_url: str
    rows: RowReconciliation
    findings: tuple[Finding, ...] = ()
    cleaning_actions: tuple[CleaningAction, ...] = ()
    identity_counts: tuple[tuple[str, int], ...] = ()
    coverage: CoverageReport
    profile: DatasetProfile
    derivations: tuple[DerivationResult, ...] = ()
    """What each declared `temporal_derivation_check` measured. A column whose precision is
    arithmetic on another column is reported here with its agreement rate and residuals."""
    not_checked: tuple[str, ...] = ()
    """Checks this run did NOT perform, named. A report that lists only what it looked at
    reads as a report that looked at everything (DEF-0001, OQ-014)."""

    @property
    def ranked_findings(self) -> tuple[Finding, ...]:
        """Return findings most severe first, then by code and subject."""
        return tuple(
            sorted(
                self.findings,
                key=lambda item: (_SEVERITY_SEQUENCE[item.severity], item.code, item.subject),
            )
        )

    def count_by_severity(self, severity: Severity) -> int:
        """Return how many findings carry one severity."""
        return sum(1 for item in self.findings if item.severity is severity)


def report_sha256(report: DataQualityReport) -> str:
    """Return the digest of a report's canonical bytes.

    Deterministic over the report's content, and therefore over the input that produced it.
    `tests/determinism/` asserts that two imports of one file yield one value here.
    """
    return hashlib.sha256(to_canonical_json(report).encode("utf-8")).hexdigest()


def _render_headline(report: DataQualityReport) -> list[str]:
    """Render the constraints block that opens the document."""
    if not report.headline_constraints:
        return [
            "## Headline constraints",
            "",
            "None recorded. **This is a claim, not an absence of checking** -- see "
            "*What this report did not check* below for the checks that did not run.",
            "",
        ]
    lines = ["## Headline constraints", ""]
    lines.append(
        "These bound what any downstream conclusion about this dataset may claim. They are "
        "not defects and cannot be fixed; they can only be known about."
    )
    lines.append("")
    for constraint in report.headline_constraints:
        lines.append(f"### {constraint.code}")
        lines.append("")
        lines.append(f"**{constraint.statement}**")
        lines.append("")
        lines.append(f"- Measured: {constraint.measurement}")
        lines.append(f"- Consequence: {constraint.consequence}")
        lines.append("")
    return lines


def _render_findings(report: DataQualityReport) -> list[str]:
    """Render the findings table, most severe first."""
    lines = ["## Findings", ""]
    if not report.findings:
        lines.extend(["No findings.", ""])
        return lines
    lines.append("| Severity | Code | Subject | Occurrences | Detail | Downstream consequence |")
    lines.append("|---|---|---|---|---|---|")
    for finding in report.ranked_findings:
        detail = finding.detail.replace("|", "\\|")
        consequence = finding.downstream_consequence.replace("|", "\\|")
        lines.append(
            f"| {finding.severity.value} | `{finding.code}` | `{finding.subject}` | "
            f"{finding.occurrences} | {detail} | {consequence} |"
        )
    lines.append("")
    return lines


def _render_columns(report: DataQualityReport) -> list[str]:
    """Render the per-column profile table."""
    lines = ["## Column profile", ""]
    lines.append("| # | Column | Type | Blank | Blank rate | Distinct | Exact? | Min | Max |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for column in report.profile.columns:
        numeric = column.numeric
        minimum = f"{numeric.minimum:g}" if numeric else (column.minimum_text or "")
        maximum = f"{numeric.maximum:g}" if numeric else (column.maximum_text or "")
        lines.append(
            f"| {column.position} | `{column.name}` | {column.inferred_type.value} | "
            f"{column.blank_count} | {column.blank_rate:.4f} | {column.distinct_count} | "
            f"{'yes' if column.distinct_exact else '**NO (capped)**'} | "
            f"{_truncate(minimum)} | {_truncate(maximum)} |"
        )
    lines.append("")
    lines.append("### Distributions")
    lines.append("")
    lines.append(
        "| Column | Count | Mean | Std dev | p01 | p25 | p50 | p75 | p99 | Fence | Low | High |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for column in report.profile.columns:
        summary = column.numeric
        if summary is None:
            continue
        lines.append(
            f"| `{column.name}` | {summary.count} | {summary.mean:.4f} | "
            f"{summary.standard_deviation:.4f} | {summary.p01:.4f} | {summary.p25:.4f} | "
            f"{summary.p50:.4f} | {summary.p75:.4f} | {summary.p99:.4f} | "
            f"{summary.fence_rule} | {summary.outliers_low} | {summary.outliers_high} |"
        )
    lines.append("")
    return lines


def _render_temporal(report: DataQualityReport) -> list[str]:
    """Render the temporal granularity table -- the numbers behind the headline."""
    rows = [column for column in report.profile.columns if column.temporal is not None]
    if not rows:
        return []
    lines = ["## Temporal granularity", ""]
    lines.append(
        "| Column | Parsed | Not date-like | Earliest | Latest | With time | Without time "
        "| Nonzero seconds | States offset | Date-granular |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for column in rows:
        summary = column.temporal
        assert summary is not None  # noqa: S101 -- narrowed by the filter above
        lines.append(
            f"| `{column.name}` | {summary.parsed_count} | {summary.unparsed_count} | "
            f"{summary.earliest or ''} | {summary.latest or ''} | "
            f"{summary.values_with_time_component} | "
            f"{summary.values_without_time_component} | "
            f"{summary.values_with_nonzero_seconds} | "
            f"{summary.values_stating_utc_offset} | "
            f"{'**YES**' if summary.is_date_granular else 'no'} |"
        )
    lines.append("")
    return lines


def _render_derivations(report: DataQualityReport) -> list[str]:
    """Render the derived-precision audit -- the numbers behind the headline."""
    if not report.derivations:
        return []
    lines = ["## Declared temporal-derivation checks", ""]
    lines.append(
        "Does one temporal column's value turn out to be arithmetic on another? A column "
        "that says `22:56` because a different column said `22:56` has not observed a "
        "minute; it has copied one."
    )
    lines.append("")
    lines.append(
        "| Check | Column | Equals | Plus days | Matches | Mismatches | Not evaluable | "
        "Agreement | Residuals (s, rows) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for result in report.derivations:
        residuals = (
            ", ".join(f"{seconds:+d}: {count:,}" for seconds, count in result.residual_seconds[:6])
            or "none"
        )
        if not result.residuals_exact:
            residuals += " (distinct residuals capped)"
        lines.append(
            f"| `{result.check_id}` | `{result.column}` | `{result.equals_column}` | "
            f"`{result.plus_days_column or ''}` | {result.matches:,} | "
            f"{result.mismatches:,} | {result.unevaluable:,} | "
            f"{result.agreement_rate:.4%} | {residuals} |"
        )
    lines.append("")
    for result in report.derivations:
        lines.append(f"- **{result.check_id}** — {result.rationale}")
    lines.append("")
    return lines


def _render_cleaning(report: DataQualityReport) -> list[str]:
    """Render the cleaning ledger summary -- the receipts."""
    lines = ["## Cleaning ledger", ""]
    if not report.cleaning_actions:
        lines.extend(["No cleaning transform changed any value.", ""])
        return lines
    lines.append(
        "Every change made between the raw bytes and the clean layer. The raw file is "
        "unmodified; this is the complete list of differences."
    )
    lines.append("")
    lines.append("| Rule | Column | Rows | Before | After | Provenance | Rationale |")
    lines.append("|---|---|---|---|---|---|---|")
    for action in report.cleaning_actions:
        lines.append(
            f"| `{action.rule_id}` | `{action.column}` | {action.rows_affected} | "
            f"`{_truncate(action.before_sample or '')}` | "
            f"`{_truncate(action.after_sample or '')}` | {action.provenance.value} | "
            f"{action.rationale} |"
        )
    lines.append("")
    return lines


def _render_coverage(report: DataQualityReport) -> list[str]:
    """Render mapping coverage: what is unmapped and what that breaks."""
    lines = ["## Mapping coverage", ""]
    lines.append(
        f"`{report.mapping_id}` v{report.mapping_version} (`{report.mapping_hash}`) against "
        f"pack `{report.ontology_pack}` v{report.ontology_version} "
        f"(`{report.ontology_hash}`)."
    )
    lines.append("")
    bound = report.coverage.bound_column_count
    dropped = report.coverage.dropped_column_count
    lines.append(f"- Bound columns: {bound}")
    lines.append(f"- Deliberately dropped columns: {dropped}")
    lines.append(f"- Source header columns: {report.coverage.header_column_count}")
    lines.append(
        f"- Binding entries: {report.coverage.binding_count} "
        f"(several bindings may read one column; {bound} + {dropped} = "
        f"{bound + dropped} accounts for the header)"
    )
    lines.append("")
    if not report.coverage.findings:
        lines.extend(["Every ontology-required field is bound.", ""])
        return lines
    lines.append("| Severity | Code | Subject | Message | Downstream consequence |")
    lines.append("|---|---|---|---|---|")
    sequence = _SEVERITY_SEQUENCE
    for finding in sorted(
        report.coverage.findings,
        key=lambda item: (sequence[item.severity], item.code, item.subject),
    ):
        message = finding.message.replace("|", "\\|")
        consequence = finding.downstream_consequence.replace("|", "\\|")
        lines.append(
            f"| {finding.severity.value} | `{finding.code}` | `{finding.subject}` | "
            f"{message} | {consequence} |"
        )
    lines.append("")
    return lines


def _truncate(text: str, limit: int = 40) -> str:
    """Shorten a cell value for the Markdown table, marking that it was shortened."""
    flattened = text.replace("\n", " ").replace("|", "\\|")
    return flattened if len(flattened) <= limit else flattened[: limit - 1] + "…"


def render_markdown(report: DataQualityReport) -> str:
    """Render the human-readable report, headline first.

    Generated from the same object as the JSON, so the two cannot disagree about what was
    found. The sequence is deliberate: constraints, then reconciliation, then findings, then
    the tables, then what was NOT checked.
    """
    lines: list[str] = []
    lines.append(f"# Data Quality Report — `{report.dataset_id}`")
    lines.append("")
    lines.append(
        f"> Generated by CausaLog module 1 (Data Adapter) and module 2 (Schema Mapper). "
        f"Report schema `{report.report_schema_version}`. This document is committed; the "
        f"data it describes is pinned by hash and is not."
    )
    lines.append("")
    lines.append(f"**`dataset_version`** `{report.dataset_version}`")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| Source file | `{report.source.source_name}` |")
    lines.append(f"| Published at | {report.source_url} |")
    lines.append(f"| Bytes | {report.source.byte_count:,} |")
    lines.append(f"| `sha256` | `{report.source.content_sha256}` |")
    lines.append(f"| Columns | {len(report.source.column_names)} |")
    lines.append(f"| Encoding chosen | `{report.source.encoding_chosen}` |")
    lines.append(
        f"| Encodings rejected | "
        f"{', '.join(f'`{item}`' for item in report.source.encoding_rejected) or 'none'} |"
    )
    lines.append(
        f"| Field separator | `{report.source.field_separator}` "
        f"({'detected' if report.source.separator_was_detected else 'ASSUMED'}) |"
    )
    lines.append(f"| `engine_version` | `{report.engine_version}` |")
    lines.append(f"| `ontology_hash` | `{report.ontology_hash}` |")
    lines.append(f"| `mapping_hash` | `{report.mapping_hash}` |")
    lines.append("")
    lines.extend(_render_headline(report))
    lines.append("## Row reconciliation")
    lines.append("")
    lines.append(
        "Nothing is dropped silently. Every row read is either in the clean layer or in "
        "quarantine with a reason."
    )
    lines.append("")
    lines.append(f"- Rows read: **{report.rows.rows_read:,}**")
    lines.append(f"- Rows clean: **{report.rows.rows_clean:,}**")
    lines.append(f"- Rows quarantined: **{report.rows.rows_quarantined:,}**")
    lines.append(
        f"- Reconciles: **{'yes' if report.rows.reconciles else 'NO — THIS IS A DEFECT'}**"
    )
    lines.append("")
    lines.extend(_render_findings(report))
    lines.extend(_render_temporal(report))
    lines.extend(_render_derivations(report))
    lines.extend(_render_coverage(report))
    lines.extend(_render_cleaning(report))
    lines.extend(_render_columns(report))
    lines.append("## What this report did not check")
    lines.append("")
    lines.append(
        "A report that lists only what it looked at reads as a report that looked at "
        "everything. This repository has twice mistaken a check that could not run for one "
        "that passed (DEF-0001, OQ-014), so the gaps are stated."
    )
    lines.append("")
    for item in report.not_checked:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
