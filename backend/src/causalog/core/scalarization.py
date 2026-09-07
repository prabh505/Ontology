"""The multi-objective trade-off, as named functions plus the frontier that outranks them.

prd.md §50 gives a ranking function in three lines -- "Highest Benefit / Lowest Cost /
Highest Confidence" -- and prints seven quantities above it. Three lines is a preference
SEQUENCE, not a procedure: it does not say what to do when one intervention is better on
benefit and worse on cost, which is the only interesting case and the case that occurs.
Turning it into a procedure requires weights, and weights are a judgement.

WHY THIS IS IN `core` AND NOT IN `recommendation_engine`
--------------------------------------------------------
`CONVENTIONS.md` §6a puts `recommendation_engine/` inside the metric-declaration lint and
lists `cost` and `impact` among its stems. Arithmetic over a cost-named value is refused
there, and it is refused for a good reason rather than an incidental one: a formula written
into engine code does not move when the ontology is swapped. So the arithmetic lands here,
under a versioned registry name that the ranked artifact records -- exactly as
`core.ranking`, `core.aggregation` and `core.composition` already do. §6a's own scope note
excludes `core/`, whose arithmetic is over engine concepts rather than domain metrics
(ADR-0009), and a desirability is an engine concept: it is arithmetic over four normalized
objectives, none of which is a domain quantity by the time it arrives.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
------------------------------------------
**It does not decide the weights.** They are declared in the rule pack and travel with the
artifact. A reader who disagrees changes the pack, which changes `rule_pack_version`, which
changes `run_id` -- so a ranking produced under one weighting can never be mistaken for a
ranking produced under another.

**It does not hold a vocabulary.** Ordinal ranks arrive with the span they were drawn from.
A function that looked up a cost class would be a store, and the caller would stop being
able to see which vocabulary it ranked against.

**It does not present the scalar as the answer.** `pareto_front_v1` exists beside
`weighted_desirability_v1` and is reported beside it, never instead of it. A scalarization
is one traversal of a trade-off surface; the frontier is the surface. ADR-0008 refused a
blended root-cause score outright for this reason. A recommendation ranking is a weaker case
-- the four objectives here are genuinely being traded against each other by an operator who
must pick one -- so the scalar is permitted, and it is permitted only with the frontier
printed next to it.

THE MISSING-OBJECTIVE RULE, WHICH IS NOT RENORMALIZATION
---------------------------------------------------------
An undeclared operational risk **costs** the candidate its risk term; it is not renormalized
away. This is module 10's ruling on `graph_connectivity`, which is reported MISSING on every
edge and costs every edge score rather than being quietly dropped. Renormalizing would rank
a candidate whose risk nobody declared ABOVE one that declared a low risk honestly, which
rewards an absent declaration -- and an absent declaration is exactly what the pack author
must be pushed to fix.

**No domain vocabulary appears below.** Nothing here knows what is being traded off.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Protocol

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES

__all__ = [
    "DEFAULT_SCALARIZER",
    "OBJECTIVES",
    "SCALARIZERS",
    "Scalarizer",
    "inverted_rank",
    "pareto_front_v1",
    "scalarize",
    "weighted_desirability_v1",
]


#: The closed set of objectives a recommendation is traded off on, in canonical sequence.
#: `benefit` and `confidence` are better high; `cost` and `risk` are better low. That
#: orientation is applied inside the scalarizer rather than expected of a caller, because a
#: caller that inverted one of them by hand would produce a ranking that looks ordinary.
OBJECTIVES: Final[tuple[str, ...]] = ("benefit", "cost", "confidence", "risk")


def _quantize(value: float) -> float:
    """Return the value at the canonical float resolution (`CONVENTIONS.md` §11)."""
    quantum = Decimal(1).scaleb(-FLOAT_QUANTIZATION_PLACES)
    return float(Decimal(repr(value)).quantize(quantum))


def inverted_rank(rank: int | None, span: int) -> float | None:
    """Return an ordinal rank re-pointed so that HIGHER IS BETTER, or `None` if absent.

    A better-low objective becomes a better-high one by measuring its distance from the
    worst member of its own vocabulary. An inversion rather than a negation, so every
    coordinate stays non-negative and two points on a frontier are compared as quantities
    of one shape.

    `None` propagates: an undeclared class excludes the point from the frontier rather than
    placing it worst, which is `pareto_front_v1`'s rule and a different rule from the
    scalarizer's. Both are deliberate and this module's docstring says why they differ.

    Lives here rather than at the call site because `CONVENTIONS.md` §6a refuses arithmetic
    over a cost-named value inside `recommendation_engine/`.
    """
    if rank is None:
        return None
    return float(max(0, span - 1) - rank)


def _normalized_rank(rank: int | None, span: int) -> float:
    """Return an ordinal rank on `[0.0, 1.0]`, where 1.0 is the worst member.

    `None` returns 1.0 -- the worst -- rather than being excluded. See this module's
    docstring: an undeclared objective costs the candidate, and does not renormalize away.
    A span of one member is degenerate and maps every member to 0.0, which is correct: a
    vocabulary that cannot distinguish two things must not be allowed to sequence them.
    """
    if rank is None:
        return 1.0
    if span <= 1:
        return 0.0
    return min(1.0, max(0.0, rank / (span - 1)))


class Scalarizer(Protocol):
    """A pure function from four objectives to one comparable value on `[0.0, 1.0]`.

    A scalarizer must return `None` when it cannot produce a value rather than substituting
    one. `core.ranking.Ranker` states the reason and it holds identically here: a candidate
    whose benefit was never measured ranks NOWHERE, and ranking it at zero would place it
    below candidates that were measured and found small, which is a different claim.
    """

    def __call__(
        self,
        *,
        benefit: float | None,
        benefit_ceiling: float | None,
        cost_rank: int | None,
        cost_span: int,
        risk_rank: int | None,
        risk_span: int,
        belief_scalar: float,
        weights: Mapping[str, float],
    ) -> float | None:  # pragma: no cover -- protocol
        """Return the desirability, or None when there is nothing to sequence on."""
        ...


def weighted_desirability_v1(
    *,
    benefit: float | None,
    benefit_ceiling: float | None,
    cost_rank: int | None,
    cost_span: int,
    risk_rank: int | None,
    risk_span: int,
    belief_scalar: float,
    weights: Mapping[str, float],
) -> float | None:
    """Return one candidate's desirability on `[0.0, 1.0]`, higher being preferred.

    Every term is normalized before it is weighted, so the four are commensurable by
    construction rather than by the caller having remembered to make them so. The weighted
    sum is divided by the total weight, which is what makes two rankings under two different
    weightings comparable in magnitude -- without it, a pack that doubled every weight would
    double every score and look like it had found better interventions.

    Args:
        benefit: the aggregated benefit figure, in the measurement's own unit. `None` when
            the benefit could not be measured or was replaced by an `EXTRAPOLATION` verdict.
        benefit_ceiling: the largest benefit among the candidates being ranked together,
            which is what `benefit` is expressed as a fraction of. Supplied by the caller
            because it is a property of the SET, and a function ranking one candidate cannot
            see the set. A ceiling at or below zero makes the benefit term unmeasurable.
        cost_rank: the ordinal rank of the declared cost class, or `None` if undeclared.
        cost_span: how many members that vocabulary holds.
        risk_rank: the ordinal rank of the declared operational-risk class, or `None`.
        risk_span: how many members that vocabulary holds.
        belief_scalar: a DERIVED scalar on `[0.0, 1.0]` whose components live on the
            `ConfidenceVector` that produced it. Named this rather than `confidence` for the
            reason `core.ranking` names its own `chain_scalar`:
            `check_confidence_is_a_vector.py` refuses a float bound to a confidence-shaped
            name, and it is right to -- LAW-EVIDENCE says a confidence is a vector, and a
            bare float called `confidence` is the unexplained number prd.md §49 forbids.
        weights: one weight per member of `OBJECTIVES`, keyed by name. Every objective is
            weighted explicitly, including at zero; an omitted key is refused rather than
            treated as zero, because the two mean the same thing to the arithmetic and
            completely different things to a reader of the pack that declared them.

    Returns:
        The desirability, or `None` when the benefit is absent -- see `Scalarizer`.

    Raises:
        ContractViolationError: if `confidence` falls outside `[0.0, 1.0]`; if a weight is
            negative; if no weight is positive; or if a span is not positive.
    """
    if belief_scalar < 0.0 or belief_scalar > 1.0:
        raise ContractViolationError(
            f"causalog.core.scalarization.weighted_desirability_v1 received belief scalar "
            f"{belief_scalar}, outside [0.0, 1.0]. A belief beyond one would let a single "
            "objective exceed its declared weight and silently outrank the other three."
        )
    for span_name, span in (("cost_span", cost_span), ("risk_span", risk_span)):
        if span < 1:
            raise ContractViolationError(
                f"causalog.core.scalarization.weighted_desirability_v1 received "
                f"{span_name}={span}. A vocabulary with no members cannot place a rank, and "
                "normalizing against it would divide by a span that does not exist."
            )
    missing = tuple(name for name in OBJECTIVES if name not in weights)
    if missing:
        raise ContractViolationError(
            f"causalog.core.scalarization.weighted_desirability_v1 was given no weight for "
            f"{', '.join(missing)}. Every objective is weighted explicitly, including at "
            "zero: an omitted weight and a zero weight mean the same thing to the "
            "arithmetic and completely different things to a reader of the pack."
        )
    for name in OBJECTIVES:
        if weights[name] < 0.0:
            raise ContractViolationError(
                f"causalog.core.scalarization.weighted_desirability_v1 received weight "
                f"{weights[name]} for '{name}'. A negative weight inverts one objective's "
                "preference direction while the artifact still reports it as that objective."
            )
    total = sum(weights[name] for name in OBJECTIVES)
    if total <= 0.0:
        raise ContractViolationError(
            "causalog.core.scalarization.weighted_desirability_v1 received weights that sum "
            "to zero; every candidate would score identically and the sequencing would be "
            "whatever the input happened to be in."
        )

    if benefit is None or benefit_ceiling is None or benefit_ceiling <= 0.0:
        return None

    benefit_term = min(1.0, max(0.0, benefit / benefit_ceiling))
    cost_term = 1.0 - _normalized_rank(cost_rank, cost_span)
    risk_term = 1.0 - _normalized_rank(risk_rank, risk_span)

    weighted = (
        weights["benefit"] * benefit_term
        + weights["cost"] * cost_term
        + weights["confidence"] * belief_scalar
        + weights["risk"] * risk_term
    )
    return _quantize(weighted / total)


def pareto_front_v1(
    points: Sequence[Sequence[float | None]],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return the non-dominated indices and, separately, the indices that could not compete.

    Every coordinate is oriented so that **higher is better** before it arrives; this
    function applies no orientation of its own, because a function that inverted an axis
    would be a second place where preference direction is decided.

    A point dominates another when it is at least as good on every coordinate and strictly
    better on at least one. The returned front is the set nothing dominates.

    **A point holding any `None` is excluded rather than treated as worst.** This is the one
    place this module departs from the missing-objective rule in `weighted_desirability_v1`,
    and the departure is deliberate: a scalar is a preference, so scoring an unmeasured
    objective at its worst is a defensible pessimism, but membership of a frontier is a
    CLAIM -- "nothing beats this" -- and that claim cannot be made about a candidate whose
    coordinates are partly unmeasured. Such candidates come back in the second tuple so a
    caller reports them rather than losing them.

    Returns:
        `(front, excluded)`, both sequenced ascending, both indices into `points`.

    Raises:
        ContractViolationError: if the points differ in dimension, which would make
            domination a comparison between different questions.
    """
    if not points:
        return ((), ())
    width = len(points[0])
    for position, point in enumerate(points):
        if len(point) != width:
            raise ContractViolationError(
                f"causalog.core.scalarization.pareto_front_v1 received a point at index "
                f"{position} with {len(point)} coordinate(s) against {width} at index 0. "
                "Domination between points of different dimension compares two different "
                "trade-offs and would report an arbitrary winner."
            )

    excluded = tuple(
        position for position, point in enumerate(points) if any(axis is None for axis in point)
    )
    contenders = tuple(position for position in range(len(points)) if position not in set(excluded))

    front: list[int] = []
    for position in contenders:
        candidate = points[position]
        dominated = False
        for other_position in contenders:
            if other_position == position:
                continue
            other = points[other_position]
            # Both are `None`-free by construction -- `contenders` excludes any point
            # holding one -- and the narrowing below tells the type checker so without a
            # cast, which would assert the fact rather than establish it.
            pairs = [
                (left, right)
                for left, right in zip(candidate, other, strict=True)
                if left is not None and right is not None
            ]
            at_least_as_good = all(right >= left for left, right in pairs)
            strictly_better = any(right > left for left, right in pairs)
            if at_least_as_good and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(position)
    return (tuple(front), excluded)


