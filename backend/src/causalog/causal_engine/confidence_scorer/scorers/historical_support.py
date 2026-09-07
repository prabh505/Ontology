"""`historical_support` -- how often this pattern recurs, ***against its base rate***.

A raw recurrence count is not a finding. "This pattern occurs in 84 process instances" says
nothing until someone says out of how many, and it says nothing at all if the effect type
occurs in every instance anyway. So this component scores **lift** -- the observed conditional rate
divided by the effect type's own baseline rate -- and never the count on its own.

    lift = P(effect follows | cause present) / P(effect present)

Lift 1.0 is independence and scores exactly 0.0. **A pattern that occurs everywhere scores
nothing**, however many instances exhibit it, and that is the property this component exists
to have. `tests/.../test_base_rates.py` pins it.

The raw count still matters, but as a reason to BELIEVE the ratio rather than as evidence
for the claim. It enters through the small-sample shrinkage `n / (n + prior)`: a lift of 3.0
seen in four instances and the same lift seen in four thousand do not deserve the same
score, and rounding the small one up is the specific dishonesty this term prevents.

    sample = shrinkage(both, prior_count)          # n / (n + declared prior)
    effect = squashed_lift(lift, reference)        # 0.0 at independence, 1.0 at the reference
    value  = sample ** (2/3) * effect ** (1/3)     # SAMPLE-weighted: this is the recurrence half

Weighted GEOMETRICALLY, which is what makes both halves necessary rather than tradeable: a
zero on either factor is a zero overall. A pattern seen in three thousand instances at
independence scores nothing, and so does a spectacular ratio seen zero times. An arithmetic
mean would let a large sample of no association carry this component to two thirds of its
range, which is precisely how a count starts standing in for a finding.

`statistical_support` reads the SAME two factors with the exponents reversed. That is the
whole of the difference between them, and it is why they disagree -- informatively -- on a
rare pattern with a large ratio.

WHAT THIS IS NOT
----------------
Recurrence, even against a base rate, is not causation, is not direction, and does not
survive the removal of the temporal gate -- lift is symmetric and every direction in this
system comes from `core.temporal.verdict` at module 9's gate. Module 9's historical
generator keeps recurrence and association apart for this reason
(`generators/historical_frequency.py`); this component measures the first, and
`statistical_support.py` measures the second, against the same shared contingency table.
"""

from __future__ import annotations

from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import (
    SAMPLE_WEIGHTED,
    blend,
    citations,
    not_scorable,
    shrinkage,
    squashed_lift,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event, EvidenceKind

__all__ = ["HistoricalSupportScorer"]


class HistoricalSupportScorer:
    """Score recurrence against the base rate it must beat to mean anything."""

    component_name = "historical_support"

    def requirement(self) -> str:
        """Return what must be declared and present for this component to be scorable."""
        return (
            "confidence_scoring.lift_reference and "
            "confidence_scoring.small_sample_prior_count, plus a contingency table for "
            "this event-type pair -- which requires the pair to have been observed in "
            "sequence in at least one process instance, and the effect type to occur at "
            "all so a baseline rate exists."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return squashed lift, discounted for small samples."""
        reference = context.parameters.lift_reference
        prior_count = context.parameters.small_sample_prior_count
        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        if reference is None or prior_count is None or source is None or target is None:
            return not_scorable(self.component_name, self.requirement())

        table = context.base_rates.table_for(source.event_type, target.event_type)
        if table is None or table.lift is None:
            return not_scorable(self.component_name, self.requirement())

        lift = table.lift
        squashed = squashed_lift(lift, reference)
        discount = shrinkage(table.both, prior_count)
        value = blend(discount, squashed, SAMPLE_WEIGHTED)
        seen_here = tuple(
            item for item in claim.evidence() if item.kind is EvidenceKind.HISTORICAL_FREQUENCY
        )
        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            provenance_class=ProvenanceClass.STATISTICAL,
            evidence_record_ids=citations(source, target),
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=(
                    f"Across {table.instances} process instances, {table.with_cause} "
                    f"contained {source.event_type} and {table.both} of those went on to "
                    f"contain {target.event_type}. That is a rate of "
                    f"{table.conditional_rate:.3f} against a baseline rate of "
                    f"{table.baseline_rate:.3f} for {target.event_type} overall -- a lift "
                    f"of {lift:.3f}. The score is that lift on a declared scale, then "
                    f"discounted because {table.both} instances is a sample of that size."
                ),
                caveats=(
                    "A lift of 1.0 is independence and scores zero. A pattern that appears "
                    "in every instance is not evidence for anything, however large its "
                    "count -- which is why the count alone is never the score.",
                    "Recurrence is not causation and carries no direction: this ratio is "
                    "identical in both directions. The direction of this edge comes only "
                    "from the temporal gate.",
                    "Computed over the pinned dataset version, and over whatever slice of "
                    "it this run read. A different slice is a different number.",
                ),
                inputs=(
                    ComponentExplanation.count("process instances (denominator)", table.instances),
                    ComponentExplanation.count("instances with cause type", table.with_cause),
                    ComponentExplanation.count("instances with effect type", table.with_effect),
                    ComponentExplanation.count("instances with the sequenced pair", table.both),
                    ComponentExplanation.count("cause only", table.cause_only),
                    ComponentExplanation.count("effect only", table.effect_only),
                    ComponentExplanation.count("neither", table.neither),
                    ComponentExplanation.number("conditional rate", table.conditional_rate),
                    ComponentExplanation.number("baseline rate", table.baseline_rate),
                    ComponentExplanation.number("lift", lift),
                    ComponentExplanation.number("declared lift_reference", reference),
                    ComponentExplanation.number("lift on the declared scale", squashed),
                    ComponentExplanation.count("declared small_sample_prior_count", prior_count),
                    ComponentExplanation.number("small-sample discount", discount),
                    ("blend", "sample-weighted: discount^(2/3) * lift^(1/3)"),
                    ComponentExplanation.count(
                        "module 9 recurrence items on this edge", len(seen_here)
                    ),
                ),
            ),
        )
