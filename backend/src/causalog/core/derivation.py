"""Derived views over the canonical types.

Some things prd.md §20 lists as *fields* are properly *functions*. An entity's current
condition is the clearest case: it is not a property of the entity, it is a property of the
entity **and an instant**, and the moment you store it you have to choose between mutating
a frozen artifact and letting its content address drift as history advances.

This module holds those functions. Everything here is pure: no I/O, no clock, no ambient
state. The instant is always an argument, never `datetime.now()` -- reading the wall clock
inside a reasoning module is a determinism defect (`CONVENTIONS.md` §11).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import canonical_instant
from causalog.core.types.state import State

__all__ = ["current_state", "states_holding_at"]


def states_holding_at(
    states: Iterable[State],
    entity_id: str,
    as_of: datetime,
) -> tuple[State, ...]:
    """Return every state of one entity whose interval contains `as_of`, sequenced.

    "Contains" is inclusive of both bounds, matching `TimeInterval`'s closed-interval
    definition (`CONVENTIONS.md` §10).

    More than one state may hold at once and that is not an error here. Two overlapping
    states are a finding about the data -- a state machine the source did not respect --
    and this function's job is to surface it, not to arbitrate it. The caller decides
    whether overlap is tolerable for its purpose; `current_state` decides that it is not.

    The result is sequenced by `(t_earliest, t_latest, state_id)`, the canonical event sort
    key of `CONVENTIONS.md` §11 applied to states, so repeated calls agree byte for byte.

    Raises:
        ContractViolationError: if `as_of` is naive or is not UTC.
    """
    canonical_instant(as_of)  # rejects naive and non-UTC instants
    holding = [
        state
        for state in states
        if state.entity_id == entity_id
        and state.held_over.t_earliest <= as_of <= state.held_over.t_latest
    ]
    return tuple(
        sorted(
            holding,
            key=lambda state: (
                state.held_over.t_earliest,
                state.held_over.t_latest,
                state.state_id,
            ),
        )
    )


def current_state(
    states: Iterable[State],
    entity_id: str,
    as_of: datetime,
) -> State | None:
    """Return the single state one entity is in at `as_of`, or None if none holds.

    This is prd.md §20's "Current State" for an entity, computed rather than stored. See
    `causalog.core.types.entity.Entity` for why it is not a field.

    `None` means no state record covers that instant. It is a legitimate answer -- an
    entity observed before its first recorded state has no current state -- and it is
    deliberately distinct from an error, so that a caller can tell "nothing was recorded"
    apart from "the records contradict each other".

    Raises:
        ContractViolationError: if more than one state holds at that instant. Two
            simultaneous states are a contradiction in the source, and returning either one
            would resolve it by arbitrary choice; the run must surface it instead. Use
            `states_holding_at` when overlap is the thing being examined.
    """
    holding = states_holding_at(states, entity_id, as_of)
    if not holding:
        return None
    if len(holding) > 1:
        raise ContractViolationError(
            f"causalog.core.derivation.current_state found {len(holding)} simultaneous "
            f"states for entity {entity_id} at {canonical_instant(as_of)}: "
            f"{sorted(state.state_id for state in holding)}. Returning one of them would "
            "resolve a contradiction in the source by arbitrary choice; use "
            "states_holding_at to inspect the overlap."
        )
    return holding[0]
