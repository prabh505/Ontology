"""Everything the builder reads, supplied by value (`GraphFacts`), never fetched.

The same shape module 9's `GenerationContext` and module 10's `ScoringContext` establish,
and for the same two reasons: forbidden edge F4 means no reasoning package may reach a
store, and a context assembled by the caller is a context a test can build by hand.

`magnitude_measurements` arrives as `core.ontology_view` values produced by
`extraction.ontology_adapters` (ADR-0056). This package may never import `ontology_runtime`
(forbidden edge F3), so the pack reaches it already flattened into plain views.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.ontology_view import MagnitudeMeasurementView
from causalog.core.types import CandidateEdge, Event, Timeline, TimelineEntryKind, TimelineView
from causalog.rule_engine import (
    ConfidenceScoringSpec,
    EvaluationResult,
    GraphConstructionSpec,
    GraphFacts,
)

__all__ = ["GraphBuildContext"]


class GraphBuildContext(BaseModel):
    """One run's inputs to graph construction.

    Fields, and why each is needed rather than derivable:

    * `facts` -- the events, because a stored `CausalEdge` holds identifiers and not
      intervals (DEF-0002), so LAW-TIME cannot be re-verified without them. This is the
      whole reason the belt-and-braces check at promotion is possible at all.
    * `timelines` -- process instances, because a feedback loop that closes inside one
      instance is a different finding from one that closes across several.
    * `candidates` -- module 9's proposals, for lineage. Regrouped here exactly as module 10
      fused them, which records provenance and re-derives no judgement.
    * `parameters` -- the pack's `graph_construction` block. Every threshold.
    * `bands` -- the pack's `confidence_scoring` block, needed only to read the declared
      band SEQUENCE, so that "reaches STRONG" can be evaluated against the same floors module
      10 used rather than against a second copy of them.
    * `rule_evaluation` -- for edge typing. `None` means no rule metadata was available and
      every edge is typed structurally, which is reported and not silently treated as "no
      rule fired".
    * `magnitude_measurements` -- the declared quantities a propagation weight apportions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    facts: GraphFacts
    timelines: tuple[Timeline, ...]
    candidates: tuple[CandidateEdge, ...]
    parameters: GraphConstructionSpec
    bands: ConfidenceScoringSpec
    rule_evaluation: EvaluationResult | None = None
    magnitude_measurements: tuple[MagnitudeMeasurementView, ...] = ()
    run_id: str = Field(min_length=1)

    def events_by_id(self) -> dict[str, Event]:
        """Return every event addressable by identifier."""
        return {event.event_id: event for event in self.facts.events()}

    def instances_by_event_id(self) -> dict[str, tuple[str, ...]]:
        """Return, per event, the process instances that witnessed it, sorted.

        An event may sit in more than one timeline; the tuple is not collapsed to a single
        value, because picking one would make a loop's instance span depend on iteration
        sequence.
        """
        found: dict[str, set[str]] = {}
        for timeline in self.timelines:
            if timeline.view is not TimelineView.PROCESS_INSTANCE:
                continue
            for entry in timeline.entries:
                if entry.kind is not TimelineEntryKind.EVENT or entry.event_id is None:
                    continue
                found.setdefault(entry.event_id, set()).add(timeline.timeline_id)
        return {event_id: tuple(sorted(names)) for event_id, names in sorted(found.items())}

    def events_of_instance(self, timeline_id: str) -> tuple[str, ...]:
        """Return the event identifiers one process instance witnessed, in entry sequence."""
        for timeline in self.timelines:
            if timeline.timeline_id != timeline_id:
                continue
            return tuple(
                entry.event_id
                for entry in timeline.entries
                if entry.kind is TimelineEntryKind.EVENT and entry.event_id is not None
            )
        return ()
