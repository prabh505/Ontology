"""As-of queries: a thin, documented wrapper over `causalog.core.derivation`.

Deliberately not a reimplementation. `core.derivation.current_state` already enforces the
"exactly one state holds, or raise" contract (frozen, `docs/contracts.md`); this module
only packages its answer with the two extra facts an as-of caller usually wants next: which
event produced the state, and how sure the engine is that the claim is correct.

**`State` carries no `ConfidenceVector`.** LAW-EVIDENCE's numeric-confidence machinery is
scoped to causal edges (module 10, `Confidence Scorer`) -- a deliberate boundary, not an
omission. "Confidence" for a state-as-of query is expressed the only way a `State` can
express it: its `provenance_class` (`OBSERVED` vs. `ASSUMED`) and its `held_over.precision`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from causalog.core.derivation import current_state
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision
from causalog.core.types import State

__all__ = ["StateAsOf", "state_as_of"]


@dataclass(frozen=True)
class StateAsOf:
    """One entity's state at a queried instant, with what produced it and how sure."""

    state: State
    produced_by_event_id: str
    confidence_class: ProvenanceClass
    precision: Precision


def state_as_of(states: Iterable[State], entity_id: str, as_of: datetime) -> StateAsOf | None:
    """Return the state holding for `entity_id` at `as_of`, or `None` if none holds.

    Raises whatever `current_state` raises on a genuine contradiction (more than one state
    holding at once) -- that guard is untouched here.
    """
    resolved = current_state(states, entity_id, as_of)
    if resolved is None:
        return None
    return StateAsOf(
        state=resolved,
        produced_by_event_id=resolved.derived_from_event_id,
        confidence_class=resolved.provenance_class,
        precision=resolved.held_over.precision,
    )
