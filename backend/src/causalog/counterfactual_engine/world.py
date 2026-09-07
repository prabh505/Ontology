"""What a hypothetical world contains, and how it differs from the one that happened.

**A simulated world holds no `Event` and no `TimeInterval`** (ADR-0068). It holds
`SimulatedEvent` and `core.perturbation.SimulatedInstant`, which are structurally distinct
shapes carrying `SIMULATED`. prd.md §37 requires that observed facts and counterfactual
simulations never be conflated "in the implementation or the user interface", and one type
carrying both is that conflation at the level where it is hardest to see and easiest to
spread. A consumer holding a `SimulatedEvent` cannot mistake it for history, and neither can
a serializer -- which is where the cheaper answer, one type plus a provenance field, fails.

COPY-ON-WRITE IS STRUCTURAL HERE, NOT CAREFUL
----------------------------------------------
Nothing below writes to a base-world artifact, and there are two independent reasons it
cannot. First, `Event` is frozen and this package never calls `core.immutability.revise` on
one -- asserted over the AST by `tests/law/test_simulation_never_writes_back.py`. Second,
`revise` itself raises on an `OBSERVED` artifact (LAW-PROVENANCE), so even a call that
slipped past the first would fail at the second. A `SimulatedEvent` is a NEW value that
names the base occurrence it derives from; it is never a modified copy of one.

THE DIFF IS THE PRODUCT, NOT A CONVENIENCE
-------------------------------------------
prd.md §33 asks the engine to "simulate downstream changes". A world on its own answers
nothing -- the reader needs to see, occurrence by occurrence, what moved, what stopped
happening, what got smaller, and what the change did not touch. `WorldDiff` carries the
UNCHANGED count beside the changes for the reason every report in this engine states what it
does not contain: a list of six deltas with no denominator reads as a large effect whatever
the denominator was.

**No domain vocabulary appears below.** Nothing here reads a type name.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.attribution import difference_of
from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.perturbation import SIMULATION_IS_NOT_A_PREDICTION_NOTICE, SimulatedInstant
from causalog.core.provenance import ProvenanceClass
from causalog.counterfactual_engine.intervention import (
    Intervention,
    canonical_intervention_payload,
)

__all__ = [
    "DeltaKind",
    "EventDelta",
    "SimulatedEvent",
    "SimulatedWorld",
    "WorldDiff",
]


class DeltaKind(str, Enum):
    """One way a hypothetical changed an occurrence. An occurrence may carry several."""

    RETIMED = "RETIMED"
    """The occurrence happens at a different instant."""

    NOT_RETIMED = "NOT_RETIMED"
    """The occurrence is downstream of a move and its instant did NOT move.

    Reported rather than omitted. The engine has no transfer function for time: an instant
    moves under a change only when the run's measurement says the source COMPUTED it from
    the moved one (`core.precedence`). Everything else keeps its instant, and saying so is
    what stops a reader concluding that the timing was checked and found unaffected.
    """

    REMOVED = "REMOVED"
    """The occurrence was named by a removal and does not happen in this world."""

    INSERTED = "INSERTED"
    """The occurrence does not appear in history and was placed by the change."""

    ELIMINATED = "ELIMINATED"
    """Nothing reaches this consequence any more, so the graph says it stops occurring.

    A re-reachability finding and never a subtraction (ADR-0061): a consequence with another
    surviving antecedent stays, which is what makes this correct on a diamond.
    """

    MAGNITUDE_REDUCED = "MAGNITUDE_REDUCED"
    """The consequence still occurs and is smaller, because some of its causes were removed.

    **The case a naive simulator gets backwards.** Removing one of several joint causes does
    not prevent the outcome; the others still hold it up. This kind exists so the difference
    between "smaller" and "prevented" is visible in the artifact rather than in a footnote.
    """

    MAGNITUDE_SCALED = "MAGNITUDE_SCALED"
    """A modifier that scaled this consequence was changed or removed."""

    ATTRIBUTE_CHANGED = "ATTRIBUTE_CHANGED"
    """A declared changeable attribute holds a different value."""

    CONDITION_INVALIDATED = "CONDITION_INVALIDATED"
    """A qualified link into this occurrence stopped transmitting because its condition no
    longer holds under the change."""


class SimulatedEvent(BaseModel):
    """One occurrence as a hypothetical world holds it.

    Not an `Event` and never convertible to one. `base_event_id` is `None` exactly when the
    occurrence was inserted, so "did this happen?" is answerable from the value alone.

    Invariants:
      * `present` is false only for a removed or eliminated occurrence, and such an
        occurrence carries no magnitude -- a value for something that does not occur is a
        number with no referent.
      * an inserted occurrence names no base occurrence, and a derived one always does.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    #: `None` exactly when this occurrence was inserted by the change.
    base_event_id: str | None
    event_type: str
    occurred_at: SimulatedInstant
    #: Sorted by name, as `Event.changed_attributes` is.
    attributes: tuple[tuple[str, str], ...] = ()
    present: bool = True
    #: The magnitude a pack-declared measurement tree yields for this occurrence in THIS
    #: world. `None` is an absence and never a zero -- see `magnitude_absent_because`.
    magnitude: float | None = None
    measurement_id: str | None = None
    unit: str | None = None
    #: Why no magnitude is carried, when none is. Exactly one of this and `magnitude`.
    magnitude_absent_because: str | None = None

    @property
    def provenance_class(self) -> ProvenanceClass:
        """Return `SIMULATED`, always.

        A property rather than a field, for `SimulatedInstant`'s reason: there is no
        admissible second value, and a field could be set to one on a deserialization path.
        """
        return ProvenanceClass.SIMULATED

    @model_validator(mode="after")
    def _check_invariants(self) -> SimulatedEvent:
        """Enforce the documented invariants at construction."""
        if (self.magnitude is None) == (self.magnitude_absent_because is None):
            raise ContractViolationError(
                f"SimulatedEvent {self.event_id} must carry exactly one of a magnitude and a "
                "reason there is none. Carrying neither hides that a value was expected; "
                "carrying both lets a reader take the number and drop the caveat."
            )
        if not self.present and self.magnitude is not None:
            raise ContractViolationError(
                f"SimulatedEvent {self.event_id} does not occur in this world and carries a "
                "magnitude. A value for something that does not happen has no referent."
            )
        if list(self.attributes) != sorted(self.attributes):
            raise ContractViolationError(
                f"SimulatedEvent {self.event_id} carries unsequenced attributes "
                "(CONVENTIONS.md §11); two runs would serialize differently."
            )
        return self

    def sort_key(self) -> tuple[str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.event_type, self.event_id)


