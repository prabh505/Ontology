"""What a data-quality finding IS, and the closed registry of rules that produce them.

Every rule is declared here with four things: a stable machine code, the dimension it
belongs to, a severity, and -- the field that makes this module worth having -- a
`downstream_consequence` naming what stops working. `min_length=1` on that field means a
rule cannot be registered without one. The requirement is therefore structural rather than a
convention that erodes on the third busy afternoon.

Severity is `ontology_runtime.diagnostics.Severity`, not a second vocabulary of its own.
`ERROR` / `WARNING` / `NOT_RUNNABLE` already carry exactly the right three meanings, and
`NOT_RUNNABLE` is the one this module could least afford to invent badly: a check that could
not run must never be indistinguishable from a check that passed (DEF-0001, OQ-014).

The severity split follows the mandate literally
------------------------------------------------
**Fail loudly on ontology violations; warn on statistical anomalies.** A row contradicting
the declared state machine, or referencing an identity that does not exist, is an `ERROR`
and is quarantined. A value outside an interquartile fence is a `WARNING` and is carried
forward untouched -- an outlier is a fact about the world at least as often as it is a
defect, and quarantining one would be the engine editing its own evidence.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.ontology_runtime.diagnostics import Severity

__all__ = [
    "RULES",
    "Dimension",
    "Finding",
    "RuleSpec",
    "rule",
]


class Dimension(str, Enum):
    """Which kind of integrity a rule is about."""

    SOURCE = "SOURCE"
    STRUCTURAL = "STRUCTURAL"
    DISTRIBUTION = "DISTRIBUTION"
    TEMPORAL = "TEMPORAL"
    REFERENTIAL = "REFERENTIAL"
    CONTRADICTION = "CONTRADICTION"
    CLEANING = "CLEANING"


class RuleSpec(BaseModel):
    """One registered validation rule: what it checks and what its failure costs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    dimension: Dimension
    severity: Severity
    title: str = Field(min_length=1)
    downstream_consequence: str = Field(min_length=1)
    """What stops working downstream, named concretely. Never empty -- a finding without a
    consequence is an observation, and observations are what reports get ignored for."""
    quarantines_row: bool = False
    """Whether a row triggering this rule is withheld from the clean layer. Only ever true
    for `ERROR`; a warning that removed data would be a silent drop under another name."""


