"""Legal-transition lookup, built from the ontology's own declared lifecycles.

Never a hardcoded state name or event type: every answer here comes from
`LifecycleView`, a plain view of the ontology's declared lifecycles adapted by
`causalog.extraction.ontology_adapters` -- this package may never import
`ontology_runtime` directly (LAW-DOMAIN, ADR-0002, forbidden edge F3).
"""

from __future__ import annotations

from dataclasses import dataclass

from causalog.core.ontology_view import LifecycleView

__all__ = ["LifecycleIndex", "TransitionOutcome", "build_lifecycle_index"]


@dataclass(frozen=True)
class TransitionOutcome:
    """What one event does to one entity's declared state machine."""

    to_state: str
    legal_from_current: bool
    """False when this event type triggers a transition, but not from the entity's
    current state -- the ontology-illegal-transition case."""
    candidate_from_states: tuple[str, ...]
    """Every `from_state` this event type is declared to fire from, for the error message
    and for resolving an entity's assumed initial state when none has been observed yet."""


@dataclass(frozen=True)
class LifecycleIndex:
    """One entity type's lifecycle, indexed by triggering event type."""

    entity_type: str
    lifecycle: LifecycleView

    def outcome_for(self, current_state: str | None, event_type: str) -> TransitionOutcome | None:
        """Return what `event_type` does from `current_state`, or `None` if it does nothing.

        `None` means "this event type triggers no declared transition for this entity
        type" -- per `docs/architecture.md`: "an event that changes nothing yields no
        transition." That is distinct from `legal_from_current=False`, which means the
        event DOES trigger a transition, just never from the state the entity is in.
        """
        candidates = [t for t in self.lifecycle.transitions if t.triggered_by == event_type]
        if not candidates:
            return None
        matching = [t for t in candidates if t.from_state == current_state]
        if matching:
            return TransitionOutcome(
                to_state=matching[0].to_state,
                legal_from_current=True,
                candidate_from_states=tuple(sorted({t.from_state for t in candidates})),
            )
        # Deterministic tie-break when the entity's current state is unknown (or wrong):
        # the lexicographically first declared from_state, so a rerun never disagrees
        # with itself about which candidate it reported.
        fallback = sorted(candidates, key=lambda t: t.from_state)[0]
        return TransitionOutcome(
            to_state=fallback.to_state,
            legal_from_current=False,
            candidate_from_states=tuple(sorted({t.from_state for t in candidates})),
        )


def build_lifecycle_index(lifecycles: tuple[LifecycleView, ...]) -> dict[str, LifecycleIndex]:
    """Return every declared lifecycle, keyed by entity type."""
    return {
        lifecycle.entity_type: LifecycleIndex(
            entity_type=lifecycle.entity_type, lifecycle=lifecycle
        )
        for lifecycle in lifecycles
    }