class EventDelta(BaseModel):
    """What one hypothetical did to one occurrence, base value beside simulated value.

    Both sides travel. A delta reporting only the new value asks the reader to hold the old
    one in their head, and the whole product here is a comparison.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    event_type: str
    #: Every way this occurrence changed. Sorted, non-empty -- an unchanged occurrence is
    #: counted in `WorldDiff.unchanged_count` and produces no delta.
    kinds: tuple[DeltaKind, ...] = Field(min_length=1)
    present_in_base: bool = True
    present_in_simulated: bool = True
    #: ISO-8601 renderings, so a delta is readable without holding the interval types.
    base_instant: str | None = None
    simulated_instant: str | None = None
    shifted_by_seconds: float | None = None
    base_magnitude: float | None = None
    simulated_magnitude: float | None = None
    measurement_id: str | None = None
    unit: str | None = None
    #: Plain language. Names the identifier and the reason, never a bare code.
    detail: str = Field(min_length=1)

    @property
    def magnitude_difference(self) -> float | None:
        """Return how much of the magnitude the change accounts for, or None.

        `None` rather than zero whenever either side is unmeasured. A difference against an
        unmeasured base is not a difference, and rendering it as zero would say the change
        moved none of something when the truth is that nobody could tell.
        """
        return difference_of(self.base_magnitude, self.simulated_magnitude)

    @model_validator(mode="after")
    def _check_invariants(self) -> EventDelta:
        """Enforce the documented invariants at construction."""
        if list(self.kinds) != sorted(self.kinds, key=lambda kind: kind.value):
            raise ContractViolationError(
                f"EventDelta {self.event_id} carries unsequenced kinds (CONVENTIONS.md §11)."
            )
        if len(set(self.kinds)) != len(self.kinds):
            raise ContractViolationError(
                f"EventDelta {self.event_id} repeats a delta kind; one change reported twice "
                "reads as two changes."
            )
        return self

    def sort_key(self) -> tuple[str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.event_type, self.event_id)


class WorldDiff(BaseModel):
    """The base world against the simulated one, occurrence by occurrence.

    `unchanged_count` travels beside the deltas because a list of changes with no denominator
    reads as a large effect whatever the denominator was. `reached_count` is separate again:
    an occurrence the propagation never reached is a different fact from one it reached and
    found unchanged, and one number cannot tell them apart.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Sequenced canonically, never by size. Sequencing by magnitude would make the artifact
    #: a ranking, and ranking is module 11's work.
    deltas: tuple[EventDelta, ...] = ()
    #: Occurrences the propagation reached and found unchanged.
    unchanged_count: int = Field(default=0, ge=0)
    #: Occurrences the propagation reached at all, changed or not.
    reached_count: int = Field(default=0, ge=0)
    #: Why the diff is empty, when it is. An empty diff with no stated reason reads as "the
    #: change had no effect" and may instead mean nothing was walked.
    empty_because: str | None = None

    @property
    def eliminated_event_ids(self) -> tuple[str, ...]:
        """Return the occurrences the graph says stop happening. Never a magnitude claim."""
        return tuple(
            delta.event_id
            for delta in self.deltas
            if DeltaKind.ELIMINATED in delta.kinds or DeltaKind.REMOVED in delta.kinds
        )

    @property
    def reduced_event_ids(self) -> tuple[str, ...]:
        """Return the consequences that still happen and are smaller.

        Kept apart from `eliminated_event_ids` deliberately. Merging the two would be the
        single most common counterfactual error wearing an accessor's name.
        """
        return tuple(
            delta.event_id
            for delta in self.deltas
            if DeltaKind.MAGNITUDE_REDUCED in delta.kinds and delta.present_in_simulated
        )

    @model_validator(mode="after")
    def _check_invariants(self) -> WorldDiff:
        """Enforce the documented invariants at construction."""
        keys = [delta.sort_key() for delta in self.deltas]
        if keys != sorted(keys):
            raise ContractViolationError(
                "WorldDiff.deltas is unsequenced (CONVENTIONS.md §11); two runs would "
                "serialize differently."
            )
        if len(set(keys)) != len(keys):
            raise ContractViolationError(
                "WorldDiff holds two deltas for one occurrence; a reader cannot tell which "
                "describes the world."
            )
        if self.reached_count < len(self.deltas) + self.unchanged_count:
            raise ContractViolationError(
                f"WorldDiff reached {self.reached_count} occurrence(s) and reports "
                f"{len(self.deltas)} changed plus {self.unchanged_count} unchanged, which is "
                "more than it reached. The totals disagree with themselves, so the diff is "
                "refused rather than published."
            )
        if not self.deltas and self.empty_because is None:
            raise ContractViolationError(
                "WorldDiff is empty and states no reason. An empty diff reads as 'the change "
                "had no effect' and may instead mean nothing was walked; the two are "
                "different findings and the type refuses to let them look alike."
            )
        return self


