"""The typed language a hypothetical is expressed in (ADR-0066).

prd.md §33 gives three examples -- move an occurrence earlier, make a resource available,
raise a capacity -- and treats them as one thing. They are three different operations on the
graph, and a free-form mutation would let a caller ask for a fourth the domain does not
admit: an entity in a state its lifecycle cannot reach, a step inserted where no process
declares one, an antecedent moved past its own consequent.

**Simulating an impossible world produces a confidently wrong answer**, and it produces it
through machinery that looks like it is working: the propagation is correct, the belief
composes correctly, the report renders correctly, and the premise is unreachable. Nothing
downstream can detect that, which is why the refusal happens here, at the boundary, before
anything is simulated.

Five kinds, as a discriminated union on `kind`, mirroring `CausalEdgePayload`'s shape so a
deserialized change cannot land in the wrong branch. The set is CLOSED because the kind
participates in the content address: an unmodelled kind would produce identifiers no rerun
could reproduce, which is the argument `CausalEdgeKind` already makes for itself.

A REJECTION IS AN ARTIFACT, NOT AN ERROR PATH
---------------------------------------------
`RejectedIntervention` has the same standing as the world that was simulated, following the
Causal Graph Builder's rejection ledger (ADR-0054): "what did you consider and refuse?" is a
question a reader is entitled to ask of a hypothetical, and a simulator that answers only
with what it accepted is asserting a conclusion while withholding the alternatives. A run
whose changes were all refused publishes the ledger and NO world -- never an unchanged world,
which would read as "the change had no effect".

**No domain vocabulary appears below.** Nothing here reads a type name.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_instant,
    canonical_payload,
    canonical_sequence,
    canonical_text,
    digest,
    format_float,
)

__all__ = [
    "ChangeAttribute",
    "ChangeEntityState",
    "InsertEvent",
    "Intervention",
    "InterventionKind",
    "InterventionPayload",
    "RejectedIntervention",
    "RejectionReason",
    "RemoveEvent",
    "ShiftTiming",
    "canonical_intervention_payload",
]


class InterventionKind(str, Enum):
    """The closed set of changes a hypothetical may express.

    Closed because the kind is part of the intervention's content-addressed identifier and
    of the simulated world's: an unmodelled kind would produce an address no rerun could
    reproduce (`CONVENTIONS.md` §9).
    """

    SHIFT_TIMING = "SHIFT_TIMING"
    """Move one occurrence's instant by a signed amount."""

    REMOVE_EVENT = "REMOVE_EVENT"
    """Delete one occurrence and every link that ran through it."""

    INSERT_EVENT = "INSERT_EVENT"
    """Place a declared kind of occurrence at a stated instant."""

    CHANGE_ATTRIBUTE = "CHANGE_ATTRIBUTE"
    """Set one ontology-declared changeable attribute to a different value."""

    CHANGE_ENTITY_STATE = "CHANGE_ENTITY_STATE"
    """Put one participant into a different declared state at a stated instant."""


class ShiftTiming(BaseModel):
    """Move an occurrence by a signed number of seconds.

    Seconds rather than a `timedelta` on the wire, because a canonical payload has one text
    form for a float and none for a duration, and an address computed two ways is two
    addresses.

    Invariants:
      * the shift is non-zero. A shift of zero moves nothing and would be reported as a
        change that had no effect, which is a different and much stronger claim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[InterventionKind.SHIFT_TIMING] = InterventionKind.SHIFT_TIMING
    target_event_id: str
    shift_seconds: float

    @model_validator(mode="after")
    def _check_invariants(self) -> ShiftTiming:
        """Enforce the documented invariants at construction."""
        if self.shift_seconds == 0.0:
            raise ContractViolationError(
                "ShiftTiming.shift_seconds is zero. A change that moves nothing would be "
                "simulated, produce an identical world, and be read as evidence that the "
                "timing does not matter -- which is a far stronger claim than the input made."
            )
        return self

    def address_fields(self) -> tuple[str, ...]:
        """Return the escaped leaves this payload contributes to an address.

        Leaves rather than a joined payload: `canonical_payload` refuses a field that already
        holds a separator, so a nested payload cannot be embedded in an outer one. Every
        change therefore contributes its leaves and the address joins once, at one level.
        """
        return (canonical_text(self.target_event_id), format_float(self.shift_seconds))

    def targets(self) -> tuple[str, ...]:
        """Return the identifiers of the base-world occurrences this change names."""
        return (self.target_event_id,)


class RemoveEvent(BaseModel):
    """Delete an occurrence, and with it every link that ran through it.

    What then stops occurring is a re-reachability question and not a subtraction: a
    consequence with another surviving antecedent does not disappear (ADR-0061). That is
    settled during propagation, not here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[InterventionKind.REMOVE_EVENT] = InterventionKind.REMOVE_EVENT
    target_event_id: str

    def address_fields(self) -> tuple[str, ...]:
        """Return the escaped leaves this payload contributes to an address."""
        return (canonical_text(self.target_event_id),)

    def targets(self) -> tuple[str, ...]:
        """Return the identifiers of the base-world occurrences this change names."""
        return (self.target_event_id,)


