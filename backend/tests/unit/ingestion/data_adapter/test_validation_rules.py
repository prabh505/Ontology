"""One positive and one negative case per validation rule (`CONVENTIONS.md` §3, §14).

Positive = the rule does NOT fire on data that satisfies it. Negative = the rule DOES fire
on data that violates it. Both are needed: a rule that never fires passes every positive
case, and DEF-0001 is this repository's record of exactly that going unnoticed.

Assertions are on `code`, never on message text. Asserting on prose makes rewording a
message a test failure, which is how validators end up with messages nobody dares improve.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from causalog.core.errors import DataQualityError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision
from causalog.ingestion.data_adapter import RULES, build_interval
from causalog.ingestion.data_adapter.validate import IdentityIndex, RowValidator
from causalog.ingestion.schema_mapper import (
    ColumnBindingSpec,
    IdentityBindingSpec,
    PrecedencePairSpec,
    ReferentialConstraintSpec,
    SchemaMappingSpec,
    TargetKind,
    TemporalBindingSpec,
    Transform,
    UnmappedValuePolicy,
)
from causalog.ingestion.schema_mapper.dsl import ValueBindingSpec
from causalog.ontology_runtime.diagnostics import Severity

HEADER = ("key", "ref", "start", "finish", "status", "count")


def _mapping(**overrides: object) -> SchemaMappingSpec:
    """Build a small, domain-neutral mapping exercising every declared check kind."""
    base: dict[str, object] = {
        "mapping_schema_version": "1.0.0",
        "mapping_id": "probe",
        "mapping_version": "1.0.0",
        "ontology_pack": "probe",
        "description": "A synthetic mapping used only to exercise the validators.",
        "column_bindings": (
            ColumnBindingSpec(
                column="key",
                target_kind=TargetKind.ENTITY_ATTRIBUTE,
                entity_type="THING",
                attribute="thing_reference",
                required=True,
            ),
            ColumnBindingSpec(
                column="count",
                target_kind=TargetKind.ENTITY_ATTRIBUTE,
                entity_type="THING",
                attribute="thing_count",
                transforms=(Transform.PARSE_INTEGER,),
                required=True,
            ),
        ),
        "identity_bindings": (IdentityBindingSpec(entity_type="THING", key_columns=("key",)),),
        "temporal_bindings": (
            TemporalBindingSpec(column="start", source_format="%Y-%m-%d", precision=Precision.DAY),
            TemporalBindingSpec(column="finish", source_format="%Y-%m-%d", precision=Precision.DAY),
        ),
        "precedence_pairs": (
            PrecedencePairSpec(
                id="START_BEFORE_FINISH",
                earlier_column="start",
                later_column="finish",
                rationale="A thing cannot finish before it starts.",
            ),
        ),
        "referential_constraints": (
            ReferentialConstraintSpec(
                id="REF_EXISTS",
                column="ref",
                references_entity_type="THING",
                rationale="A reference must name a thing the dataset carries.",
            ),
        ),
        "value_bindings": (
            ValueBindingSpec(
                column="status",
                values=(("open", "OPEN"), ("shut", "SHUT")),
                unmapped_value_policy=UnmappedValuePolicy.ERROR,
            ),
        ),
    }
    base.update(overrides)
    return SchemaMappingSpec.model_validate(base)


class _Pack:
    """The narrowest stand-in for a `ResolvedPack` the validator actually reads."""

    entity_types: tuple[object, ...] = ()


def _validator(rows: list[dict[str, str]]) -> RowValidator:
    """Build a validator whose identity index has seen every supplied row."""
    mapping = _mapping()
    index = IdentityIndex(mapping)
    for row in rows:
        index.observe(row)
    return RowValidator(mapping, _Pack(), index, HEADER)  # type: ignore[arg-type]


def _row(**overrides: str) -> dict[str, str]:
    """A row that satisfies every rule, before any override."""
    clean = {
        "key": "K1",
        "ref": "K1",
        "start": "2020-01-01",
        "finish": "2020-01-05",
        "status": "open",
        "count": "3",
    }
    clean.update(overrides)
    return clean


def _codes(row: dict[str, str], *, surplus: int = 0) -> set[str]:
    """Return the codes one row triggers, against an index that has seen it."""
    issues, _intervals = _validator([row]).check(row, surplus)
    return {issue.code for issue in issues}


# --------------------------------------------------------------------------------------
# Every registered rule must be reachable, and every quarantining rule must be an ERROR.
# --------------------------------------------------------------------------------------


def test_every_registered_rule_states_a_downstream_consequence() -> None:
    for code, spec in RULES.items():
        assert spec.downstream_consequence.strip(), f"{code} has no stated consequence"


def test_only_error_rules_quarantine() -> None:
    for code, spec in RULES.items():
        if spec.quarantines_row:
            assert spec.severity is Severity.ERROR, (
                f"{code} removes a row from the clean layer at severity "
                f"{spec.severity.value}; a warning that deletes data is a silent drop."
            )


# --------------------------------------------------------------------------------------
# Structural
# --------------------------------------------------------------------------------------


def test_field_count_positive() -> None:
    assert "DQ-STR-FIELD-COUNT" not in _codes(_row())


def test_field_count_negative() -> None:
    assert "DQ-STR-FIELD-COUNT" in _codes(_row(), surplus=2)


def test_blank_required_positive() -> None:
    assert "DQ-STR-BLANK-REQUIRED" not in _codes(_row())


def test_blank_required_negative() -> None:
    assert "DQ-STR-BLANK-REQUIRED" in _codes(_row(key=""))


# --------------------------------------------------------------------------------------
# Temporal
# --------------------------------------------------------------------------------------


def test_precedence_positive() -> None:
    assert "DQ-TMP-PRECEDENCE-VIOLATION" not in _codes(_row())


def test_precedence_negative() -> None:
    assert "DQ-TMP-PRECEDENCE-VIOLATION" in _codes(_row(start="2020-01-05", finish="2020-01-01"))


def test_precedence_equal_is_reported_separately_from_an_inversion() -> None:
    codes = _codes(_row(start="2020-01-01", finish="2020-01-01"))
    assert "DQ-TMP-PRECEDENCE-EQUAL" in codes
    assert "DQ-TMP-PRECEDENCE-VIOLATION" not in codes


def test_temporal_missing_positive() -> None:
    assert "DQ-TMP-MISSING" not in _codes(_row())


def test_temporal_missing_negative() -> None:
    assert "DQ-TMP-MISSING" in _codes(_row(start=""))


def test_temporal_unparseable_positive() -> None:
    assert "DQ-TMP-UNPARSEABLE" not in _codes(_row())


def test_temporal_unparseable_negative() -> None:
    assert "DQ-TMP-UNPARSEABLE" in _codes(_row(start="01/01/2020"))


# --------------------------------------------------------------------------------------
# Referential
# --------------------------------------------------------------------------------------


def test_orphan_key_positive() -> None:
    assert "DQ-REF-ORPHAN-KEY" not in _codes(_row())


def test_orphan_key_negative() -> None:
    row = _row(ref="NOT-A-KEY")
    assert "DQ-REF-ORPHAN-KEY" in _codes(row)


def test_a_forward_reference_is_not_an_orphan() -> None:
    """The index is built over the WHOLE file before any row is judged."""
    later = _row(key="K2", ref="K2")
    earlier = _row(key="K1", ref="K2")
    validator = _validator([earlier, later])
    issues, _intervals = validator.check(earlier, 0)
    assert "DQ-REF-ORPHAN-KEY" not in {issue.code for issue in issues}


def test_duplicate_identity_negative() -> None:
    mapping = _mapping()
    index = IdentityIndex(mapping)
    index.observe(_row(count="3"))
    index.observe(_row(count="9"))
    assert index.conflicts()[0][0] == "THING"


def test_duplicate_identity_positive() -> None:
    mapping = _mapping()
    index = IdentityIndex(mapping)
    index.observe(_row(count="3"))
    index.observe(_row(count="3"))
    assert index.conflicts() == ()


# --------------------------------------------------------------------------------------
# Contradiction
# --------------------------------------------------------------------------------------


def test_unmapped_value_positive() -> None:
    assert "DQ-CON-UNMAPPED-VALUE" not in _codes(_row())


def test_unmapped_value_negative() -> None:
    assert "DQ-CON-UNMAPPED-VALUE" in _codes(_row(status="ajar"))


def test_an_unmapped_value_is_never_defaulted() -> None:
    """It is an error, not a pass-through. Risk R-07 is precisely this failure."""
    issues, _intervals = _validator([_row()]).check(_row(status="ajar"), 0)
    offending = [issue for issue in issues if issue.code == "DQ-CON-UNMAPPED-VALUE"]
    assert offending and "ajar" in offending[0].detail


# --------------------------------------------------------------------------------------
# Cleaning transforms
# --------------------------------------------------------------------------------------


def test_parse_integer_positive() -> None:
    assert "DQ-STR-UNPARSEABLE" not in _codes(_row(count="12"))


def test_an_unparseable_required_value_raises_rather_than_returning_a_sentinel() -> None:
    from causalog.ingestion.data_adapter import apply_transforms

    with pytest.raises(DataQualityError):
        apply_transforms("three", (Transform.PARSE_INTEGER,))


def test_a_blank_becomes_the_unbounded_unknown_interval_and_never_a_guess() -> None:
    binding = TemporalBindingSpec(column="start", source_format="%Y-%m-%d", precision=Precision.DAY)
    interval = build_interval("", binding)
    assert interval.precision is Precision.UNKNOWN
    assert interval.provenance is ProvenanceClass.ASSUMED


def test_a_day_value_widens_to_the_whole_day_it_denotes() -> None:
    binding = TemporalBindingSpec(column="start", source_format="%Y-%m-%d", precision=Precision.DAY)
    interval = build_interval("2020-01-01", binding)
    assert interval.t_earliest == datetime(2020, 1, 1, tzinfo=UTC)
    assert interval.t_latest.date() == datetime(2020, 1, 1, tzinfo=UTC).date()
    assert interval.t_latest > interval.t_earliest