class SimulatedWorld(BaseModel):
    """One hypothetical: the changes that made it, what it holds, and how it differs.

    `standing` is REQUIRED and has no default, so a world cannot be built without someone
    stating which graph it was simulated over -- the rule ADR-0059 established for modules
    11 and 12, applied here. A world simulated over claims the engine never asserted is
    disowned by this type: `notice` carries the fixed text and the validator refuses
    `INFERRED` on it, so a diagnostic finding cannot be laundered into an assertion by
    editing a field.

    Address: `sim:digest(base_graph_id | interventions)` -- `CONVENTIONS.md` §9's recipe,
    unchanged. Two runs handed one base world and one set of changes address one world.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    simulated_world_id: str
    run_id: str = Field(min_length=1)
    #: Which graph this was simulated over. `GraphStanding` is imported from module 12
    #: rather than redefined: two copies of a closed set in two packages is the divergence
    #: `check_law_copies.py` exists to catch one level up.
    standing: str
    base_graph_id: str = Field(min_length=1)
    #: Sequenced canonically. Non-empty: a world with no change is the base world, and
    #: publishing one under this type would present history as a hypothetical.
    interventions: tuple[Intervention, ...] = Field(min_length=1)
    #: Every occurrence the propagation reached, in this world's terms.
    events: tuple[SimulatedEvent, ...] = ()
    diff: WorldDiff
    #: Fixed text stating what a simulated world is not. Held here as well as on each
    #: instant because a world may be rendered without its occurrences.
    provenance_class: ProvenanceClass = ProvenanceClass.SIMULATED

    @property
    def notice(self) -> str:
        """Return the fixed statement of what this artifact is and is not.

        A property rather than a field so that no revision can soften it and it enters no
        content address (the mechanism ADR-0059 uses for `DIAGNOSTIC_NOT_STATED_NOTICE`).
        """
        return SIMULATION_IS_NOT_A_PREDICTION_NOTICE

    @classmethod
    def address(cls, base_graph_id: str, interventions: tuple[Intervention, ...]) -> str:
        """Return the content address of a hypothetical world (`CONVENTIONS.md` §9)."""
        return digest(
            IdentifierPrefix.SIMULATED_WORLD,
            canonical_payload(
                canonical_text(base_graph_id), canonical_intervention_payload(interventions)
            ),
        )

    @model_validator(mode="after")
    def _check_invariants(self) -> SimulatedWorld:
        """Enforce the documented invariants at construction."""
        if self.provenance_class is not ProvenanceClass.SIMULATED:
            raise ContractViolationError(
                f"SimulatedWorld {self.simulated_world_id} claims "
                f"{self.provenance_class.value}. Everything inside a hypothetical is "
                "SIMULATED (LAW-PROVENANCE); a world that claimed otherwise would be a "
                "simulated figure wearing an inferred claim's standing."
            )
        expected = type(self).address(self.base_graph_id, self.interventions)
        if self.simulated_world_id != expected:
            raise ContractViolationError(
                f"SimulatedWorld.simulated_world_id {self.simulated_world_id!r} does not "
                f"address its own base world and changes (expected {expected!r}). An address "
                "that does not follow from the content makes two worlds indistinguishable."
            )
        keys = [item.sort_key() for item in self.events]
        if keys != sorted(keys):
            raise ContractViolationError(
                "SimulatedWorld.events is unsequenced (CONVENTIONS.md §11)."
            )
        intervention_keys = [item.sort_key() for item in self.interventions]
        if intervention_keys != sorted(intervention_keys):
            raise ContractViolationError(
                "SimulatedWorld.interventions is unsequenced (CONVENTIONS.md §11)."
            )
        return self
