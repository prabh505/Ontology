"""Interpreting the mapping DSL's transform and temporal declarations.

**This is mapping semantics, not import bookkeeping.** Every function here reads a
`Transform` or a `TemporalBindingSpec` -- types declared two files away in `dsl.py` -- and
answers "what does this declaration MEAN for one cell". That is the schema mapper's
question. It lived in `data_adapter.cleaning` while module 1 was the only caller; module 2's
own record mapper is the second, and a shared function reached through the module that
happens to have used it first is a cycle waiting for its second caller.

Moved here verbatim, with no behavioural change, and re-exported from
`data_adapter.cleaning` so module 1's public surface is exactly what it was. What stayed
behind is what genuinely belongs to an import RUN: the receipts, their rationales, and the
ledger that accumulates them.

**No timestamp is ever imputed.** This is the load-bearing property and it moves with the
code. There is no transform that narrows an instant. `build_interval` either WIDENS a
parsed value into the interval it actually denotes or, for a blank, returns the unbounded
UNKNOWN interval with `ASSUMED` provenance. There is deliberately no code path from a coarse
or absent instant to a point one; `TimeInterval` refuses `INFERRED` + `EXACT` at
construction, and `tests/law/test_cleaning_never_imputes_time.py` enumerates this registry
rather than trusting a naming convention (`CONVENTIONS.md` §10, ADR-0021).

A transform that cannot express a value raises `core.errors.DataQualityError` -- the
existing member of the closed taxonomy for exactly this (`CONVENTIONS.md` §7).
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Final

from causalog.core.errors import DataQualityError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TimeInterval,
)
from causalog.ingestion.schema_mapper.dsl import TemporalBindingSpec, Transform

__all__ = [
    "PRECISION_SPANS",
    "TransformStep",
    "apply_transform",
    "apply_transforms",
    "apply_transforms_stepwise",
    "build_interval",
    "parse_source_instant",
]

#: One transform's OWN effect inside a chain: the rule, and the value either side of it.
#: A plain tuple rather than a model because one is built per changed cell per column per
#: row, and the ledger consumes it immediately.
TransformStep = tuple[Transform, str | None, str | None]

#: How far an interval reaches beyond its lower bound, per declared precision. Every entry
#: WIDENS. There is no entry that narrows, and `EXACT` is absent because the mapping DSL
#: refuses to declare it (ADR-0021).
PRECISION_SPANS: Final[dict[Precision, timedelta]] = {
    Precision.SECOND: timedelta(seconds=1) - timedelta(microseconds=1),
    Precision.MINUTE: timedelta(minutes=1) - timedelta(microseconds=1),
    Precision.HOUR: timedelta(hours=1) - timedelta(microseconds=1),
    Precision.DAY: timedelta(days=1) - timedelta(microseconds=1),
}

_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "y", "t"})
_FALSE_VALUES: Final[frozenset[str]] = frozenset({"0", "false", "no", "n", "f"})


def apply_transform(transform: Transform, value: str | None) -> str | None:
    """Apply one transform, returning the new value or `None` for an absent one.

    A `None` input passes through every transform unchanged: an absent value has nothing to
    trim, parse, or normalise, and inventing one at this point is the failure the whole
    module is built to prevent.

    Raises:
        DataQualityError: if the value is present and the transform cannot express it.
    """
    if value is None:
        return None
    if transform is Transform.IDENTITY:
        return value
    if transform is Transform.TRIM_WHITESPACE:
        return value.strip()
    if transform is Transform.NORMALIZE_UNICODE_NFC:
        return unicodedata.normalize("NFC", value)
    if transform is Transform.UPPERCASE:
        return value.upper()
    if transform is Transform.EMPTY_TO_NULL:
        return None if not value.strip() else value
    if transform is Transform.PARSE_INTEGER:
        return _parse_integer(value)
    if transform is Transform.PARSE_DECIMAL:
        return _parse_decimal(value)
    if transform is Transform.PARSE_BOOLEAN_FLAG:
        return _parse_boolean(value)
    # The two temporal members are applied through `build_interval`, which needs the
    # binding's declared format and precision. Reaching them here means a temporal
    # transform was listed on a plain column binding, which is a mapping defect.
    raise DataQualityError(
        f"{transform.value} produces a TimeInterval and must be declared through a "
        "temporal_binding, not as a column transform."
    )


def _parse_integer(value: str) -> str:
    """Return the canonical text of an integer, or fail."""
    text = value.strip()
    try:
        return str(int(text))
    except ValueError as failure:
        raise DataQualityError(f"{value!r} is not an integer") from failure


def _parse_decimal(value: str) -> str:
    """Return the canonical text of a decimal, or fail."""
    text = value.strip()
    try:
        number = float(text)
    except ValueError as failure:
        raise DataQualityError(f"{value!r} is not a decimal") from failure
    if number != number or number in (float("inf"), float("-inf")):
        raise DataQualityError(f"{value!r} is not a finite decimal")
    return repr(number)


def _parse_boolean(value: str) -> str:
    """Return `true`/`false`, or fail. The admissible set is closed and small."""
    text = value.strip().lower()
    if text in _TRUE_VALUES:
        return "true"
    if text in _FALSE_VALUES:
        return "false"
    raise DataQualityError(
        f"{value!r} is not one of the admissible flag values "
        f"{sorted(_TRUE_VALUES | _FALSE_VALUES)}"
    )


def apply_transforms_stepwise(
    value: str | None, transforms: tuple[Transform, ...]
) -> tuple[str | None, tuple[TransformStep, ...]]:
    """Apply a chain in declared sequence, returning the result and a step per CHANGE.

    Each step carries the before/after of ONE transform, not of the chain. This is what
    makes a receipt name the rule that actually did the work: a chain of
    `[TRIM_WHITESPACE, PARSE_DECIMAL]` turning `' 35 '` into `'35.0'` yields two steps, and
    the decimal parse is credited to `PARSE_DECIMAL` rather than to whichever member of the
    chain happened to come first. Attributing a chain's net effect to its first member was
    a real defect here: it filed every type coercion in the dataset under TRIM_WHITESPACE,
    carrying TRIM_WHITESPACE's whitespace rationale, and left `PARSE_DECIMAL` and
    `PARSE_BOOLEAN_FLAG` absent from the ledger while they fired on ~180k rows each.

    Only changing steps are returned. A transform that left the value alone did nothing,
    and a receipt for nothing is noise (the same rule `CleaningLedger.record` applies).

    Raises:
        DataQualityError: from the first transform that cannot express the value.
    """
    current = value
    steps: list[TransformStep] = []
    for transform in transforms:
        result = apply_transform(transform, current)
        if result != current:
            steps.append((transform, current, result))
        current = result
    return current, tuple(steps)


def apply_transforms(value: str | None, transforms: tuple[Transform, ...]) -> str | None:
    """Apply a transform chain in declared sequence, discarding the per-step receipts.

    Raises:
        DataQualityError: from the first transform that cannot express the value.
    """
    return apply_transforms_stepwise(value, transforms)[0]


def build_interval(value: str | None, binding: TemporalBindingSpec) -> TimeInterval:
    """Turn one source instant into a `TimeInterval`, widening only.

    A blank value yields the unbounded `UNKNOWN` interval with `ASSUMED` provenance -- the
    representation `CONVENTIONS.md` §10 mandates for a missing instant, and the only one
    that claims nothing. A present value is parsed under the binding's DECLARED
    `source_format` and widened to the span its declared precision denotes.

    Raises:
        DataQualityError: if a present value does not parse under the declared format. It is
            not retried against a second format: a date the declared format cannot read is
            either a different format or corrupt, and choosing between those is a guess.
    """
    source = f"mapping.temporal_bindings[{binding.column}]"
    if value is None or not value.strip():
        return TimeInterval(
            t_earliest=UNKNOWN_EARLIEST,
            t_latest=UNKNOWN_LATEST,
            precision=Precision.UNKNOWN,
            provenance=ProvenanceClass.ASSUMED,
            source=source,
        )
    try:
        parsed = datetime.strptime(value.strip(), binding.source_format)  # noqa: DTZ007
    except ValueError as failure:
        raise DataQualityError(
            f"{value!r} does not parse under the declared source_format "
            f"{binding.source_format!r}"
        ) from failure
    moment = parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    floor = _floor_to(moment, binding.precision)
    span = PRECISION_SPANS.get(binding.precision)
    if span is None:
        # UNKNOWN precision with a present value: the mapping says this column's instants
        # are not usable, and the value is discarded rather than being pinned by this code.
        return TimeInterval(
            t_earliest=UNKNOWN_EARLIEST,
            t_latest=UNKNOWN_LATEST,
            precision=Precision.UNKNOWN,
            provenance=ProvenanceClass.ASSUMED,
            source=source,
        )
    return TimeInterval(
        t_earliest=floor,
        t_latest=floor + span,
        precision=binding.precision,
        provenance=binding.provenance,
        source=source,
    )


def parse_source_instant(value: str | None, binding: TemporalBindingSpec) -> datetime | None:
    """Parse a source instant at the granularity the TEXT carries, ignoring declared precision.

    Distinct from `build_interval`, and deliberately so. `build_interval` produces the
    interval the engine may USE, which is bounded by the precision the mapping declares.
    This produces the instant the source WROTE, which is the evidence a declared precision
    is argued from.

    Using the bound interval to test a derivation would be circular: a column bound to DAY
    precision has already had its minutes discarded, so comparing it against a MINUTE-bound
    column would show a disagreement the binding itself created. That mistake was made here
    once and reported 0.07% agreement where the truth was 94.6%.

    Returns `None` for a blank or unparseable value; the caller counts it as unevaluable.
    """
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), binding.source_format)  # noqa: DTZ007
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _floor_to(moment: datetime, precision: Precision) -> datetime:
    """Truncate an instant down to the start of the unit its precision names."""
    if precision is Precision.DAY:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if precision is Precision.HOUR:
        return moment.replace(minute=0, second=0, microsecond=0)
    if precision is Precision.MINUTE:
        return moment.replace(second=0, microsecond=0)
    if precision is Precision.SECOND:
        return moment.replace(microsecond=0)
    return moment
