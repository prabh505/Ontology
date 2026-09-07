"""`graph_connectivity` -- structural plausibility of the path between the two events.

The question is whether the entities the two events touch are connected in the relationship
graph at all. Two events over one entity are trivially connected; two events whose entities
sit two hops apart through a shared parent are plausibly related; two events whose entities
have no path between them are structurally implausible however well they correlate.

**TODAY THIS COMPONENT IS MISSING ON EVERY EDGE, AND THAT IS PUBLISHED RATHER THAN HIDDEN.**

The relationship graph is module 7's output and module 8's projection. Neither exists
(`CONTEXT.md` §3), so `GraphFacts.relationships()` returns an empty tuple and there is no
structure to measure. Module 9's `structural_path` generator already reports zero proposals
for the same reason and its report flags it as degenerate.

Three responses were available and two of them are dishonest:

1. Drop the component from the vector. Then `weighted_mean` renormalizes over what remains,
   every edge silently scores as though connectivity had been checked and found irrelevant,
   and nothing in the artifact records that a declared component was never computed.
2. Score it 1.0 as a neutral value. This manufactures support out of an absence.
3. Emit it MISSING at 0.0, so it costs the edge score, and count it in the report.

The third is what happens. The cost is real -- roughly a tenth of every edge's addend weight
-- and it is the correct cost: an engine that could not check structural plausibility should
be less confident than one that checked and was satisfied. When module 7 lands, this scorer
starts returning values without anything else in the module changing.
"""

from __future__ import annotations

from causalog.causal_engine.confidence_scorer.context import (
    FusedClaim,
    ScoredComponent,
    ScoringContext,
)
from causalog.causal_engine.confidence_scorer.explain import ComponentExplanation
from causalog.causal_engine.confidence_scorer.scorers.shared import citations, not_scorable
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Event

__all__ = ["GraphConnectivityScorer"]

#: How many hops out from the cause's entities the walk goes before giving up. A named
#: bound on THIS module's traversal, not a domain policy about the data: it governs how much
#: work is done, not which hypotheses are entertained, which is why it is not in the pack.
#: Matches the shape of `MAX_PROPAGATION_DEPTH` in module 12's contract.
MAX_CONNECTIVITY_HOPS = 3


class GraphConnectivityScorer:
    """Score how directly the two events' entities are connected."""

    component_name = "graph_connectivity"

    def requirement(self) -> str:
        """Return what must exist for this component to be scorable."""
        return (
            "at least one Relationship in the fact set. The relationship graph is module "
            "7's output and module 8's projection, and neither exists yet (CONTEXT.md "
            "section 3) -- so this component is MISSING on every edge today rather than "
            "scored zero or silently omitted, and every edge is scored lower for it."
        )

    def score(
        self,
        claim: FusedClaim,
        context: ScoringContext,
        events_by_id: dict[str, Event],
    ) -> ScoredComponent:
        """Return connectivity by shortest path, or MISSING when there is no graph."""
        relationships = context.facts.relationships()
        source = events_by_id.get(claim.source_event_id)
        target = events_by_id.get(claim.target_event_id)
        if not relationships or source is None or target is None:
            return not_scorable(self.component_name, self.requirement())

        cause_entities = frozenset((*source.source_entity_ids, *source.target_entity_ids))
        effect_entities = frozenset((*target.source_entity_ids, *target.target_entity_ids))
        if not cause_entities or not effect_entities:
            return not_scorable(self.component_name, self.requirement())

        adjacency: dict[str, set[str]] = {}
        for relationship in relationships:
            adjacency.setdefault(relationship.source_entity_id, set()).add(
                relationship.target_entity_id
            )
            adjacency.setdefault(relationship.target_entity_id, set()).add(
                relationship.source_entity_id
            )

        hops = _shortest_hops(cause_entities, effect_entities, adjacency)
        if hops is None:
            value = 0.0
            sentence = (
                "The entities these two events touch are not connected in the "
                f"relationship graph within {MAX_CONNECTIVITY_HOPS} hops. That is a "
                "structural argument against the claim: a cause and an effect with no path "
                "between the things they concern is implausible however well they correlate."
            )
        else:
            # Zero hops means a shared entity, which is the strongest structural link
            # available; each further hop through an intermediary halves it.
            value = 1.0 / (2.0**hops)
            sentence = (
                f"The entities these two events touch are {hops} hop(s) apart in the "
                "relationship graph. A shared entity scores 1.0 and each further hop "
                "through an intermediary halves the score, because a path through an "
                "intermediary is a weaker link than identity."
            )

        return ScoredComponent(
            component_name=self.component_name,
            value=value,
            provenance_class=ProvenanceClass.OBSERVED,
            evidence_record_ids=citations(source, target),
            explanation=ComponentExplanation(
                component_name=self.component_name,
                plain_language=sentence,
                caveats=(
                    "Structural connectivity is a plausibility argument, not evidence of "
                    "causation. A well-connected node is suggestive of nothing on its own, "
                    "which is why this carries the smallest addend weight.",
                    "The walk is bounded at "
                    f"{MAX_CONNECTIVITY_HOPS} hops. Reaching the bound is reported as "
                    "unconnected-within-the-bound, never as unconnected.",
                ),
                inputs=(
                    ComponentExplanation.count("relationships in the fact set", len(relationships)),
                    ComponentExplanation.count("cause entities", len(cause_entities)),
                    ComponentExplanation.count("effect entities", len(effect_entities)),
                    ("shortest path (hops)", "none within bound" if hops is None else str(hops)),
                    ComponentExplanation.count("hop bound", MAX_CONNECTIVITY_HOPS),
                ),
            ),
        )


def _shortest_hops(
    start: frozenset[str],
    goal: frozenset[str],
    adjacency: dict[str, set[str]],
) -> int | None:
    """Return the fewest hops from any start entity to any goal entity, or None.

    Breadth-first and bounded. Returns 0 when the two sets intersect -- a shared
    participant is a connection at distance zero, not a special case.
    """
    if start & goal:
        return 0
    seen = set(start)
    frontier = set(start)
    for hop in range(1, MAX_CONNECTIVITY_HOPS + 1):
        expanded: set[str] = set()
        for entity_id in frontier:
            expanded |= adjacency.get(entity_id, set())
        expanded -= seen
        if not expanded:
            return None
        if expanded & goal:
            return hop
        seen |= expanded
        frontier = expanded
    return None
