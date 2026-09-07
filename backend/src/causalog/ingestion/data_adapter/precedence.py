"""Project measured derivation checks into the value type a reasoning module consults.

`DerivationResult` is this package's own measurement type: it carries counts, a residual
histogram, and the audit's bookkeeping. `DerivedPrecedence` is the L0 value a confidence
scorer reads. They are deliberately not the same type -- the scorer has no business holding
`unevaluable`, and this package has no business knowing what a scorer does with a rate.

This function is the whole of the seam, and it is a projection with three refusals rather
than a conversion. Every refusal turns an entry that would MISLEAD downstream into an entry
that is simply absent, and each one is a different mistake:

  * **Nothing evaluable.** `agreement_rate` divides by `evaluated` and answers `0.0` when
    that is zero. The zero is a division guard, not a measurement, and carrying it forward
    would hand downstream a "never tested" wearing the clothes of "tested and found false".
    The adapter's own finding path skips these for the same reason.
  * **No day count.** A check without one asserts two columns hold the SAME instant. That is
    a duplicated column, not a derived precedence, and `DerivedPrecedence` refuses it at
    construction anyway -- caught here so a legitimate mapping does not raise.
  * **Below the confirmation threshold.** The mapping SUSPECTED a derivation and the data
    did not bear it out. That is a finding about the mapping, which the adapter already
    reports; it is not grounds for depressing anybody's confidence.

The direction is the load-bearing detail. `column` is the derived one -- the instant the
source COMPUTED -- and `equals_column` is what it was computed from, so `equals_column`
supplies the cause side and `column` the effect side. A pair stored the other way round
would flag precedence the measurement never claimed.
"""

from __future__ import annotations

from causalog.core.precedence import (
    DerivedPrecedence,
    DerivedPrecedenceIndex,
    temporal_binding_source,
)
from causalog.ingestion.data_adapter.adapter import DERIVATION_CONFIRMED_RATE
from causalog.ingestion.data_adapter.validate import DerivationResult

__all__ = ["derived_precedence_index"]


def derived_precedence_index(
    results: tuple[DerivationResult, ...],
    confirmed_rate: float = DERIVATION_CONFIRMED_RATE,
) -> DerivedPrecedenceIndex:
    """Return the index of every derivation this run measured and confirmed.

    An EMPTY index is a real answer -- the measurement ran and confirmed nothing. Callers
    say "no measurement was supplied" by holding `None` in place of an index, never by
    passing an empty tuple here.

    `confirmed_rate` is a parameter rather than a constant read inline so a test can pin the
    boundary from both sides without reaching into module state.
    """
    entries = tuple(
        DerivedPrecedence(
            check_id=result.check_id,
            cause_interval_source=temporal_binding_source(result.equals_column),
            effect_interval_source=temporal_binding_source(result.column),
            agreement_rate=result.agreement_rate,
            evaluated=result.evaluated,
            residual_seconds=result.residual_seconds,
            residuals_exact=result.residuals_exact,
            rationale=result.rationale,
        )
        for result in results
        if result.evaluated > 0
        and result.plus_days_column is not None
        and result.agreement_rate >= confirmed_rate
    )
    return DerivedPrecedenceIndex.of(entries)
