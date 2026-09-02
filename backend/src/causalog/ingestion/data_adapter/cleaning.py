"""Cleaning with receipts: a closed transform registry and the ledger of what it changed.

Three properties, each of which is a refusal rather than a habit.

**Raw is never modified.** Cleaning produces a new layer keyed by `dataset_version`. The
source file is opened read-only and is the same bytes afterwards. A pipeline that edits its
own evidence cannot satisfy LAW-EVIDENCE, because the record a conclusion cites no longer
says what it said when the conclusion was drawn.

**Nothing changes without a receipt, and the receipt names the rule that did it.** Every
transform that changes a value is counted against ITSELF, with its own before/after -- not
against whichever member of its chain ran first. The first change per (rule, source column)
keeps the example. The ledger is written beside the clean layer and summarised in the
data-quality report. "We trimmed some whitespace" is not a receipt; "TRIM_WHITESPACE,
`Product Name`, 1 774 rows, `'Smart watch '` -> `'Smart watch'`" is. A receipt that says
TRIM_WHITESPACE over a before/after of `'0'` -> `'false'` is worse than no receipt, because
it is a plausible-looking lie about the provenance of a value: that was a real defect here,
and `apply_transforms_stepwise` is the fix.

**Counts are per SOURCE COLUMN, not per binding.** A column bound more than once (DataCo
binds twelve of them, up to three times each) is cleaned once and counted once. Counting
per binding reported 189 748 changed rows in a 180 519-row dataset -- an arithmetic
impossibility on the face of the published report.

**No timestamp is ever imputed.** This is the load-bearing one. The registry contains no
transform that narrows an instant, and `build_interval` can only WIDEN a parsed value into
the interval it actually denotes or, for a blank, return the unbounded UNKNOWN interval with
`ASSUMED` provenance. There is deliberately no code path from a coarse or absent instant to
a point one. `TimeInterval` refuses `INFERRED` + `EXACT` at construction, and
`tests/law/test_cleaning_never_imputes_time.py` additionally enumerates this registry and
asserts no member can produce `EXACT` from anything coarser (`CONVENTIONS.md` §10,
ADR-0021).

A transform that cannot express a value raises `core.errors.DataQualityError` -- the
existing member of the closed taxonomy for exactly this (`CONVENTIONS.md` §7). A new
exception class here would widen a taxonomy that is closed on purpose, to say something the
existing member already says.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.provenance import ProvenanceClass
from causalog.ingestion.schema_mapper.dsl import Transform

# Re-exported, not reimplemented. The transform registry and the interval builder are
# MAPPING semantics and now live with the DSL they interpret, because module 2's own record
# mapper needs them too and reaching them through module 1 would be a cycle
# (`CONVENTIONS.md` §6). Module 1's public surface is unchanged: every name this module
# exported before still resolves here.
from causalog.ingestion.schema_mapper.transforms import (
    PRECISION_SPANS,
    TransformStep,
    apply_transform,
    apply_transforms,
    apply_transforms_stepwise,
    build_interval,
    parse_source_instant,
)

__all__ = [
    "PRECISION_SPANS",
    "TRANSFORM_RATIONALE",
    "CleaningAction",
    "CleaningLedger",
    "TransformStep",
    "apply_transform",
    "apply_transforms",
    "apply_transforms_stepwise",
    "build_interval",
    "parse_source_instant",
]


#: Why each transform exists, carried into the ledger so a receipt explains itself.
TRANSFORM_RATIONALE: Final[dict[Transform, str]] = {
    Transform.IDENTITY: "no change; the value is carried through exactly as the source wrote it",
    Transform.TRIM_WHITESPACE: (
        "leading and trailing whitespace is a formatting artefact, and two values differing "
        "only by it would otherwise mint two identifiers for one thing"
    ),
    Transform.NORMALIZE_UNICODE_NFC: (
        "the same accented character has several encodings; without one normal form, "
        "content addressing produces two identifiers for one value"
    ),
    Transform.UPPERCASE: "case-folded so a categorical value does not split on capitalisation",
    Transform.EMPTY_TO_NULL: (
        "an empty string is an absent value, and recording it as the empty string would "
        "make 'no value' indistinguishable from 'the empty value'"
    ),
    Transform.PARSE_INTEGER: "the declared type is INTEGER; a value that is not one is a defect",
    Transform.PARSE_DECIMAL: "the declared type is DECIMAL; a value that is not one is a defect",
    Transform.PARSE_BOOLEAN_FLAG: "the declared type is a flag with two admissible values",
    Transform.PARSE_DATE_TO_DAY: (
        "a date names a whole day, so it WIDENS into the interval that day spans; it is "
        "never narrowed to an instant, which would be imputation (CONVENTIONS.md §10)"
    ),
    Transform.PARSE_DATETIME_TO_MINUTE: (
        "a minute-granular instant WIDENS into the sixty seconds it spans; the seconds the "
        "source did not record are not invented"
    ),
}


class CleaningAction(BaseModel):
    """One receipt: what a rule changed, in which column, how often, with an example."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(min_length=1)
    column: str = Field(min_length=1)
    rows_affected: int = Field(ge=0)
    before_sample: str | None
    after_sample: str | None
    rationale: str = Field(min_length=1)
    provenance: ProvenanceClass


class CleaningLedger:
    """Accumulate cleaning receipts in bounded memory.

    One entry per `(rule, column)` with a running count and the FIRST observed change as the
    example. First rather than last, and first rather than random: a reproducible example is
    part of a reproducible report (`CONVENTIONS.md` §11).
    """

    def __init__(self) -> None:
        """Start an empty ledger."""
        self._counts: dict[tuple[str, str], int] = {}
        self._examples: dict[tuple[str, str], tuple[str | None, str | None]] = {}
        self._provenance: dict[tuple[str, str], ProvenanceClass] = {}

    def record(
        self,
        rule_id: str,
        column: str,
        before: str | None,
        after: str | None,
        provenance: ProvenanceClass = ProvenanceClass.OBSERVED,
    ) -> None:
        """Record one change. A no-op change is not recorded; a receipt for nothing is noise."""
        if before == after:
            return
        key = (rule_id, column)
        self._counts[key] = self._counts.get(key, 0) + 1
        self._provenance.setdefault(key, provenance)
        self._examples.setdefault(key, (before, after))

    def actions(self) -> tuple[CleaningAction, ...]:
        """Return every receipt, sequenced by `(rule_id, column)` for a stable report."""
        return tuple(
            CleaningAction(
                rule_id=rule_id,
                column=column,
                rows_affected=count,
                before_sample=self._examples[(rule_id, column)][0],
                after_sample=self._examples[(rule_id, column)][1],
                rationale=_rationale_for(rule_id),
                provenance=self._provenance[(rule_id, column)],
            )
            for (rule_id, column), count in sorted(self._counts.items())
        )


def _rationale_for(rule_id: str) -> str:
    """Return the registered rationale for a transform name, or a stated fallback."""
    for transform, rationale in TRANSFORM_RATIONALE.items():
        if transform.value == rule_id:
            return rationale
    return f"{rule_id} is not a registered transform; its rationale is unrecorded"
