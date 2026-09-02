"""`GraphFacts` -- what the evaluator reads, as values rather than as a store.

Forbidden edge F4 (`docs/architecture.md` §1.4) means no reasoning package may import
`causalog.persistence`; only `orchestration` wires an adapter to a port. So the evaluator
takes its facts as a protocol satisfied by a plain value, and every test runs without a
database.

**Why not `TemporalPropertyGraph`.** Module 8 does not exist (`CONTEXT.md` §3: not-started),
so the graph this module is documented as evaluating over cannot yet be handed to it. A
protocol taken by value is what module 8 will satisfy when it lands, without this module
changing. The alternative -- waiting for module 8 -- would leave seam 4 unbuilt and
`rule_pack_version` unset, which is the last input `RunKey` is missing.

Every method returns a tuple in the canonical sequence its docstring names. An unsequenced
read breaks determinism silently: two evaluations differ only in the sequence of a list
nobody was looking at (`CONVENTIONS.md` §11).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from causalog.core.errors import ContractViolationError
from causalog.core.types import Event, Relationship, State

__all__ = ["FactSet", "GraphFacts"]


@runtime_checkable
class GraphFacts(Protocol):
    """The observed structure a rule pack is evaluated against.

    Nothing here is inferred. These are the facts modules 3 through 8 produce, and the rule
    engine's whole job is to propose which of them stand in a claimed relation -- never to
    add to them.
    """

    def events(self) -> tuple[Event, ...]:
        """Return every event, sequenced by `(t_earliest, t_latest, event_id)`."""
        ...

    def states(self) -> tuple[State, ...]:
        """Return every derived state, sequenced by `state_id`."""
        ...

    def relationships(self) -> tuple[Relationship, ...]:
        """Return every structural relationship, sequenced by `relationship_id`."""
        ...


class FactSet(BaseModel):
    """The in-memory `GraphFacts` the evaluator is handed today.

    Constructing one sequences every collection canonically, so a caller that assembled its
    inputs in a different sequence still produces one value. Sequencing here rather than
    trusting the caller is the same choice `Event.address` makes about sorting its
    participants: the canonical sequence is part of the contract, so it is applied at the
    boundary rather than assumed to have been applied outside it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_values: tuple[Event, ...] = ()
    state_values: tuple[State, ...] = ()
    relationship_values: tuple[Relationship, ...] = ()

    @classmethod
    def of(
        cls,
        events: tuple[Event, ...] = (),
        states: tuple[State, ...] = (),
        relationships: tuple[Relationship, ...] = (),
    ) -> FactSet:
        """Return a fact set with every collection in canonical sequence."""
        sequenced_events = tuple(
            sorted(
                events,
                key=lambda item: (
                    item.occurred_at.t_earliest,
                    item.occurred_at.t_latest,
                    item.event_id,
                ),
            )
        )
        seen = {event.event_id for event in sequenced_events}
        if len(seen) != len(sequenced_events):
            raise ContractViolationError(
                "FactSet was given two events under one event_id. Events are content "
                "addressed, so this is a digest collision on differing payloads or a "
                "caller that duplicated a value; neither is recoverable here "
                "(CONVENTIONS.md §9)."
            )
        return cls(
            event_values=sequenced_events,
            state_values=tuple(sorted(states, key=lambda item: item.state_id)),
            relationship_values=tuple(sorted(relationships, key=lambda item: item.relationship_id)),
        )

    def events(self) -> tuple[Event, ...]:
        """Return every event, sequenced by `(t_earliest, t_latest, event_id)`."""
        return self.event_values

    def states(self) -> tuple[State, ...]:
        """Return every derived state, sequenced by `state_id`."""
        return self.state_values

    def relationships(self) -> tuple[Relationship, ...]:
        """Return every structural relationship, sequenced by `relationship_id`."""
        return self.relationship_values
