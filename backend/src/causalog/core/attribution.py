"""Combination of attributed magnitudes over a consequence SET, without double counting.

**Why this is at `L0` and not in `causal_engine`.** `scripts/check_metrics_are_declared.py`
refuses inline arithmetic bound to a metric name inside the reasoning packages, and it is
right to: a formula written there does not move when the domain is swapped, which is
LAW-DOMAIN defeated by a value rather than by a word (`CONVENTIONS.md` §6a). The sanctioned
alternative that lint exists to push code toward is a generic routine that never mentions a
metric, held in `core/` -- the exemption `core/aggregation.py` and `core/measurement.py`
already hold, for this reason and no other. Nothing below knows what is being combined,
what unit it is in, or what it is a magnitude OF.

**The one idea this module exists to enforce: attribute to nodes, never to paths.**

A consequence reachable by two routes is one consequence. If a magnitude were accumulated
along paths, a diamond -- one origin, two intermediates, one shared consequence -- would
count that consequence twice, and a graph with many parallel routes would report an
attributed total that exceeds any quantity anyone measured. So the unit of accumulation is
the **set of reachable nodes**, each contributing its magnitude exactly once, and the
routes are reported separately as structure rather than being summed as quantity.

This composes correctly with the share a node's magnitude is already split into. A node
with several incoming claims has its magnitude apportioned among them by
`PropagationWeight`, whose contributing weights sum to one over a single consequence. Each
node therefore offers **one** magnitude to the set regardless of how many claims reach it,
and `share_of` exists so a caller can take one claim's portion of that single magnitude
rather than re-reading the whole of it per claim.

**The combination operator is declared, never assumed.** Whether two consequences'
magnitudes add, or the larger stands for both, is domain policy: two currency figures over
distinct subjects add, two elapsed-time figures over overlapping periods do not. The
operator arrives here as a name drawn from the same closed set the ontology's measurement
expressions use, so a pack author reads one vocabulary rather than two. A caller with no
declaration must report that the policy cannot run; there is deliberately no default here
to fall back to.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES

__all__ = [
    "COMBINATION_OPERATORS",
    "combine_magnitudes",
    "difference_of",
    "share_of",
]

#: The operators a caller may declare for combining magnitudes across a consequence set.
#: A strict subset of the ontology's nine, named identically so a pack author reads one
#: vocabulary. The five omitted ones are omitted deliberately: `CONSTANT` and `ATTRIBUTE`
#: are leaves rather than combinations, and `DIFFERENCE`, `PRODUCT` and `RATIO` are not
#: n-ary over an unordered set -- a set has no first element for them to be relative to,
#: so admitting one would make the result depend on iteration sequence.
COMBINATION_OPERATORS: Final[frozenset[str]] = frozenset({"SUM", "MINIMUM", "MAXIMUM"})


def _quantize(value: float) -> float:
    """Return the value at the canonical float resolution (`CONVENTIONS.md` §11)."""
    quantum = Decimal(1).scaleb(-FLOAT_QUANTIZATION_PLACES)
    return float(Decimal(repr(value)).quantize(quantum))


def combine_magnitudes(readings: Sequence[float], operator_name: str) -> float | None:
    """Combine one reading per consequence under a declared operator.

    The caller is responsible for having already reduced its consequences to a SET -- one
    reading per node, never one per route. This function cannot check that for the caller
    and does not try to; it is asserted where the set is built, and by
    `tests/graph/test_impact_is_not_double_counted.py`.

    Returns `None` for an empty sequence. That is the "nothing was measurable here" answer
    and it is deliberately not zero: a combination over no readings and a combination that
    genuinely came to nothing are different findings, and a caller that printed them
    identically would be reporting an absence as a measurement.

    Raises:
        ContractViolationError: if `operator_name` is not in `COMBINATION_OPERATORS`. An
            unrecognised operator is refused rather than skipped or defaulted, because a
            silently substituted operator changes the number without changing the label
            beside it.
    """
    if operator_name not in COMBINATION_OPERATORS:
        raise ContractViolationError(
            f"causalog.core.attribution.combine_magnitudes received unknown operator "
            f"'{operator_name}'; admissible operators are {sorted(COMBINATION_OPERATORS)}. "
            "An operator outside the set is refused rather than defaulted: substituting "
            "one would change the figure while leaving the declaration that names it "
            "unchanged."
        )
    if not readings:
        return None
    if operator_name == "SUM":
        return _quantize(float(sum(readings)))
    if operator_name == "MINIMUM":
        return _quantize(min(readings))
    return _quantize(max(readings))


def share_of(reading: float, weight: float) -> float:
    """Return one claim's apportioned part of a single consequence's magnitude.

    `weight` is a `PropagationWeight.weight`, already normalized over the claims competing
    for one consequence. The result is an attribution estimate and not a measurement; the
    fixed notice on `PropagationWeight` says so and travels with every figure derived here.

    Raises:
        ContractViolationError: if `weight` falls outside `[0.0, 1.0]`, which would make
            the shares over one consequence sum to something other than one.
    """
    if weight < 0.0 or weight > 1.0:
        raise ContractViolationError(
            f"causalog.core.attribution.share_of received weight {weight}, outside "
            "[0.0, 1.0]. Shares over one consequence sum to one; a weight beyond the "
            "range would break that silently rather than being refused."
        )
    return _quantize(reading * weight)


def difference_of(whole: float | None, remainder: float | None) -> float | None:
    """Return what a counterfactual removal accounts for: the whole less what survives it.

    The arithmetic behind "what does the graph say disappears if this node is removed".
    Both operands are combinations over consequence sets produced by the same operator, so
    the subtraction is between two figures of one kind.

    Returns `None` if either operand is `None` -- if either side was not measurable, the
    difference is not measurable either, and reporting it as zero would claim a removal
    prevents nothing when the truth is that nobody could tell.
    """
    if whole is None or remainder is None:
        return None
    return _quantize(whole - remainder)