class Finding(BaseModel):
    """One occurrence of one rule, with its subject and its count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    dimension: Dimension
    severity: Severity
    subject: str
    """What the finding is about: a column, a declared constraint, or the dataset itself."""
    detail: str = Field(min_length=1)
    occurrences: int = Field(ge=0)
    downstream_consequence: str = Field(min_length=1)
    example_rows: tuple[int, ...] = ()
    """Up to a few 1-based source row numbers, so a reader can go and look."""

    def render(self) -> str:
        """Return the one-line form."""
        return (
            f"[{self.severity.value}] {self.code} {self.subject} "
            f"({self.occurrences}): {self.detail} => {self.downstream_consequence}"
        )


def _spec(
    code: str,
    dimension: Dimension,
    severity: Severity,
    title: str,
    downstream_consequence: str,
    *,
    quarantines_row: bool = False,
) -> RuleSpec:
    """Build one registry entry."""
    return RuleSpec(
        code=code,
        dimension=dimension,
        severity=severity,
        title=title,
        downstream_consequence=downstream_consequence,
        quarantines_row=quarantines_row,
    )


#: The closed rule registry. Adding a rule means adding a row here, which means stating its
#: consequence; there is no path to a finding that does not carry one.
RULES: Final[dict[str, RuleSpec]] = {
    spec.code: spec
    for spec in (
        _spec(
            "DQ-SRC-ENCODING-FALLBACK",
            Dimension.SOURCE,
            Severity.WARNING,
            "the file is not valid UTF-8 and a fallback codec was used",
            "Text values were decoded with a single-byte codec chosen by probe. If the "
            "publisher's true encoding differs, accented characters become plausible but "
            "wrong text, and every identifier content-addressed over that text differs "
            "from the identifier the correct decoding would produce.",
        ),
        _spec(
            "DQ-SRC-DIALECT-UNSNIFFED",
            Dimension.SOURCE,
            Severity.WARNING,
            "the delimiter could not be sniffed and the documented default was used",
            "A wrong delimiter parses the file into one column per row, which surfaces as "
            "a profile of near-total nulls rather than as an error.",
        ),
        _spec(
            "DQ-STR-FIELD-COUNT",
            Dimension.STRUCTURAL,
            Severity.ERROR,
            "the row's field count disagrees with the header",
            "Fields after the disagreement are attributed to the wrong columns, so every "
            "value in the row is suspect. Quarantined rather than realigned by guess.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-STR-UNPARSEABLE",
            Dimension.STRUCTURAL,
            Severity.ERROR,
            "a required bound value does not parse under its declared transform",
            "Module 3 or 4 would receive a hole where a required attribute belongs. "
            "Filling it with a default would be an invented observation, so the row is "
            "quarantined instead.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-STR-BLANK-REQUIRED",
            Dimension.STRUCTURAL,
            Severity.ERROR,
            "a required bound column is blank",
            "The same hole as an unparseable value, arriving as absence rather than as "
            "malformation. Quarantined; never defaulted.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-STR-COLUMN-ALL-BLANK",
            Dimension.STRUCTURAL,
            Severity.WARNING,
            "a column carries no value in any row",
            "Every binding through this column yields nothing for the whole dataset. If "
            "the ontology declares an attribute from it, that attribute is absent "
            "everywhere and any measurement reading it is unavailable.",
        ),
        _spec(
            "DQ-DST-OUTLIERS",
            Dimension.DISTRIBUTION,
            Severity.WARNING,
            "values fall outside the interquartile fence",
            "Carried forward untouched. An outlier is a fact about the world at least as "
            "often as it is a defect, and any measurement that aggregates this column is "
            "sensitive to it -- inspect before trusting a mean.",
        ),
        _spec(
            "DQ-DST-CARDINALITY-INEXACT",
            Dimension.DISTRIBUTION,
            Severity.NOT_RUNNABLE,
            "the distinct-value count hit its cap and stopped being exact",
            "The reported cardinality is a floor, not a count. Any judgement that reads it "
            "as a count -- 'this column is categorical' -- is unsupported for this column.",
        ),
        _spec(
            "DQ-TMP-GRANULARITY",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "a temporal column pins instants no finer than a calendar day",
            "Every interval built from this column spans a whole day, so two events on one "
            "date OVERLAP and `causalog.core.temporal.verdict` returns UNDETERMINED. No "
            "intra-day causal edge can ever be promoted to INFERRED. This is risk R-14 "
            "made measurable rather than predicted.",
        ),
        _spec(
            "DQ-TMP-NO-OFFSET",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "a temporal column states no UTC offset",
            "The interval is stamped ASSUMED rather than OBSERVED provenance under the "
            "mapping's declared timezone policy. If the source is not really UTC, every "
            "instant is displaced by an unknown constant and cross-source precedence is "
            "unsound.",
        ),
        _spec(
            "DQ-TMP-MISSING",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "a temporal column is blank",
            "The instant becomes UNKNOWN precision with ASSUMED provenance and unbounded "
            "bounds -- never a guessed value (CONVENTIONS.md §10). LAW-TIME can return no "
            "verdict for it, so the event participates in no causal edge.",
        ),
        _spec(
            "DQ-TMP-UNPARSEABLE",
            Dimension.TEMPORAL,
            Severity.ERROR,
            "a temporal value does not parse under its declared source_format",
            "A date the declared format cannot read is either a different format or a "
            "corrupt value, and both readings are guesses. Quarantined rather than "
            "reparsed by a second format nobody declared.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-TMP-PRECEDENCE-VIOLATION",
            Dimension.TEMPORAL,
            Severity.ERROR,
            "a declared precedence pair is inverted",
            "The later instant precedes the earlier one, so the row asserts an impossible "
            "sequence. Admitting it would let module 9 build an edge whose LAW-TIME "
            "verdict is VIOLATION. Quarantined.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-TMP-PRECEDENCE-EQUAL",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "a declared precedence pair holds on the same instant",
            "Not an inversion -- at day granularity it is the expected case. The pair is "
            "temporally inseparable, so the edge between them is UNDETERMINED and cannot "
            "be promoted. Counted so the size of R-14's exposure is known.",
        ),
        _spec(
            "DQ-TMP-DERIVED-PRECISION",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "a temporal column's sub-day component is arithmetic on another column",
            "The column carries SPURIOUS PRECISION: its minutes were copied from another "
            "instant, not measured. Sequencing two events by them would sequence them by a "
            "number the source manufactured, which is the failure LAW-TIME exists to "
            "prevent -- arriving through a column that looks precise rather than one that "
            "looks coarse. The mapping must declare this column at DAY precision; declaring "
            "the precision the text displays would let imputation in through a format.",
        ),
        _spec(
            "DQ-TMP-DERIVATION-UNCONFIRMED",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "a declared derivation check did not hold often enough to support it",
            "The mapping DECLARED that this column's value is arithmetic on another and the "
            "measurement does not bear that out. Either the declared arithmetic is wrong, or "
            "the column really is independently observed. Until that is resolved, any "
            "precision decision the mapping justified by this check is unsupported -- and a "
            "precision widened for a reason that turned out to be false is still a "
            "precision that discards real information.",
        ),
        _spec(
            "DQ-TMP-DERIVATION-RESIDUAL",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "a declared derivation misses by a small number of constant offsets",
            "A derivation that misses by a HANDFUL OF CONSTANTS has not failed -- it has "
            "revealed a second construction rule. Measured values, by contrast, miss by a "
            "spread. Either way the affected rows carry an instant that was computed and "
            "looks entirely valid, so nothing downstream can detect them. The residual "
            "histogram is reported so a reader can tell the two apart rather than being "
            "told which it is.",
        ),
        _spec(
            "DQ-TMP-DUPLICATE-INSTANT",
            Dimension.TEMPORAL,
            Severity.WARNING,
            "one identity carries several rows at one instant",
            "The rows are temporally inseparable, so no precedence among them is recoverable "
            "from the data. Any sequence a downstream module shows for them is a rendering "
            "choice and must never be read as precedence.",
        ),
        _spec(
            "DQ-REF-ORPHAN-KEY",
            Dimension.REFERENTIAL,
            Severity.ERROR,
            "a foreign key references an identity that appears nowhere",
            "Module 7 would resolve a relationship to a non-existent entity, producing a "
            "dangling edge in the temporal graph. Quarantined.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-REF-DUPLICATE-IDENTITY",
            Dimension.REFERENTIAL,
            Severity.WARNING,
            "one identifying key carries conflicting attribute values across rows",
            "Module 3 mints one content-addressed entity per key, so one of the conflicting "
            "readings silently wins. Which one is a function of row sequence, not of truth.",
        ),
        _spec(
            "DQ-CON-UNKNOWN-STATE",
            Dimension.CONTRADICTION,
            Severity.ERROR,
            "a value maps to no state the ontology's lifecycle declares",
            "The row asserts the entity is in a state the state machine does not have. "
            "Module 6 could build no transition into or out of it. Quarantined.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-CON-UNREACHABLE-STATE",
            Dimension.CONTRADICTION,
            Severity.ERROR,
            "a declared state is unreachable by any declared transition",
            "The row claims a state the lifecycle admits but cannot arrive at. Either the "
            "data or the pack is wrong, and nothing here can say which -- so the row is "
            "quarantined and the pack's state machine is flagged for review (risk R-16).",
            quarantines_row=True,
        ),
        _spec(
            "DQ-CON-UNMAPPED-VALUE",
            Dimension.CONTRADICTION,
            Severity.ERROR,
            "a source value has no binding and the policy is ERROR",
            "Passing it through or defaulting it would put an uninterpreted domain value "
            "into the engine, which is risk R-07 exactly. Quarantined.",
            quarantines_row=True,
        ),
        _spec(
            "DQ-CLN-APPLIED",
            Dimension.CLEANING,
            Severity.WARNING,
            "a cleaning transform changed values",
            "Values downstream differ from the bytes on disk. The cleaning ledger records "
            "every change with its rule, its count, and a before/after example, so the "
            "difference is auditable rather than assumed benign.",
        ),
        _spec(
            "DQ-CLN-TIME-ASSUMED",
            Dimension.CLEANING,
            Severity.WARNING,
            "a temporal transform had to assume something the source did not state",
            "The resulting interval carries ASSUMED rather than OBSERVED provenance, and "
            "ADR-0021 bars an ASSUMED-bounded pair from ever yielding a CERTAIN verdict "
            "when either side is INFERRED. The assumption is named in the report.",
        ),
    )
}


def rule(code: str) -> RuleSpec:
    """Return one registered rule.

    Raises:
        KeyError: if the code is not registered. Deliberately not a soft lookup -- an
            unregistered code would produce a finding with no stated consequence, which is
            the one thing this module exists to make impossible.
    """
    return RULES[code]