#: Registry keyed by name, as `core.ranking.RANKERS` and `core.aggregation.AGGREGATORS` are.
#: The name travels with the ranked artifact so a consumer can recompute the sequencing and
#: disagree with it.
SCALARIZERS: Final[Mapping[str, Scalarizer]] = MappingProxyType(
    {"weighted_desirability_v1": weighted_desirability_v1}
)

#: Named rather than positional. Changing this constant does not reinterpret an existing
#: ranking: every ranked artifact records the name it was sequenced under.
DEFAULT_SCALARIZER: Final[str] = "weighted_desirability_v1"


def scalarize(
    *,
    benefit: float | None,
    benefit_ceiling: float | None,
    cost_rank: int | None,
    cost_span: int,
    risk_rank: int | None,
    risk_span: int,
    belief_scalar: float,
    weights: Mapping[str, float],
    scalarizer_name: str = DEFAULT_SCALARIZER,
) -> float | None:
    """Compute one candidate's desirability under a named scalarizer.

    Raises:
        ContractViolationError: if the name is not registered. Naming an unregistered
            function is a pack error, and defaulting past it would silently rank under a
            function the pack did not choose.
    """
    if scalarizer_name not in SCALARIZERS:
        raise ContractViolationError(
            f"causalog.core.scalarization.scalarize was asked for {scalarizer_name!r}, which "
            f"is not registered. Registered: {', '.join(sorted(SCALARIZERS))}. The name is "
            "recorded on every ranked artifact, so falling back to the default would "
            "produce a ranking whose stated function did not produce it."
        )
    return SCALARIZERS[scalarizer_name](
        benefit=benefit,
        benefit_ceiling=benefit_ceiling,
        cost_rank=cost_rank,
        cost_span=cost_span,
        risk_rank=risk_rank,
        risk_span=risk_span,
        belief_scalar=belief_scalar,
        weights=weights,
    )
