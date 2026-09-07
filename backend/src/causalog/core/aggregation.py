"""Confidence aggregation: explainable, named, and pluggable (ADR-0009).

LAW-EVIDENCE requires that every confidence number decompose into named components. That
leaves one question open, which this module answers: how the components roll up into the
single figure a ranking needs.

Three rules govern every aggregator here.

1. **The rollup is derived, never authoritative.** `ConfidenceVector.components` is the
   value. `scalar` is a convenience for sequencing and display, and discarding it must
   never lose information.
2. **The function is named in the artifact.** `ConfidenceVector.aggregation` records which
   aggregator produced the scalar, so any consumer can recompute it and disagree. An
   unnamed rollup is the unexplained number prd.md §49 forbids.
3. **Provenance does not aggregate the same way.** The scalar combines by the aggregator's
   own arithmetic; the provenance class always takes the weakest component present
   (ADR-0005). These are separate questions and are answered separately -- a high scalar
   over `ASSUMED` inputs is still `ASSUMED`.

Pluggability is a registry lookup by name, not a subclass hierarchy: an aggregator is a
plain function, the registry maps name to function, and the name travels with the data.
Adding one is additive. Changing what an existing name computes is a breaking change to
`confidence_schema_version`, which is why the shipped names carry a `_v1` suffix.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from itertools import pairwise
from types import MappingProxyType
from typing import Final, Protocol

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES
from causalog.core.provenance import combine
from causalog.core.types.confidence import ConfidenceComponent, ConfidenceVector

__all__ = [
    "AGGREGATORS",
    "AGGREGATOR_COMPONENT_NAMES",
    "CONTRADICTION_CEILING_ANCHORS",
    "DEFAULT_AGGREGATOR",
    "DEFAULT_COMPONENT_WEIGHTS",
    "GATE_COMPONENT_NAMES",
    "TEMPORAL_CEILING_ANCHORS",
    "V2_ADDEND_WEIGHTS",
    "V2_COMPONENT_NAMES",
    "Aggregator",
    "aggregate",
    "ceiling_at",
    "gated_weighted_mean_v1",
    "minimum_v1",
    "weighted_mean_v1",
]


class Aggregator(Protocol):
    """A pure function from components to a scalar rollup in `[0.0, 1.0]`.

    An aggregator reads only the component names and values. It may not read evidence,
    provenance, or anything outside its arguments -- provenance is combined separately by
    `aggregate`, and an aggregator that peeked at it would make the two rules interact in
    a way no consumer could reproduce.
    """

    def __call__(self, components: Sequence[ConfidenceComponent]) -> float:
        """Return the rollup for these components."""
        ...


#: The declared weights of `weighted_mean_v1`, one per prd.md §49 component name.
#:
#: These are a stated editorial judgement, not a measurement: this dataset has no causal
#: ground truth to fit them against, so no procedure could have derived them. They are
#: recorded here, in one place, precisely so that disagreement is possible -- a weight
#: buried in a scoring loop is a judgement nobody can find to argue with.
#:
#: Rule support leads because an explicit rule is the strongest evidence the engine
#: admits; graph connectivity trails because a well-connected node is suggestive of
#: nothing on its own.
DEFAULT_COMPONENT_WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(
    {
        "rule_support": 0.25,
        "temporal_support": 0.20,
        "historical_support": 0.15,
        "statistical_support": 0.15,
        "evidence_count": 0.15,
        "graph_connectivity": 0.10,
    }
)


def _quantize(value: float) -> float:
    """Return the value rounded to the canonical float resolution.

    `CONVENTIONS.md` §11 quantizes at every serialization boundary. Quantizing here as
    well means the stored scalar equals the recomputed one exactly, so a consumer checking
    the rollup does not have to know the comparison tolerance.
    """
    quantum = Decimal(1).scaleb(-FLOAT_QUANTIZATION_PLACES)
    return float(Decimal(repr(value)).quantize(quantum))


def weighted_mean_v1(components: Sequence[ConfidenceComponent]) -> float:
    """Return the weight-normalized mean of the components present.

    Weights come from `DEFAULT_COMPONENT_WEIGHTS` and are renormalized over the components
    actually supplied, so an absent component neither helps nor hurts -- it abstains.
    Treating an absent component as zero instead would punish an edge for evidence the
    pipeline never looked for.

    Raises:
        ContractViolationError: on a component name absent from the weight table. The
            component names are part of `confidence_schema_version`; guessing a weight for
            an unrecognised one would let a schema change pass silently and shift every
            score. Introducing a name means shipping a new aggregator version alongside it.
    """
    unknown = sorted(
        component.component_name
        for component in components
        if component.component_name not in DEFAULT_COMPONENT_WEIGHTS
    )
    if unknown:
        raise ContractViolationError(
            f"causalog.core.aggregation.weighted_mean_v1 received unweighted component "
            f"name(s) {unknown}; every name is part of confidence_schema_version and a "
            "new name requires a new aggregator version (ADR-0009)."
        )
    total_weight = sum(
        DEFAULT_COMPONENT_WEIGHTS[component.component_name] for component in components
    )
    if total_weight == 0.0:
        raise ContractViolationError(
            "causalog.core.aggregation.weighted_mean_v1 received components whose weights "
            "sum to zero; the rollup would be undefined (ADR-0009)."
        )
    weighted = sum(
        DEFAULT_COMPONENT_WEIGHTS[component.component_name] * component.value
        for component in components
    )
    return _quantize(weighted / total_weight)


def minimum_v1(components: Sequence[ConfidenceComponent]) -> float:
    """Return the smallest component value.

    The conservative rollup: the claim is only as strong as its weakest support, mirroring
    the provenance algebra. Name-agnostic, so it keeps working across schema changes that
    `weighted_mean_v1` deliberately rejects. It ranks poorly -- one weak component pins
    every score to the floor -- which is why it is not the default.
    """
    return _quantize(min(component.value for component in components))


# ---------------------------------------------------------------------------------------
# confidence_schema_version 2.0.0 -- the gated strategy (ADR-0052)
#
# `weighted_mean_v1` above is UNCHANGED and stays registered. Every artifact that names it
# must still recompute to the same scalar, which is the whole point of putting the function
# name in the vector. What follows is a SECOND strategy beside it, not a revision of it.
#
# Two things separate it from `weighted_mean_v1`:
#
#   1. **Two new component names.** `evidence_diversity` and `contradiction_freedom`.
#      Adding a name is a breaking change to `confidence_schema_version` (docs/contracts.md
#      section 5), which is why this arrives as `_v1` of a new function rather than as `_v2`
#      of the old one.
#   2. **Two of the eight components are GATES, not addends.** Temporal support and freedom
#      from contradiction do not contribute to a sum that other evidence can outvote. They
#      cap the result. An edge whose precedence cannot be established is not slightly less
#      confident than one whose precedence is certain -- it is bounded, and no quantity of
#      rule support may lift it past that bound (prd.md section 23, CONVENTIONS.md section 10).
# ---------------------------------------------------------------------------------------

#: The six ADDEND weights of `gated_weighted_mean_v1`, renormalized over those supplied.
#:
#: Like `DEFAULT_COMPONENT_WEIGHTS`, these are a stated editorial judgement and not a
#: measurement. This repository holds no labelled causal ground truth, so no procedure could
#: have fitted them; they are written here, in one place, so that disagreement has somewhere
#: to point. See ADR-0052.
#:
#: Rule support leads, because an authored rule is the strongest evidence the engine admits.
#: Diversity is deliberately weighted ABOVE raw count: two independent lines of reasoning
#: reaching one pair say more than one line repeated twice, and weighting volume higher
#: would reward a generator that fires many times over a generator that agrees with another.
#: Graph connectivity trails, because a well-connected node is suggestive of nothing alone.
V2_ADDEND_WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(
    {
        "rule_support": 0.28,
        "historical_support": 0.17,
        "statistical_support": 0.17,
        "evidence_diversity": 0.16,
        "evidence_count": 0.12,
        "graph_connectivity": 0.10,
    }
)

#: The two components that act as ceilings rather than as addends.
GATE_COMPONENT_NAMES: Final[frozenset[str]] = frozenset(
    {"temporal_support", "contradiction_freedom"}
)

#: Every name `gated_weighted_mean_v1` knows. Part of `confidence_schema_version` 2.0.0.
V2_COMPONENT_NAMES: Final[frozenset[str]] = frozenset(V2_ADDEND_WEIGHTS) | GATE_COMPONENT_NAMES

#: `(component value, ceiling)` anchors for the temporal gate, ascending, piecewise-linear
#: between them. Read as: an edge whose precedence rests on nothing may not be reported above
#: 0.25 however much other evidence it carries.
#:
#: Every anchor's ceiling is at or above its own input, which is not decorative: it is what
#: keeps the rollup from falling below its weakest component, a property
#: `tests/unit/core/test_confidence_aggregation.py` asserts over every registered aggregator.
TEMPORAL_CEILING_ANCHORS: Final[tuple[tuple[float, float], ...]] = (
    (0.0, 0.25),
    (0.30, 0.55),
    (0.60, 0.80),
    (1.0, 1.0),
)

#: The same shape for the contradiction gate. Steeper at the bottom: an edge with active
#: counter-evidence is capped harder than one merely resting on unverifiable time, because
#: the first is a positive finding against the claim and the second is only an absence.
CONTRADICTION_CEILING_ANCHORS: Final[tuple[tuple[float, float], ...]] = (
    (0.0, 0.10),
    (0.50, 0.60),
    (1.0, 1.0),
)


def ceiling_at(value: float, anchors: tuple[tuple[float, float], ...]) -> float:
    """Return the piecewise-linear ceiling for one gate value, at canonical resolution.

    Non-decreasing in `value` by construction, because the anchors ascend in both
    coordinates. That is the property the monotonicity proof rests on: a weighted mean is
    non-decreasing in each addend, each ceiling is non-decreasing in its gate, and the
    minimum of non-decreasing functions is non-decreasing -- so raising any one of the eight
    components can never lower the scalar (ADR-0052).

    **The result is quantized, and that is load-bearing rather than tidy.** The scalar is
    stored at six decimal places, so a cap compared against an unquantized ceiling is not a
    cap: interpolation lands on a value like `0.44738999999999995`, the scalar rounds to
    `0.44739`, and the stored number sits 5.5e-17 ABOVE its own ceiling. Measured at 3.8% of
    random component vectors before this line existed, and caught by
    `test_the_scalar_never_exceeds_either_ceiling`. A hard cap that a rounding can step over
    is a soft cap with better documentation, so both sides of the comparison are brought to
    the resolution the system actually stores.
    """
    if value <= anchors[0][0]:
        return _quantize(anchors[0][1])
    for (low_value, low_ceiling), (high_value, high_ceiling) in pairwise(anchors):
        if value <= high_value:
            span = high_value - low_value
            if span == 0.0:
                return _quantize(high_ceiling)
            return _quantize(
                low_ceiling + (high_ceiling - low_ceiling) * (value - low_value) / span
            )
    return _quantize(anchors[-1][1])


def gated_weighted_mean_v1(components: Sequence[ConfidenceComponent]) -> float:
    """Return the weighted mean of the six addends, capped by the two gates.

        scalar = min(
            weighted_mean(rule, historical, statistical, diversity, count, connectivity),
            ceiling(temporal_support),
            ceiling(contradiction_freedom),
        )

    **All eight names are required.** Unlike `weighted_mean_v1`, an absent component does
    not abstain here, because the module that produces these vectors never omits one: a
    component whose data is missing is emitted at zero and reported as missing
    (`causal_engine.confidence_scorer`, ADR-0052). An absent name therefore means a caller
    assembled a vector some other way, and guessing which of the two meanings was intended
    would silently change every score.

    Raises:
        ContractViolationError: on an unrecognised name, or on a missing one. Both are
            schema errors rather than weak evidence, and both are refused rather than
            repaired.
    """
    supplied = {component.component_name: component.value for component in components}
    unknown = sorted(name for name in supplied if name not in V2_COMPONENT_NAMES)
    if unknown:
        raise ContractViolationError(
            f"causalog.core.aggregation.gated_weighted_mean_v1 received unrecognised "
            f"component name(s) {unknown}; the eight names are part of "
            "confidence_schema_version 2.0.0 and a new name requires a new aggregator "
            "version (ADR-0052)."
        )
    absent = sorted(V2_COMPONENT_NAMES - set(supplied))
    if absent:
        raise ContractViolationError(
            f"causalog.core.aggregation.gated_weighted_mean_v1 was not given component(s) "
            f"{absent}. This strategy does not let an absent component abstain: a missing "
            "component is emitted at zero and reported as missing, so an absent one means "
            "the vector was assembled outside the confidence scorer (ADR-0052)."
        )
    total_weight = sum(V2_ADDEND_WEIGHTS.values())
    weighted = sum(weight * supplied[name] for name, weight in V2_ADDEND_WEIGHTS.items())
    return _quantize(
        min(
            weighted / total_weight,
            ceiling_at(supplied["temporal_support"], TEMPORAL_CEILING_ANCHORS),
            ceiling_at(supplied["contradiction_freedom"], CONTRADICTION_CEILING_ANCHORS),
        )
    )


#: The registry. Frozen: an aggregator added at runtime would not survive into the
#: artifact's `aggregation` field on another machine, and the rollup would stop being
#: reproducible.
AGGREGATORS: Final[Mapping[str, Aggregator]] = MappingProxyType(
    {
        "weighted_mean_v1": weighted_mean_v1,
        "minimum_v1": minimum_v1,
        "gated_weighted_mean_v1": gated_weighted_mean_v1,
    }
)

#: What each registered aggregator will accept, so a caller -- and a property test -- can
#: ask rather than assume. `None` means name-agnostic.
#:
#: This mapping exists because the registry stopped being uniform the moment a second
#: schema version landed: `weighted_mean_v1` accepts any subset of its six names,
#: `gated_weighted_mean_v1` requires all eight of its own, and `minimum_v1` accepts
#: anything. A test that draws one aggregator and one component set has to know which,
#: and discovering it by catching `ContractViolationError` would make the check pass for
#: the wrong reason.
AGGREGATOR_COMPONENT_NAMES: Final[Mapping[str, frozenset[str] | None]] = MappingProxyType(
    {
        "weighted_mean_v1": frozenset(DEFAULT_COMPONENT_WEIGHTS),
        "minimum_v1": None,
        "gated_weighted_mean_v1": V2_COMPONENT_NAMES,
    }
)

#: Used when no aggregator is named. Recorded in the artifact either way, so a later
#: change of default cannot silently reinterpret an existing scalar.
DEFAULT_AGGREGATOR: Final[str] = "weighted_mean_v1"


def aggregate(
    components: Sequence[ConfidenceComponent],
    aggregator_name: str = DEFAULT_AGGREGATOR,
) -> ConfidenceVector:
    """Build a `ConfidenceVector` from its components.

    Sorts the components by name (`CONVENTIONS.md` §11), computes the scalar with the
    named aggregator, and sets the vector's provenance to the weakest component class
    (ADR-0005) -- never to the aggregator's arithmetic result.

    Raises:
        ContractViolationError: if `components` is empty, or if `aggregator_name` is not
            in `AGGREGATORS`. An unknown name is never silently replaced by the default:
            that would produce a vector whose `aggregation` field misdescribes its own
            scalar.
    """
    if not components:
        raise ContractViolationError(
            "causalog.core.aggregation.aggregate requires at least one component; an "
            "empty vector is a defect, not zero confidence (LAW-EVIDENCE)."
        )
    if aggregator_name not in AGGREGATORS:
        raise ContractViolationError(
            f"causalog.core.aggregation.aggregate received unknown aggregator "
            f"'{aggregator_name}'; registered names are "
            f"{sorted(AGGREGATORS)} (ADR-0009)."
        )
    sequenced = tuple(sorted(components, key=lambda component: component.component_name))
    return ConfidenceVector(
        components=sequenced,
        scalar=AGGREGATORS[aggregator_name](sequenced),
        aggregation=aggregator_name,
        provenance_class=combine(*(component.provenance_class for component in sequenced)),
    )