class InsertEvent(BaseModel):
    """Place a declared kind of occurrence at a stated instant.

    The inserted occurrence has no links in the stated graph, because nothing was ever
    inferred about an occurrence that did not happen. It therefore propagates NOTHING, and
    the report says so rather than letting the absence read as "inserting it changed
    nothing". Attaching links to it would mean inventing causal claims inside a simulator,
    which is module 10's work and would be an assertion nobody scored.

    Invariants:
      * the instant is timezone-aware; local time never exists inside the engine.
      * `after_event_id` and `before_event_id` name the neighbours the insertion sits
        between, so process legality is checkable. At least one is required -- an insertion
        anchored to nothing cannot be checked against any declared sequence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[InterventionKind.INSERT_EVENT] = InterventionKind.INSERT_EVENT
    event_type: str
    at_instant: datetime
    after_event_id: str | None = None
    before_event_id: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> InsertEvent:
        """Enforce the documented invariants at construction."""
        if self.at_instant.tzinfo is None:
            raise ContractViolationError(
                "InsertEvent.at_instant is naive. Local time never exists inside the engine "
                "(CONVENTIONS.md §10), and a hypothetical is not an exemption."
            )
        if self.after_event_id is None and self.before_event_id is None:
            raise ContractViolationError(
                "InsertEvent names neither an occurrence it follows nor one it precedes. An "
                "insertion anchored to nothing cannot be checked against any declared "
                "sequence, so it would be admitted without ever being validated."
            )
        return self

    def address_fields(self) -> tuple[str, ...]:
        """Return the escaped leaves this payload contributes to an address."""
        return (
            canonical_text(self.event_type),
            canonical_instant(self.at_instant),
            canonical_text(self.after_event_id or ""),
            canonical_text(self.before_event_id or ""),
        )

    def targets(self) -> tuple[str, ...]:
        """Return the identifiers of the base-world occurrences this change names."""
        return tuple(
            sorted(
                identifier
                for identifier in (self.after_event_id, self.before_event_id)
                if identifier is not None
            )
        )


class ChangeAttribute(BaseModel):
    """Set one ontology-declared changeable attribute to a different value.

    The value is carried as text, as `Event.changed_attributes` carries every attribute:
    one wire form, one canonical text form, one address. Whether the text is admissible for
    the declared type is checked against the pack, not here -- this type does not know what
    the attribute means and must not learn.

    Invariants:
      * the new value differs from nothing, because the base value is not visible here. A
        change to the value the attribute already holds is caught at validation, where the
        base world is in hand.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[InterventionKind.CHANGE_ATTRIBUTE] = InterventionKind.CHANGE_ATTRIBUTE
    target_event_id: str
    attribute_name: str
    new_value: str

    @model_validator(mode="after")
    def _check_invariants(self) -> ChangeAttribute:
        """Enforce the documented invariants at construction."""
        if not self.attribute_name.strip():
            raise ContractViolationError(
                "ChangeAttribute.attribute_name is empty; there is nothing to check against "
                "a declaration and nothing to change."
            )
        return self

    def address_fields(self) -> tuple[str, ...]:
        """Return the escaped leaves this payload contributes to an address."""
        return (
            canonical_text(self.target_event_id),
            canonical_text(self.attribute_name),
            canonical_text(self.new_value),
        )

    def targets(self) -> tuple[str, ...]:
        """Return the identifiers of the base-world occurrences this change names."""
        return (self.target_event_id,)


