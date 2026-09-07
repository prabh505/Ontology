"""Shared, component-neutral helpers. No component logic lives here.

Four shapes every scorer needs and none of them should implement twice: the two saturating
curves, the record citation, and the "this component could not be measured" return.
"""

from __future__ import annotations

import math

from causalog.causal_engine.confidence_scorer.context import ScoredComponent
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event

__all__ = [
    "EFFECT_WEIGHTED",
    "SAMPLE_WEIGHTED",
    "blend",
    "citations",
    "not_scorable",
    "saturating",
    "shrinkage",
    "squashed_lift",
]


def saturating(count: int, half_at: int) -> float:
    """Return `count / (count + half_at)` -- volume that decelerates.

    Saturating rather than linear-to-a-cap, because the tenth justification for a claim
    genuinely adds less than the second and a linear scale says otherwise. At
    `count == half_at` the value is exactly 0.5, which is what makes the declared parameter
    readable: it is the count at which this pack is half convinced.
    """
    if count <= 0:
        return 0.0
    return count / (count + half_at)


def shrinkage(sample_size: int, prior_count: int) -> float:
    """Return the small-sample discount `n / (n + prior)`.

    The same curve as `saturating`, applied to a different question and kept separate
    because merging them would hide that one is about how much evidence there is and the
    other about how much of it to believe. A pattern seen three times and a pattern seen
    three thousand times do not deserve the same score at identical lift, and rounding the
    small one up is the specific dishonesty this term exists to prevent.
    """
    if sample_size <= 0:
        return 0.0
    return sample_size / (sample_size + prior_count)


def squashed_lift(lift: float, reference: float) -> float:
    """Return lift mapped into `[0, 1]`, logarithmically, against a declared reference.

    `lift == 1.0` is independence and maps to exactly 0.0 -- **this is the base-rate
    property**: a pattern that occurs everywhere has a conditional rate equal to its
    baseline rate, lift 1.0, and scores nothing however many instances exhibit it. Lift
    below 1.0 is negative association and also maps to 0.0; it is not evidence FOR the
    claim, and this component measures support rather than direction of association.

    `lift == reference` maps to 1.0. Logarithmic between them because lift is a ratio: the
    step from 1.0 to 1.5 is a larger change in belief than the step from 3.0 to 3.5, and a
    linear map would say they are the same size.
    """
    if lift <= 1.0 or reference <= 1.0:
        return 0.0
    return min(1.0, math.log(lift) / math.log(reference))


#: The exponent pair that makes a blend SAMPLE-dominated: how much evidence there is counts
#: for twice what the size of the effect does. `historical_support` reads this, because the
#: question it answers is "does this recur often enough to be worth looking at".
SAMPLE_WEIGHTED = (2.0 / 3.0, 1.0 / 3.0)

#: The mirror image, EFFECT-dominated. `statistical_support` reads this, because the question
#: it answers is "how far is this from independence".
#:
#: Two thirds against one third rather than anything finer. The pair is a statement about
#: WHICH of two factors each component is mostly about, not a fitted weighting -- nothing
#: here has been calibrated, and a two-decimal exponent would imply a precision that does not
#: exist. Both components read both factors, so neither can score well on a large sample of
#: nothing or on a huge ratio seen twice.
EFFECT_WEIGHTED = (1.0 / 3.0, 2.0 / 3.0)


def blend(sample_term: float, effect_term: float, exponents: tuple[float, float]) -> float:
    """Return a weighted geometric mean of the sample term and the effect term.

    Geometric rather than arithmetic, and that is the whole point: **a zero on either factor
    is a zero overall.** An association at independence scores nothing however many instances
    exhibit it, and a spectacular ratio seen zero times scores nothing either. An arithmetic
    mean would let a large sample of no association carry a component to a third of its
    range, which is the specific way a count starts standing in for a finding.

    Bounded in `[0, 1]` because both inputs are, and monotone non-decreasing in each because
    the exponents are positive.
    """
    if sample_term <= 0.0 or effect_term <= 0.0:
        return 0.0
    sample_exponent, effect_exponent = exponents
    return float(sample_term**sample_exponent) * float(effect_term**effect_exponent)


def citations(*events: Event) -> tuple[str, ...]:
    """Return the dataset records these events were derived from, sorted, deduplicated.

    `ConfidenceComponent.evidence_record_ids` is "the trace that makes the value
    re-derivable from an audit record alone" (`docs/contracts.md` §5), and a dataset record
    is what an audit actually holds. The `EvidenceItem` identifiers a component read are
    carried in its explanation's `inputs` instead -- they are content addresses over
    reasoning, not citations into the source, and putting them in this field would make the
    audit trail stop at the engine's own output.
    """
    return tuple(sorted({record for event in events for record in event.evidence_record_ids}))


def not_scorable(component_name: str, requirement: str) -> ScoredComponent:
    """Return the one admissible shape of a component that could not be measured.

    Value zero, cited nothing, explained as missing. Absence costs confidence rather than
    abstaining -- but it is REPORTED as absence, which is what separates it from a measured
    zero. Every scorer returns through here rather than returning None, because a None is
    something a caller can drop on the floor.
    """
    return ScoredComponent(
        component_name=component_name,
        value=0.0,
        provenance_class=ProvenanceClass.ASSUMED,
        evidence_record_ids=(),
        explanation=ComponentExplanation.absent(component_name, requirement),
    )
