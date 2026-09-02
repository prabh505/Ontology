"""`Transition` -- movement between two states (prd.md §20)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
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

    @classmethod
    def address(cls, from_state_id: str, to_state_id: str, causing_event_id: str) -> str:
        """Return the content-addressed identifier for a transition (`CONVENTIONS.md` §9).

        Payload recipe: `from_state_id | to_state_id | causing_event_id`.
        """
        return digest(
            IdentifierPrefix.TRANSITION,
            canonical_payload(
                canonical_text(from_state_id),
                canonical_text(to_state_id),
                canonical_text(causing_event_id),
            ),
        )
