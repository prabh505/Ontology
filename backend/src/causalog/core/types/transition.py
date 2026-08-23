"""`Transition` -- movement between two states (prd.md §20)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.provenance import ProvenanceClass

__all__ = ["Transition"]


class Transition(BaseModel):
    """A legal move from one state to another, attributed to the event that caused it.

    "Caused" here is the *observed* attribution recorded at state-derivation time -- the
    event whose occurrence the state change accompanies. It is not an inferred causal
    edge and never carries `INFERRED` provenance.

    A transition the active ontology does not declare legal is a hard error, never a
    tolerated anomaly (`CONVENTIONS.md` §7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    transition_id: str
    from_state_id: str
    to_state_id: str
    causing_event_id: str
    provenance_class: ProvenanceClass
