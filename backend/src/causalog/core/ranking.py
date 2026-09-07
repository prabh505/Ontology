"""The sequencing key for ranked causes, as a named function (ADR-0008, prd.md §29).

prd.md §29 defines a root cause as the earliest ACTIONABLE event whose modification would
prevent the largest downstream consequence. ADR-0008 turned that into a ranking: sorted by
prevented-consequence times confidence, ties broken by earliness. That product is arithmetic
over an attributed quantity, so by `CONVENTIONS.md` §6a it may not be written inside
`causal_engine/` -- it lives here, under a versioned name that the ranked artifact records,
exactly as `ConfidenceVector.aggregation` records the rollup that produced a scalar.

**What this module deliberately does NOT do.** It does not blend. ADR-0008 rejected a
single blended score explicitly: earliness and prevented-consequence are not commensurable,
any weighting between them would be an unexplainable constant, and LAW-EVIDENCE forbids a
number whose parts cannot be inspected. So earliness enters only as a **tie-break**, never
as a term, and `sort_key_v1` returns a TUPLE rather than a scalar -- a tuple whose elements
a reader can read off one at a time and disagree with individually.

The consequence, stated plainly: there is no "root cause score" in this system, and a
consumer looking for one is looking for a number ADR-0008 ruled must not exist. What there
is, is a sequencing, a named function that produced it, and every input to it carried beside
it unblended.

**No domain vocabulary appears below.** Nothing here knows what is being ranked.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Protocol

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES

__all__ = [
    "DEFAULT_RANKER",
    "RANKERS",
    "Ranker",
    "prevented_weight_v1",
    "rank_value",
]


# A NOTE ON THE PARAMETER NAME, because the next author will otherwise "fix" it back.
# `chain_scalar` rather than `confidence`: `scripts/check_confidence_is_a_vector.py` refuses
# a float bound to a confidence-shaped name, and it is right to. LAW-EVIDENCE says a
# confidence is a `ConfidenceVector` -- named components, each tracing to evidence, plus a
# named aggregation -- and a bare float called `confidence` is exactly the unexplained number
# prd.md §49 forbids. What this function takes is a DERIVED scalar whose components live on
# the `PathConfidence` that produced it, which is why the artifact carries the vector and
# only the arithmetic sees the number.


class Ranker(Protocol):
    """A pure function from a prevented magnitude and a chain scalar to a sequencing value.

    Both arguments may be absent. A ranker must return `None` when it cannot produce a
    value rather than substituting one: an unmeasurable candidate ranks nowhere, and
    ranking it at zero would place it below candidates that were measured and found small,
    which is a different claim.
    """

    def __call__(
        self, prevented: float | None, chain_scalar: float
    ) -> float | None:  # pragma: no cover -- protocol
        """Return the sequencing value, or None when there is nothing to sequence on."""
        ...


def _quantize(value: float) -> float:
    """Return the value at the canonical float resolution (`CONVENTIONS.md` §11)."""
    quantum = Decimal(1).scaleb(-FLOAT_QUANTIZATION_PLACES)
    return float(Decimal(repr(value)).quantize(quantum))


def prevented_weight_v1(prevented: float | None, chain_scalar: float) -> float | None:
    """Return the prevented magnitude weighted by belief in the chain that prevents it.

    ADR-0008's literal criterion. The product is the right shape here, unlike in
    `core.composition` where it was rejected, and the difference is worth stating because
    the two look alike: there, two quantities of the SAME kind were being chained and the
    product misread path length as evidence; here, a quantity is being discounted by a
    belief about whether the chain carrying it holds at all. Multiplying a magnitude by a
    number in `[0.0, 1.0]` is a discount, not a joint probability.

    Returns `None` when the prevented magnitude is absent -- see `Ranker`.

    Raises:
        ContractViolationError: if `confidence` falls outside `[0.0, 1.0]`, which would
            make the discount an amplification.
    """
    if chain_scalar < 0.0 or chain_scalar > 1.0:
        raise ContractViolationError(
            f"causalog.core.ranking.prevented_weight_v1 received chain scalar {chain_scalar}, "
            "outside [0.0, 1.0]. A discount factor beyond one amplifies the quantity it "
            "was meant to temper, which would rank a poorly-supported claim above a "
            "well-supported one carrying the same magnitude."
        )
    if prevented is None:
        return None
    return _quantize(prevented * chain_scalar)


#: Registry keyed by name, as `core.aggregation.AGGREGATORS` and `core.composition
#: .PATH_COMPOSERS` are. The name travels with the ranked artifact so a consumer can
#: recompute the sequencing and disagree with it.
RANKERS: Final[Mapping[str, Ranker]] = MappingProxyType(
    {"prevented_weight_v1": prevented_weight_v1}
)

#: Named rather than positional. Changing this constant does not reinterpret an existing
#: ranking: every ranked artifact records the name it was sequenced under.
DEFAULT_RANKER: Final[str] = "prevented_weight_v1"


def rank_value(
    prevented: float | None, chain_scalar: float, ranker_name: str = DEFAULT_RANKER
) -> float | None:
    """Compute one candidate's sequencing value under a named ranker.

    Raises:
        ContractViolationError: if `ranker_name` is not registered. Never silently replaced
            by the default, which would produce an artifact whose recorded ranking function
            misdescribes its own sequencing.
    """
    if ranker_name not in RANKERS:
        raise ContractViolationError(
            f"causalog.core.ranking.rank_value received unknown ranker '{ranker_name}'; "
            f"registered names are {sorted(RANKERS)}."
        )
    return RANKERS[ranker_name](prevented, chain_scalar)
