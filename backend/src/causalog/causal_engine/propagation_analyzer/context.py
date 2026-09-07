"""Everything module 12 reads, supplied by value (`GraphFacts`), never fetched.

The shape modules 9 and 10 and the Causal Graph Builder established, and for the same two
reasons: forbidden edge F4 means no reasoning package may reach a store, and a context
assembled by the caller is a context a test can build by hand.

Two fields deserve their rationale here rather than only on the field.

`cache` is a `DerivedCache` **protocol value**, injected. The port is declared in
`core/ports` and implemented in `persistence`, and F4 forbids this package from importing
the latter -- so the adapter arrives already wired, or does not arrive at all. `None` means
no cache was supplied and every query recomputes, which is slower and answers identically.
That is the whole contract: flushing the cache changes latency and never an answer.

`magnitude_measurements` and `actionability` arrive as `core.ontology_view` values produced
by `extraction.ontology_adapters`. This package may never import `ontology_runtime`
(forbidden edge F3), so the pack reaches it already flattened into plain views.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from causalog.causal_engine.propagation_analyzer.view import GraphView
from causalog.core.ontology_view import MagnitudeMeasurementView
from causalog.core.ports.persistence import DerivedCache
from causalog.core.types import Event, Timeline, TimelineEntryKind, TimelineView
from causalog.rule_engine import GraphFacts, PropagationAnalysisSpec

__all__ = ["CACHE_TTL_SECONDS", "PropagationContext"]

#: How long a cached traversal lives. Required by the port -- there is no "no expiry" path,
#: because an entry nobody has chosen a lifetime for is an entry nobody will remove. One
#: hour: long enough that the five queries of one report share the precomputation, short
#: enough that a stale entry cannot outlive the session that produced it. It cannot outlive
#: its RUN under any value, because the run is in the key.
CACHE_TTL_SECONDS: int = 3600


class PropagationContext(BaseModel):
    """One run's inputs to propagation analysis.

    Fields, and why each is needed rather than derivable:

    * `facts` -- the events, because a link holds identifiers and not the events themselves.
      Magnitude, participation, actionability and type all come from here.
    * `timelines` -- process instances, because a measurement is defined over one instance
      and because "how many process instances were affected" is one of prd.md §30's
      measures.
    * `view` -- the adjacency, and the standing it was drawn under. Both graphs satisfy one
      protocol, so this module never learns which it is walking except to record it.
    * `parameters` -- the pack's `propagation_analysis` block. Every bound. An absent one
      means the traversal cannot run and says so.
    * `magnitude_measurements` -- the declared quantities a consequence's magnitude is read
      from.
    * `magnitude_attributions` -- which measurement supplies which effect type's magnitude.
      Read from the `graph_construction` block rather than duplicated into a new one: the
      quantity a weight apportions and the quantity a consequence is worth are the same
      quantity, and two declarations of it could disagree.
    * `cache` -- optional, recomputable only. See this module's docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    facts: GraphFacts
    timelines: tuple[Timeline, ...]
    view: GraphView
    parameters: PropagationAnalysisSpec
    magnitude_measurements: tuple[MagnitudeMeasurementView, ...] = ()
    #: `(effect_event_type, measurement_id)` pairs, sorted, flattened from the pack's
    #: `graph_construction.magnitude_attributions` by the caller.
    magnitude_attributions: tuple[tuple[str, str], ...] = ()
    cache: DerivedCache | None = None
    run_id: str = Field(min_length=1)

    _events_by_id: dict[str, Event] | None = PrivateAttr(default=None)
    _instances_by_event: dict[str, tuple[str, ...]] | None = PrivateAttr(default=None)

    def events_by_id(self) -> dict[str, Event]:
        """Return every event addressable by identifier, built once per context.

        Lazily cached on a private attribute rather than computed per call: a traversal
        touches this on every node, and a frozen model cannot hold a computed field.
        """
        if self._events_by_id is None:
            self._events_by_id = {event.event_id: event for event in self.facts.events()}
        return self._events_by_id

    def instances_by_event_id(self) -> dict[str, tuple[str, ...]]:
        """Return, per event, the process instances that witnessed it, sorted.

        An event may sit in more than one timeline and the tuple is not collapsed to a
        single value: picking one would make an affected-instance count depend on iteration
        sequence.
        """
        if self._instances_by_event is None:
            found: dict[str, set[str]] = {}
            for timeline in self.timelines:
                if timeline.view is not TimelineView.PROCESS_INSTANCE:
                    continue
                for entry in timeline.entries:
                    if entry.kind is not TimelineEntryKind.EVENT or entry.event_id is None:
                        continue
                    found.setdefault(entry.event_id, set()).add(timeline.timeline_id)
            self._instances_by_event = {
                event_id: tuple(sorted(names)) for event_id, names in sorted(found.items())
            }
        return self._instances_by_event

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

    def measurement_for(self, event_type: str) -> str | None:
        """Return the measurement identifier declared for one effect type, or None."""
        for declared_type, measurement_id in self.magnitude_attributions:
            if declared_type == event_type:
                return measurement_id
        return None

    def measurement_by_id(self, identifier: str) -> MagnitudeMeasurementView | None:
        """Return one declared measurement view by identifier, or None if undeclared."""
        for measurement in self.magnitude_measurements:
            if measurement.id == identifier:
                return measurement
        return None
