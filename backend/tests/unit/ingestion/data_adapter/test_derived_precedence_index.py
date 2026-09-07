"""Projecting a measured derivation into the L0 value a scorer reads (ADR-0057).

The seam has exactly three refusals, and each one turns an entry that would MISLEAD a
downstream scorer into an entry that is simply absent. They are tested one at a time because
a single "bad input yields empty" test would pass even if two of the three were missing.

The confirmed case is pinned against the numbers module 1 actually measured on the shipped
dataset, so a change to the projection shows up as a diff against reality rather than
against a fixture invented to match the code.
"""

from __future__ import annotations

import pytest

from causalog.core.precedence import temporal_binding_source
from causalog.ingestion.data_adapter.precedence import derived_precedence_index
from causalog.ingestion.data_adapter.validate import DerivationResult

#: The shipped pack's own check, with the counts the committed report records for it.
MATCHES = 170782
MISMATCHES = 9737
EARLIER_COLUMN = "column_a"
DERIVED_COLUMN = "column_b"


def _result(
    matches: int = MATCHES,
    mismatches: int = MISMATCHES,
    plus_days_column: str | None = "day_count",
) -> DerivationResult:
    """Return one measured check, varying only what a test cares about."""
    return DerivationResult(
        check_id="CHECK_ONE",
        column=DERIVED_COLUMN,
        equals_column=EARLIER_COLUMN,
        plus_days_column=plus_days_column,
        rationale="the later instant is suspected of being computed from the earlier one",
        matches=matches,
        mismatches=mismatches,
        unevaluable=0,
        residual_seconds=((43200, 5080), (-43200, 4657)),
        residuals_exact=True,
    )


def test_a_confirmed_check_becomes_one_directed_entry() -> None:
    """The measured agreement and its denominator survive the projection intact."""
    index = derived_precedence_index((_result(),))

    (entry,) = index.entries
    assert entry.check_id == "CHECK_ONE"
    assert entry.agreement_rate == pytest.approx(MATCHES / (MATCHES + MISMATCHES))
    assert entry.evaluated == MATCHES + MISMATCHES
    assert entry.residual_seconds == ((43200, 5080), (-43200, 4657))


def test_the_derived_column_supplies_the_effect_side_and_never_the_cause_side() -> None:
    """Direction is the whole claim: the COMPUTED instant is the later one.

    Stored the other way round, the index would depress confidence on the reverse
    precedence -- something the measurement never claimed.
    """
    index = derived_precedence_index((_result(),))

    assert (
        index.precedence_for(
            temporal_binding_source(EARLIER_COLUMN), temporal_binding_source(DERIVED_COLUMN)
        )
        is not None
    )
    assert (
        index.precedence_for(
            temporal_binding_source(DERIVED_COLUMN), temporal_binding_source(EARLIER_COLUMN)
        )
        is None
    )


def test_a_check_with_no_evaluable_rows_is_refused_rather_than_read_as_disconfirmed() -> None:
    """`agreement_rate` answers 0.0 by division guard; that is not a measurement of zero."""
    index = derived_precedence_index((_result(matches=0, mismatches=0),))

    assert index.entries == ()


def test_a_check_without_a_day_count_is_refused() -> None:
    """Two columns asserted to hold the same instant is a duplicated column, not a precedence."""
    index = derived_precedence_index((_result(plus_days_column=None),))

    assert index.entries == ()


def test_a_check_the_data_did_not_bear_out_is_refused() -> None:
    """Below the threshold the mapping's suspicion is unsupported, which the adapter reports.

    It is not grounds for depressing anyone's confidence, so no entry is produced.
    """
    index = derived_precedence_index((_result(matches=1, mismatches=99),))

    assert index.entries == ()


def test_the_confirmation_threshold_is_inclusive_at_its_boundary() -> None:
    """Pinned from both sides, so a later change to the comparison is visible."""
    assert derived_precedence_index((_result(matches=50, mismatches=50),), 0.5).entries != ()
    assert derived_precedence_index((_result(matches=49, mismatches=51),), 0.5).entries == ()


def test_no_checks_at_all_yields_an_empty_index_and_not_an_error() -> None:
    """Supplied-and-empty is a legitimate answer: measured, and nothing confirmed.

    A caller says "not measured" by holding `None` instead of an index, never by arriving here.
    """
    assert derived_precedence_index(()).entries == ()
