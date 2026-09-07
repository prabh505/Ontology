"""`evidence_count` -- how much justification this claim carries. Volume only.

prd.md §49 names "Evidence Count" as a confidence component. This is that name, honestly
scoped: it counts, and it does nothing else. Whether the justifications are INDEPENDENT is a
different question with a different answer, and it is `evidence_diversity`'s -- which is
weighted higher, because ten repetitions of one line of reasoning are worth less than two
lines that disagree about nothing.

Splitting the two is the point. A single component blending count and diversity would let a
generator that fires repeatedly over one pair look like corroboration from several
directions, which is exactly the failure module 9's report already watches for when it flags
a saturated generator.

    value = n / (n + k)

Saturating rather than linear-to-a-cap, so the tenth justification adds less than the
second, and so the score never reaches 1.0 -- there is always more evidence one could have.
`k` is declared per pack and is the count at which that pack is half convinced.
"""

from __future__ import annotations

from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import (
    citations,
    not_scorable,
    saturating,
)
from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.types import Event

__all__ = ["EvidenceCountScorer"]


class EvidenceCountScorer:
    """Score the sheer volume of justification, and nothing else."""

    component_name = "evidence_count"

    def requirement(self) -> str:
        """Return what must be declared for this component to be scorable."""
        return (
            "confidence_scoring.evidence_count_saturation_k. The count at which a domain is "
            "half convinced is a domain judgement; a value written into engine code would "
            "not move when the domain is swapped (CONVENTIONS.md section 6a)."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return the saturating count of distinct evidence items on this claim."""
        half_at = context.parameters.evidence_count_saturation_k
        if half_at is None:
            return not_scorable(self.component_name, self.requirement())

        items = claim.evidence()
        value = saturating(len(items), half_at)
        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        present = tuple(event for event in (source, target) if event is not None)
        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            # The weakest class among the items counted. A count over mixed provenance is
            # never more certain about its origin than its weakest input (ADR-0005).
            provenance_class=combine(*(item.provenance_class for item in items))
            if items
            else ProvenanceClass.ASSUMED,
            evidence_record_ids=citations(*present),
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=(
                    f"{len(items)} distinct justification(s) support this pair. The scale "
                    f"is saturating: this pack is half convinced at {half_at}, and each "
                    "further justification adds less than the one before it."
                ),
                caveats=(
                    "This counts justifications; it does not ask whether they are "
                    "independent. Ten items of one kind score the same here as ten items "
                    "of ten kinds. The evidence_diversity component is what separates "
                    "them, and it is weighted higher than this one.",
                    "Evidence items are deduplicated by content address, so two generators "
                    "minting a byte-identical justification contribute one item, not two.",
                ),
                inputs=(
                    ComponentExplanation.count("distinct evidence items", len(items)),
                    ComponentExplanation.count(
                        "generators reaching this pair", len(claim.generator_ids())
                    ),
                    ComponentExplanation.count("declared saturation k", half_at),
                ),
            ),
        )
