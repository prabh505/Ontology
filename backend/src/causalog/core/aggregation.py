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
from types import MappingProxyType
from typing import Final, Protocol

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES
from causalog.core.provenance import combine
from causalog.core.types.confidence import ConfidenceComponent, ConfidenceVector

__all__ = [
    "AGGREGATORS",
    "DEFAULT_AGGREGATOR",
    "DEFAULT_COMPONENT_WEIGHTS",
    "Aggregator",
    "aggregate",
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


#: The registry. Frozen: an aggregator added at runtime would not survive into the
#: artifact's `aggregation` field on another machine, and the rollup would stop being
#: reproducible.
AGGREGATORS: Final[Mapping[str, Aggregator]] = MappingProxyType(
    {
        "weighted_mean_v1": weighted_mean_v1,
        "minimum_v1": minimum_v1,
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