class ChangeEntityState(BaseModel):
    """Put one participant into a different declared state at a stated instant.

    Checked against the entity type's declared lifecycle, which is the one place the domain
    says which conditions follow which. A state machine is exactly the structure that makes
    "this world is impossible" a decidable question rather than a matter of taste.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[InterventionKind.CHANGE_ENTITY_STATE] = InterventionKind.CHANGE_ENTITY_STATE
    target_entity_id: str
    from_state: str
    to_state: str
    at_instant: datetime

    @model_validator(mode="after")
    def _check_invariants(self) -> ChangeEntityState:
        """Enforce the documented invariants at construction."""
        if self.at_instant.tzinfo is None:
            raise ContractViolationError(
                "ChangeEntityState.at_instant is naive. Local time never exists inside the "
                "engine (CONVENTIONS.md §10)."
            )
        if self.from_state == self.to_state:
            raise ContractViolationError(
                f"ChangeEntityState names {self.from_state!r} on both sides; a transition to "
                "the state already held changes nothing and would be reported as a change "
                "that had no effect."
            )
        return self

    def address_fields(self) -> tuple[str, ...]:
        """Return the escaped leaves this payload contributes to an address."""
        return (
            canonical_text(self.target_entity_id),
            canonical_text(self.from_state),
            canonical_text(self.to_state),
            canonical_instant(self.at_instant),
        )

    def targets(self) -> tuple[str, ...]:
        """Return the identifiers of the base-world occurrences this change names.

        A state change names an entity rather than an occurrence, so it names none. The
        occurrences it reaches are found during propagation, through the participants each
        occurrence declares.
        """
        return ()


#: The discriminated union. `kind` is the discriminator, so pydantic selects the payload
#: type from the data itself and a deserialized change cannot land in the wrong branch.
InterventionPayload = Annotated[
    ShiftTiming | RemoveEvent | InsertEvent | ChangeAttribute | ChangeEntityState,
    Field(discriminator="kind"),
]


class Intervention(BaseModel):
    """One addressed change, with the reason it was proposed.

    Addressed because two runs handed the same change must produce the same simulated
    world, and a world whose input cannot be named cannot be reproduced (`CONVENTIONS.md`
    §9). `rationale` is required and carries no weight in the address: it is what a reader
    needs and what a rerun must not depend on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intervention_id: str
    payload: InterventionPayload
    rationale: str = Field(min_length=1)

    @property
    def kind(self) -> InterventionKind:
        """Return the change's kind, read off the payload rather than stored twice."""
        return self.payload.kind

    @classmethod
    def address(cls, payload: InterventionPayload) -> str:
        """Return the content address of a change.

        The rationale is excluded. Two callers proposing the identical change for different
        stated reasons are proposing one change, and giving them two addresses would make
        the simulated world's identity depend on prose.
        """
        return digest(
            IdentifierPrefix.INTERVENTION,
            canonical_payload(canonical_text(payload.kind.value), *payload.address_fields()),
        )

    @classmethod
    def of(cls, payload: InterventionPayload, *, rationale: str) -> Intervention:
        """Return the addressed change for this payload."""
        return cls(intervention_id=cls.address(payload), payload=payload, rationale=rationale)

    def sort_key(self) -> tuple[str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.payload.kind.value, self.intervention_id)

    @model_validator(mode="after")
    def _check_address(self) -> Intervention:
        """Refuse an identifier that does not address this payload."""
        expected = type(self).address(self.payload)
        if self.intervention_id != expected:
            raise ContractViolationError(
                f"Intervention.intervention_id {self.intervention_id!r} does not address its "
                f"own payload (expected {expected!r}). An address that does not follow from "
                "the content makes two different changes indistinguishable to a rerun."
            )
        return self


class RejectionReason(str, Enum):
    """Why a proposed change was refused before anything was simulated.

    Closed, and every member names a declaration the change was checked against, so a
    rejection tells a reader what would have admitted it rather than only that it failed.
    """

    UNKNOWN_TARGET = "UNKNOWN_TARGET"
    """The change names an occurrence or a participant the base world does not hold."""

    ATTRIBUTE_NOT_DECLARED_CHANGEABLE = "ATTRIBUTE_NOT_DECLARED_CHANGEABLE"
    """The ontology declares no `mutable` on this attribute of this kind of occurrence."""

    VALUE_OUTSIDE_DECLARED_BOUND = "VALUE_OUTSIDE_DECLARED_BOUND"
    """The attribute is changeable and the proposed value is outside its declared bound."""

    TRANSITION_NOT_DECLARED = "TRANSITION_NOT_DECLARED"
    """The entity type's lifecycle declares no transition between the two named states."""

    STEP_NOT_ADMITTED_BY_PROCESS = "STEP_NOT_ADMITTED_BY_PROCESS"
    """No declared process sequence, variant or optional step admits the insertion here."""

    WOULD_VIOLATE_LAW_TIME = "WOULD_VIOLATE_LAW_TIME"
    """The change would place an antecedent at or after its own consequent."""

    CHANGES_NOTHING = "CHANGES_NOTHING"
    """The change sets a value the base world already holds."""

    DECLARATION_ABSENT = "DECLARATION_ABSENT"
    """The pack declares nothing this change could be checked against.

    Distinct from every reason above, and the distinction is the point: those say the change
    was checked and refused, this says it could not be checked at all. Collapsing them would
    let an unconfigured run read as a validated one, which is the `NOT_RUNNABLE` distinction
    every report in this engine keeps.
    """


class RejectedIntervention(BaseModel):
    """One change the engine refused, with what it was checked against.

    Carried at the same standing as the world that WAS simulated (ADR-0054's ledger), so a
    reader can see what was considered and refused rather than only what was accepted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    intervention_id: str
    kind: InterventionKind
    reason: RejectionReason
    #: What the change was checked against, named so the remedy is legible: the declaration
    #: that would have admitted it, or the statement that none exists.
    checked_against: str = Field(min_length=1)
    #: Plain language, naming the identifier and the contract. Never a bare code.
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.reason.value, self.kind.value, self.intervention_id)


def canonical_intervention_payload(interventions: tuple[Intervention, ...]) -> str:
    """Return the canonical text for a whole set of changes.

    The second half of a simulated world's address (`CONVENTIONS.md` §9:
    `sim: base_graph_id | mutations`). Sequenced canonically here rather than trusted from
    the caller, so two callers proposing one set in two sequences address one world.
    """
    return canonical_sequence(
        item.intervention_id for item in sorted(interventions, key=lambda one: one.sort_key())
    )
