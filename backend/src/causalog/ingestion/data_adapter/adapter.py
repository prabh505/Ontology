"""Module 1's entry point: read a pinned source, measure it, clean it, and account for it.

Two passes over the source, and no third
----------------------------------------
* **Pass A** -- profile pass 1 and the identity index. Nothing is written and nothing is
  judged: a foreign key cannot be called an orphan until the whole file has been seen.
* **Pass B** -- profile pass 2, row validation against the index, the cleaning transforms,
  and the two output streams.

Both passes stream. Peak memory is a function of the header width, the distinct-value cap,
and the identity cardinality -- never of the row count. `prd.md` §55 wants a large dataset
loaded inside a budget, and a profiler that had to hold the file could not be measured
against that budget honestly.

Nothing is dropped silently
---------------------------
Every row read is written to exactly one of two files: the clean layer or the quarantine,
and a quarantined row carries the codes that put it there. `rows_read == rows_clean +
rows_quarantined` is asserted at the end and printed in the report. If that assertion ever
fails, the run raises rather than publishing a report whose own arithmetic disagrees with
itself.

The raw file is opened read-only in both passes and is byte-identical afterwards. Cleaning
produces a new layer keyed by `dataset_version`; it never edits its own evidence.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, TextIO

from causalog.core.errors import DataQualityError
from causalog.core.ports.source import RawRecord, SourceDescription, SourceReader
from causalog.ingestion.data_adapter.cleaning import CleaningLedger, apply_transforms_stepwise
from causalog.ingestion.data_adapter.findings import Finding, rule
from causalog.ingestion.data_adapter.profile import DatasetProfile, Profiler
from causalog.ingestion.data_adapter.report import (
    DataQualityReport,
    HeadlineConstraint,
    RowReconciliation,
)
from causalog.ingestion.data_adapter.validate import (
    DerivationAudit,
    DerivationResult,
    IdentityIndex,
    RowValidator,
)
from causalog.ingestion.schema_mapper.coverage import CoverageReport
from causalog.ingestion.schema_mapper.dsl import SchemaMappingSpec, Transform
from causalog.ontology_runtime.dsl import ResolvedPack

__all__ = ["CLEAN_LAYER_FILES", "ImportResult", "import_dataset"]

#: The three files a clean layer holds. Named here so a caller can check for them without
#: hard-coding strings in three places.
CLEAN_LAYER_FILES: Final[tuple[str, str, str]] = (
    "records.jsonl",
    "quarantine.jsonl",
    "cleaning_ledger.jsonl",
)

#: Source row numbers kept per finding so a reader can go and look at one.
_EXAMPLE_ROW_LIMIT: Final[int] = 5

_SURPLUS_PREFIX: Final[str] = "__surplus_"

#: One source column's cleaning step: `(column, transforms, required)`. Built once per
#: import by `_cleaning_plan`, which collapses the bindings that share a column.
_ColumnPlan = tuple[str, tuple[Transform, ...], bool]

#: The share of evaluable rows a declared derivation must hold in before it is treated as
#: confirmed. A majority, and nothing cleverer: below it the mapping's stated reason for a
#: precision choice is not supported by the data, and the report says so instead of
#: repeating the claim back with a number that contradicts it.
DERIVATION_CONFIRMED_RATE: Final[float] = 0.5


@dataclass
class _FindingAccumulator:
    """Counts and example rows per `(code, subject)`, in bounded memory."""

    counts: dict[tuple[str, str], int] = field(default_factory=dict)
    details: dict[tuple[str, str], str] = field(default_factory=dict)
    examples: dict[tuple[str, str], list[int]] = field(default_factory=dict)

    def record(self, code: str, subject: str, detail: str, row_number: int | None) -> None:
        """Fold one occurrence in, keeping the FIRST detail and the first few row numbers."""
        key = (code, subject)
        self.counts[key] = self.counts.get(key, 0) + 1
        self.details.setdefault(key, detail)
        if row_number is not None:
            rows = self.examples.setdefault(key, [])
            if len(rows) < _EXAMPLE_ROW_LIMIT:
                rows.append(row_number)

    def findings(self) -> tuple[Finding, ...]:
        """Return one `Finding` per `(code, subject)`, canonically sequenced."""
        results = []
        for (code, subject), count in sorted(self.counts.items()):
            spec = rule(code)
            results.append(
                Finding(
                    code=code,
                    dimension=spec.dimension,
                    severity=spec.severity,
                    subject=subject,
                    detail=self.details[(code, subject)],
                    occurrences=count,
                    downstream_consequence=spec.downstream_consequence,
                    example_rows=tuple(self.examples.get((code, subject), [])),
                )
            )
        return tuple(results)


@dataclass
class ImportResult:
    """What one import produced: the report and where its artifacts were written."""

    report: DataQualityReport
    clean_layer: Path | None
    quarantined_row_numbers: tuple[int, ...]


def _row_values(record: RawRecord) -> tuple[dict[str, str], int]:
    """Split a raw record into header-keyed values and a surplus-field count."""
    values: dict[str, str] = {}
    surplus = 0
    for name, value in record.fields:
        if name.startswith(_SURPLUS_PREFIX):
            surplus += 1
            continue
        values[name] = value
    return values, surplus


def _records(source: SourceReader) -> Iterator[tuple[int, RawRecord]]:
    """Yield `(row_number, record)` across every batch, with 1-based row numbers."""
    row_number = 0
    for batch in source.read():
        for record in batch.records:
            row_number += 1
            yield row_number, record


def _cleaning_plan(mapping: SchemaMappingSpec) -> tuple[_ColumnPlan, ...]:
    """Collapse the bindings into one cleaning step per DISTINCT source column.

    Several bindings routinely name one column, because several ontology concepts read the
    same cell. The cell is one cell: cleaning it once per binding did the identical work
    repeatedly and, worse, counted the identical change repeatedly, which is how a
    published ledger came to claim 189,748 changed rows in a 180,519-row dataset.

    Bindings that share a column must agree on how it is cleaned. If they disagree the
    mapping is refused rather than resolved: `cleaned` is keyed by column, so one chain's
    output would silently overwrite the other's, and picking a winner by declaration
    sequence would make the cleaned value a function of YAML layout, not of the mapping.

    Raises:
        DataQualityError: if two bindings on one column declare different transform chains
            or disagree on whether it is required.
    """
    plans: dict[str, _ColumnPlan] = {}
    for binding in mapping.column_bindings:
        existing = plans.get(binding.column)
        if existing is None:
            plans[binding.column] = (binding.column, binding.transforms, binding.required)
            continue
        _, transforms, required = existing
        if transforms != binding.transforms or required != binding.required:
            raise DataQualityError(
                f"column {binding.column!r} is bound more than once with disagreeing "
                f"cleaning: transforms {[t.value for t in transforms]} required={required} "
                f"versus transforms {[t.value for t in binding.transforms]} "
                f"required={binding.required}. One cell cannot be cleaned two ways; the "
                "mapping must declare one."
            )
    return tuple(plans.values())


def _clean_row(
    values: Mapping[str, str],
    plan: tuple[_ColumnPlan, ...],
    ledger: CleaningLedger,
    accumulator: _FindingAccumulator,
    row_number: int,
) -> tuple[dict[str, str | None], bool]:
    """Apply every declared transform chain to one row, recording each change.

    Returns the cleaned values and whether any REQUIRED binding failed. A failure on an
    optional binding is recorded and the value becomes absent; a failure on a required one
    quarantines the row, because a required attribute filled by default would be an
    invented observation.

    Every transform that changes the value is recorded against ITSELF with its own
    before/after. Crediting the whole chain to its first member -- what this did until the
    ledger was found filing `'0'` -> `'false'` under TRIM_WHITESPACE -- produces receipts
    that name the wrong rule and carry the wrong rationale.
    """
    cleaned: dict[str, str | None] = {}
    failed_required = False
    for column, transforms, required in plan:
        raw = values.get(column)
        try:
            result, steps = apply_transforms_stepwise(raw, transforms)
        except DataQualityError as failure:
            accumulator.record(
                "DQ-STR-UNPARSEABLE",
                column,
                str(failure),
                row_number,
            )
            if required:
                failed_required = True
            cleaned[column] = None
            continue
        for transform, before, after in steps:
            ledger.record(transform.value, column, before, after)
        cleaned[column] = result
    return cleaned, failed_required


def _source_findings(description: SourceDescription, accumulator: _FindingAccumulator) -> None:
    """Record what the probe had to do to make the file readable at all."""
    subject = description.source_name
    if description.encoding_fell_back:
        accumulator.record(
            "DQ-SRC-ENCODING-FALLBACK",
            subject,
            (
                f"decoded as {description.encoding_chosen!r} after "
                f"{list(description.encoding_rejected)} were rejected; the first "
                "undecodable sequence is at probe-window byte offset "
                f"{description.first_undecodable_byte_offset} "
                f"({description.first_undecodable_reason})"
            ),
            None,
        )
    if description.field_separator and not description.separator_was_detected:
        accumulator.record(
            "DQ-SRC-DIALECT-UNSNIFFED",
            subject,
            (
                "the field separator could not be determined; "
                f"{description.field_separator!r} was assumed"
            ),
            None,
        )


def _profile_findings(profile: DatasetProfile, accumulator: _FindingAccumulator) -> None:
    """Record everything the profile alone establishes about the columns."""
    for column in profile.columns:
        if column.row_count and column.blank_count == column.row_count:
            accumulator.record(
                "DQ-STR-COLUMN-ALL-BLANK",
                column.name,
                f"all {column.row_count} rows are blank",
                None,
            )
        if not column.distinct_exact:
            accumulator.record(
                "DQ-DST-CARDINALITY-INEXACT",
                column.name,
                (
                    f"distinct values exceeded the cap of {column.distinct_cap}; the "
                    f"reported count of {column.distinct_count} is a floor, not a count"
                ),
                None,
            )
        summary = column.numeric
        if summary is not None and (summary.outliers_low or summary.outliers_high):
            accumulator.record(
                "DQ-DST-OUTLIERS",
                column.name,
                (
                    f"{summary.outliers_low} below {summary.fence_low:.4f} and "
                    f"{summary.outliers_high} above {summary.fence_high:.4f} under "
                    f"{summary.fence_rule} (p25={summary.p25:.4f}, p75={summary.p75:.4f})"
                ),
                None,
            )
        temporal = column.temporal
        if temporal is not None and temporal.values_stating_utc_offset == 0:
            accumulator.record(
                "DQ-TMP-NO-OFFSET",
                column.name,
                (
                    f"none of {temporal.parsed_count} parsed instants states a UTC offset; "
                    "the mapping's declared timezone policy applies and the interval "
                    "carries ASSUMED provenance"
                ),
                None,
            )


def _derivation_findings(
    results: tuple[DerivationResult, ...], accumulator: _FindingAccumulator
) -> None:
    """Turn each declared derivation check's measurement into findings.

    The threshold is deliberately low. A derivation holding in even a large minority of
    rows means the column's sub-day component is sometimes arithmetic, and "sometimes
    manufactured" is not a precision anything may rely on -- a reader cannot tell which
    rows they are holding.
    """
    for result in results:
        if result.evaluated == 0:
            continue
        if result.agreement_rate < DERIVATION_CONFIRMED_RATE:
            accumulator.record(
                "DQ-TMP-DERIVATION-UNCONFIRMED",
                result.column,
                (
                    f"{result.check_id}: holds in only {result.matches:,} of "
                    f"{result.evaluated:,} evaluable rows ({result.agreement_rate:.4%}), "
                    f"below the {DERIVATION_CONFIRMED_RATE:.0%} threshold"
                ),
                None,
            )
            continue
        accumulator.record(
            "DQ-TMP-DERIVED-PRECISION",
            result.column,
            (
                f"{result.check_id}: equals {result.equals_column}"
                + (f" plus {result.plus_days_column} days" if result.plus_days_column else "")
                + f" exactly in {result.matches:,} of {result.evaluated:,} evaluable rows "
                f"({result.agreement_rate:.4%})"
            ),
            None,
        )
        if not result.residual_seconds:
            continue
        top = ", ".join(
            f"{seconds:+d}s in {count:,} rows" for seconds, count in result.residual_seconds[:4]
        )
        accumulator.record(
            "DQ-TMP-DERIVATION-RESIDUAL",
            result.column,
            (
                f"{result.check_id}: {result.mismatches:,} rows do not match, across "
                f"{len(result.residual_seconds)}"
                + ("" if result.residuals_exact else "+ (capped)")
                + f" distinct residual(s): {top}"
            ),
            None,
        )


def _headline_constraints(
    profile: DatasetProfile,
    mapping: SchemaMappingSpec,
    findings: tuple[Finding, ...],
    derivations: tuple[DerivationResult, ...],
) -> tuple[HeadlineConstraint, ...]:
    """Derive the constraints that bound every downstream conclusion.

    Each one is measured from this run's own numbers. A constraint stated without the
    number behind it is an opinion, and the model refuses to hold one.
    """
    constraints: list[HeadlineConstraint] = []
    for result in derivations:
        if result.evaluated == 0 or result.agreement_rate < DERIVATION_CONFIRMED_RATE:
            continue
        residual = (
            "; the rows that do not match are displaced by "
            + ", ".join(
                f"{seconds // 3600:+d}h ({count:,} rows)"
                for seconds, count in result.residual_seconds[:3]
            )
            if result.residual_seconds
            else ""
        )
        constraints.append(
            HeadlineConstraint(
                code=f"DQ-HEADLINE-DERIVED-{result.check_id}",
                statement=(
                    f"`{result.column}` IS NOT AN INDEPENDENTLY OBSERVED INSTANT. Its value "
                    f"equals `{result.equals_column}`"
                    + (
                        f" plus `{result.plus_days_column}` whole days"
                        if result.plus_days_column
                        else ""
                    )
                    + f", to the minute, in {result.agreement_rate:.4%} of evaluable rows. "
                    "Its sub-day component was therefore COPIED, not measured, and any "
                    "sequencing that reads it is reading a number the source manufactured."
                ),
                measurement=(
                    f"{result.matches:,} of {result.evaluated:,} evaluable rows match "
                    f"exactly ({result.agreement_rate:.4%})"
                    f"{residual}"
                ),
                consequence=(
                    "This column MUST be bound at DAY precision, and this mapping binds it "
                    "that way. Binding it at the precision its text displays would let the "
                    "engine sequence two events by manufactured minutes -- imputation entering "
                    "through a format string rather than through a missing value, and "
                    "invisible to every check downstream of here. Whatever precedence the "
                    "source's sub-day component appears to give between these two columns "
                    "is not evidence and must never be promoted to INFERRED."
                ),
            )
        )
    equal_pairs = {
        finding.subject: finding.occurrences
        for finding in findings
        if finding.code == "DQ-TMP-PRECEDENCE-EQUAL"
    }
    date_granular = [
        column
        for binding in mapping.temporal_bindings
        for column in [profile.column(binding.column)]
        if column is not None and column.temporal is not None and column.temporal.is_date_granular
    ]
    if date_granular:
        names = ", ".join(f"`{column.name}`" for column in date_granular)
        total = sum(column.temporal.parsed_count for column in date_granular if column.temporal)
        constraints.append(
            HeadlineConstraint(
                code="DQ-HEADLINE-DATE-GRANULAR",
                statement=(
                    f"{names} pin instants no finer than a calendar day, so every interval "
                    "built from them spans a whole day. TWO EVENTS ON ONE DATE OVERLAP, so "
                    "causalog.core.temporal.verdict returns UNDETERMINED for the pair, and "
                    "NO INTRA-DAY CAUSAL EDGE CAN EVER BE PROMOTED TO INFERRED."
                ),
                measurement=(
                    f"{total:,} parsed instants across {len(date_granular)} column(s); "
                    "zero of them carry a non-midnight time component"
                ),
                consequence=(
                    "This is risk R-14 (UNDETERMINED dominance) made measurable rather than "
                    "predicted. It is a property of the source, not a defect to fix: the "
                    "precedence information is not in the data. Do not tune it away by "
                    "loosening the LAW-TIME test -- that would manufacture precedence the "
                    "source never recorded."
                ),
            )
        )
    for pair_id, count in sorted(equal_pairs.items()):
        constraints.append(
            HeadlineConstraint(
                code=f"DQ-HEADLINE-INSEPARABLE-{pair_id}",
                statement=(
                    f"The declared precedence pair {pair_id} is temporally INSEPARABLE in "
                    f"{count:,} rows: both instants fall in the same interval."
                ),
                measurement=f"{count:,} rows of the dataset",
                consequence=(
                    "For those rows the two events cannot be sequenced from the data at all. "
                    "Any edge between them is UNDETERMINED and is blocked from promotion to "
                    "INFERRED (ADR-0021). A ranking that appears to sequence them is showing a "
                    "sort key, not a precedence claim."
                ),
            )
        )
    return tuple(constraints)


def _not_checked(coverage: CoverageReport, clean_layer: Path | None) -> tuple[str, ...]:
    """Assemble the explicit list of checks this run did not perform."""
    items = [
        "**Semantic correctness of the mapping.** That a column is bound to the RIGHT "
        "ontology concept is not checkable here and is not checked anywhere. A mapping that "
        "validates cleanly can still be wrong, and it would produce silently wrong "
        "causality rather than an error. This is risk R-16.",
        "**Whether the source data is TRUE.** Profiling measures what the file says, not "
        "whether the file is right about the world.",
        "**Persistence.** No fact was written to PostgreSQL: module 4 (Event Generator) "
        "does not exist, so there are no Events to persist. This import ends at the clean "
        "layer and this report.",
        "**Causal accuracy.** There is no causal ground truth in this dataset "
        "(CONVENTIONS.md §14), so nothing here or downstream can measure it.",
    ]
    if clean_layer is None:
        items.append(
            "**The clean layer was not written.** This run profiled and validated without "
            "materialising output, so the row reconciliation is a count rather than a "
            "count of files on disk."
        )
    items.extend(
        f"**{finding.code}** ({finding.subject}): {finding.message} => "
        f"{finding.downstream_consequence}"
        for finding in coverage.not_runnable
    )
    return tuple(items)


def import_dataset(
    source: SourceReader,
    mapping: SchemaMappingSpec,
    pack: ResolvedPack,
    coverage: CoverageReport,
    *,
    dataset_id: str,
    source_url: str,
    mapping_hash: str,
    ontology_hash: str,
    engine_version: str,
    clean_layer: Path | None = None,
) -> ImportResult:
    """Run the full import: two streaming passes, then the report.

    Args:
        source: the pinned, probed reader.
        mapping: the CONFIRMED mapping (a proposal never reaches here -- the loader refuses
            it).
        pack: the resolved ontology pack the mapping binds to.
        coverage: the coverage assessment already computed for this mapping and pack.
        dataset_id: the pack identifier, carried into the report.
        source_url: where the file was published, for the record.
        mapping_hash: the mapping's content address.
        ontology_hash: the pack's content address.
        engine_version: `causalog.ENGINE_VERSION`.
        clean_layer: directory to write the clean layer into. `None` profiles and validates
            without materialising anything, and the report SAYS the layer was not written.

    Raises:
        DataQualityError: if the row reconciliation does not balance. Publishing a report
            whose own arithmetic disagrees with itself would be worse than failing.
    """
    description = source.describe()
    header = description.column_names
    accumulator = _FindingAccumulator()
    _source_findings(description, accumulator)

    profiler = Profiler(header)
    index = IdentityIndex(mapping)
    for _row_number, record in _records(source):
        values, _surplus = _row_values(record)
        profiler.observe_first(record.fields)
        index.observe(values)
    profiler.begin_second_pass()

    validator = RowValidator(mapping, pack, index, header)
    audit = DerivationAudit(mapping)
    ledger = CleaningLedger()
    plan = _cleaning_plan(mapping)
    quarantined: list[int] = []
    rows_read = 0
    rows_clean = 0

    with _open_layer(clean_layer) as streams:
        records_out, quarantine_out = streams
        for row_number, record in _records(source):
            rows_read += 1
            values, surplus = _row_values(record)
            profiler.observe_second(record.fields)
            issues, _intervals = validator.check(values, surplus)
            audit.observe(values)
            cleaned, failed_required = _clean_row(values, plan, ledger, accumulator, row_number)
            quarantining = failed_required
            for issue in issues:
                accumulator.record(issue.code, issue.subject, issue.detail, row_number)
                if rule(issue.code).quarantines_row:
                    quarantining = True
            if quarantining:
                quarantined.append(row_number)
                _write_json(
                    quarantine_out,
                    {
                        "row_number": row_number,
                        "evidence_record_id": record.evidence_record_id,
                        "reasons": sorted(
                            {issue.code for issue in issues if rule(issue.code).quarantines_row}
                            | ({"DQ-STR-UNPARSEABLE"} if failed_required else set())
                        ),
                        "fields": dict(record.fields),
                    },
                )
                continue
            rows_clean += 1
            _write_json(
                records_out,
                {
                    "row_number": row_number,
                    "evidence_record_id": record.evidence_record_id,
                    "values": cleaned,
                },
            )

    profile = profiler.result()
    _profile_findings(profile, accumulator)
    findings = accumulator.findings()
    reconciliation = RowReconciliation(
        rows_read=rows_read, rows_clean=rows_clean, rows_quarantined=len(quarantined)
    )
    if not reconciliation.reconciles:
        raise DataQualityError(
            f"Row reconciliation failed: read {rows_read}, clean {rows_clean}, quarantined "
            f"{len(quarantined)}. A report whose own arithmetic disagrees with itself "
            "cannot be published; nothing is dropped silently."
        )
    cleaning_actions = ledger.actions()
    if cleaning_actions:
        accumulator.record(
            "DQ-CLN-APPLIED",
            "<dataset>",
            (
                f"{len(cleaning_actions)} (rule, column) pair(s) changed values; every "
                "change is itemised in the cleaning ledger"
            ),
            None,
        )
    for binding in mapping.temporal_bindings:
        accumulator.record(
            "DQ-CLN-TIME-ASSUMED",
            binding.column,
            (
                f"parsed under the declared source_format {binding.source_format!r} at "
                f"{binding.precision.value} precision with timezone policy "
                f"{binding.timezone_policy.value}; the interval carries "
                f"{binding.provenance.value} provenance"
            ),
            None,
        )
    for entity_type, count, example in index.conflicts():
        accumulator.record(
            "DQ-REF-DUPLICATE-IDENTITY",
            entity_type,
            (
                f"{count:,} row(s) carry an identifying key already seen with different "
                f"attribute values; first such key: {example!r}"
            ),
            None,
        )
    derivations = audit.results()
    _derivation_findings(derivations, accumulator)
    findings = accumulator.findings()

    report = DataQualityReport(
        dataset_id=dataset_id,
        dataset_version=source.dataset_version(),
        engine_version=engine_version,
        ontology_pack=pack.pack_id,
        ontology_version=pack.ontology_version,
        ontology_hash=ontology_hash,
        mapping_id=mapping.mapping_id,
        mapping_version=mapping.mapping_version,
        mapping_hash=mapping_hash,
        headline_constraints=_headline_constraints(profile, mapping, findings, derivations),
        source=description,
        source_url=source_url,
        rows=reconciliation,
        findings=findings,
        cleaning_actions=cleaning_actions,
        identity_counts=tuple(
            (entity_type, index.distinct_count(entity_type)) for entity_type in index.entity_types()
        ),
        coverage=coverage,
        profile=profile,
        derivations=derivations,
        not_checked=_not_checked(coverage, clean_layer),
    )
    if clean_layer is not None:
        _write_ledger(clean_layer, cleaning_actions)
    return ImportResult(
        report=report,
        clean_layer=clean_layer,
        quarantined_row_numbers=tuple(quarantined),
    )


class _LayerStreams:
    """Open the two output streams, or two sinks that discard, as one context manager."""

    def __init__(self, directory: Path | None) -> None:
        """Prepare the layer directory, if there is one."""
        self._directory = directory
        self._handles: list[TextIO] = []

    def __enter__(self) -> tuple[TextIO | None, TextIO | None]:
        """Open `records.jsonl` and `quarantine.jsonl`, or return two `None`s."""
        if self._directory is None:
            return (None, None)
        self._directory.mkdir(parents=True, exist_ok=True)
        records = (self._directory / CLEAN_LAYER_FILES[0]).open("w", encoding="utf-8")
        quarantine = (self._directory / CLEAN_LAYER_FILES[1]).open("w", encoding="utf-8")
        self._handles = [records, quarantine]
        return (records, quarantine)

    def __exit__(self, *_exception: object) -> None:
        """Close whatever was opened."""
        for handle in self._handles:
            handle.close()
        self._handles = []


def _open_layer(directory: Path | None) -> _LayerStreams:
    """Return the output-stream context manager for a layer directory."""
    return _LayerStreams(directory)


def _write_json(handle: TextIO | None, payload: dict[str, object]) -> None:
    """Write one JSONL line, or nothing when no layer is being materialised.

    `sort_keys` and no whitespace: the layer is compared byte-for-byte by the determinism
    test, and a formatter that emitted keys in insertion sequence would make an identical
    run look like a changed one.
    """
    if handle is None:
        return
    handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _write_ledger(directory: Path, actions: tuple[object, ...]) -> None:
    """Write the cleaning ledger beside the clean layer."""
    path = directory / CLEAN_LAYER_FILES[2]
    with path.open("w", encoding="utf-8") as handle:
        for action in actions:
            payload = action.model_dump(mode="json")  # type: ignore[attr-defined]
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
