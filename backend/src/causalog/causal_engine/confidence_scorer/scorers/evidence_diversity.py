"""`evidence_diversity` -- how many INDEPENDENT lines of reasoning agree, not how many items.

This is the component `evidence_count` deliberately is not, and it is weighted above it.
Two justifications of different kinds -- a rule fired AND the pair recurs against its base
rate -- say something ten repetitions of one kind cannot: two lines of reasoning that share
no premises arrived at the same place. Ten items from one generator over one pair are one
argument stated ten times.

**This component is computable only because of a decision made one module earlier.** Module
9 keeps parallel candidates -- one per generator over a pair -- rather than merging them, and
says in `graph.py` that doing so is "exactly what module 10 needs to assemble a decomposed
confidence vector from". `fuse.py` gathers that group, and diversity is a property of the
group that no single `CandidateEdge` could carry.

THE MEASURE
-----------
    value = (distinct evidence kinds - 1) / (reachable kinds - 1)   ... call this k
            (distinct generators   - 1) / (reachable generators - 1) ... call this g
    value = (k + g) / 2

Two axes averaged, because they can disagree and the disagreement is informative: two
generators can mint items of one kind, and one generator can mint items of two kinds. A
single justification of a single kind scores exactly 0.0 -- it is not diverse, and calling
it slightly diverse would be arithmetic flattering a single source.

Normalized against what was REACHABLE in this run rather than against the enum, so that a
run where three generators could not run does not permanently cap every edge's diversity at
a level nothing could reach. The reachable counts travel in the explanation.
"""

from __future__ import annotations

from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import citations
from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.types import Event

__all__ = ["EvidenceDiversityScorer"]


class EvidenceDiversityScorer:
    """Score independence of support, not volume of it."""

    component_name = "evidence_diversity"

    def __init__(self, reachable_kinds: int, reachable_generators: int) -> None:
        """Bind what this run could have produced, which is the normalizing denominator.

        Passed in rather than read from the enums: a run in which three generators were
        NOT_RUNNABLE could never reach the full spread, and normalizing against a spread
        nothing could achieve would silently cap every edge in that run.
        """
        self.reachable_kinds = max(reachable_kinds, 1)
        self.reachable_generators = max(reachable_generators, 1)

    def requirement(self) -> str:
        """Return what must be present for this component to be scorable.

        Nothing, in practice: a fused claim carries at least one candidate and every
        candidate carries at least one evidence item (LAW-EVIDENCE), so diversity is
        always computable. A single-source claim scores 0.0, which is a measurement and
        not an absence.
        """
        return (
            "nothing beyond the claim itself; every fused claim carries at least one "
            "evidence item, so this component is always computable. A single-kind, "
            "single-generator claim scores exactly 0.0 -- a measured zero, not a missing "
            "component."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return the mean of kind spread and generator spread."""
        items = claim.evidence()
        kinds = sorted({item.kind.value for item in items})
        generators = claim.generator_ids()
        kind_spread = _spread(len(kinds), self.reachable_kinds)
        generator_spread = _spread(len(generators), self.reachable_generators)
        value = (kind_spread + generator_spread) / 2.0

        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        present = tuple(event for event in (source, target) if event is not None)
        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            provenance_class=combine(*(item.provenance_class for item in items))
            if items
            else ProvenanceClass.ASSUMED,
            evidence_record_ids=citations(*present),
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=(
                    f"Support for this pair comes from {len(kinds)} distinct kind(s) of "
                    f"evidence, produced by {len(generators)} independent generator(s): "
                    f"{', '.join(kinds)} via {', '.join(generators)}. Independent lines of "
                    "reasoning reaching one conclusion count for more than one line "
                    "repeated, which is why this is weighted above raw evidence count."
                ),
                caveats=(
                    "Independence here means different reasoning, not statistical "
                    "independence. Two generators can rest on the same underlying "
                    "coincidence in the data -- the shared-entity and shared-identifier "
                    "generators are the obvious pair -- and nothing here detects that.",
                    "Normalized against what THIS run could reach, not against the full "
                    "vocabulary. A run with generators that could not run has a smaller "
                    "denominator, so diversity scores are not comparable across runs with "
                    "different generator availability.",
                ),
                inputs=(
                    ComponentExplanation.count("distinct evidence kinds", len(kinds)),
                    ComponentExplanation.count("reachable kinds this run", self.reachable_kinds),
                    ComponentExplanation.number("kind spread", kind_spread),
                    ComponentExplanation.count("distinct generators", len(generators)),
                    ComponentExplanation.count(
                        "reachable generators this run", self.reachable_generators
                    ),
                    ComponentExplanation.number("generator spread", generator_spread),
                    ComponentExplanation.count("total evidence items", len(items)),
                ),
            ),
        )


def _spread(observed: int, reachable: int) -> float:
    """Return `(observed - 1) / (reachable - 1)`, clamped to `[0, 1]`.

    One source scores exactly zero. `reachable == 1` means nothing could have been diverse
    in this run, and the answer is zero rather than an undefined division -- an edge is not
    credited with diversity a run could not have produced.
    """
    if reachable <= 1 or observed <= 1:
        return 0.0
    return min(1.0, (observed - 1) / (reachable - 1))
