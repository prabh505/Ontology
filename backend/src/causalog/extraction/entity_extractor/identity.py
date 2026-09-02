"""Identity resolution: one participant, one identifier, and every disagreement recorded.

Identity here is **content-addressed and nothing else**. `docs/architecture.md` §2 forbids
this module from merging two entities on a similarity heuristic, and the reason is not
fastidiousness: a fuzzy merge is irreversible, invisible downstream, and produces a graph in
which two participants have silently become one. `Entity.address` is the whole of the
identity decision, and it is a pure function of `(ontology_hash, entity_type, natural_key)`.

What is left to decide is what to do when two records agree about WHO and disagree about
WHAT -- the same key carrying different attribute values. That is a reconciliation policy,
and it is configurable because no single answer is right for every source: a file sorted
oldest-first and a file of corrections want opposite rules.

The policy decides which value the entity CARRIES. It never decides whether the
disagreement is reported. Every conflict reaches the reconciliation report with both values
and both citations under every policy, including the one that silently keeps the first --
because a policy that could suppress a finding would make the report a function of
configuration rather than of the data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.errors import DataQualityError
from causalog.core.temporal import TimeInterval

__all__ = [
    "AttributeConflict",
    "ConflictPolicy",
    "EntityAccumulator",
    "ResolvedIdentity",
]


class ConflictPolicy(str, Enum):
    """What an entity carries when two records disagree about one of its attributes.

    Deliberately three members and no fourth. There is no `MOST_FREQUENT`: a majority vote
    over source rows is a statistical claim wearing a reconciliation rule, and it would put
    a `STATISTICAL` value on an entity whose provenance class is `OBSERVED`.
    """

    FIRST_WINS = "FIRST_WINS"
    """The value from the earliest record in canonical sequence is kept. The default,
    because it makes an entity's attributes a function of the sequence the source declares
    rather than of how far a run happened to get."""

    LAST_WINS = "LAST_WINS"
    """The value from the latest record in canonical sequence is kept. Correct for a source
    whose later rows are corrections; wrong for one whose later rows are merely later."""

    REJECT = "REJECT"
    """A disagreement is a hard error. Correct for a source that claims to be internally
    consistent, where a conflict means the key is not the key."""


class AttributeConflict(BaseModel):
    """One recorded disagreement between two records about one attribute of one entity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: str
    natural_key: str
    attribute: str
    held_value: str
    held_evidence_record_id: str
    held_row_number: int = Field(ge=1)
    offered_value: str
    offered_evidence_record_id: str
    offered_row_number: int = Field(ge=1)
    resolved_value: str
    policy: ConflictPolicy

    def render(self) -> str:
        """Return the one-line form a report prints."""
        return (
            f"{self.entity_type}[{self.natural_key}].{self.attribute}: "
            f"row {self.held_row_number} says {self.held_value!r}, "
            f"row {self.offered_row_number} says {self.offered_value!r}; "
            f"{self.policy.value} keeps {self.resolved_value!r}"
        )


@dataclass
class ResolvedIdentity:
    """The accumulating state of one entity across every record that mentions it."""

    entity_id: str
    entity_type: str
    natural_key: str
    first_row_number: int
    attributes: dict[str, str] = field(default_factory=dict)
    attribute_origin: dict[str, tuple[str, int]] = field(default_factory=dict)
    """attribute -> the (evidence record, row number) whose value is currently held."""
    citations: list[str] = field(default_factory=list)
    """The records that ESTABLISHED or CHANGED this entity, in the sequence they arrived.

    Not every record that mentioned it. A citation to a record that repeated what was
    already known adds no support and would make an entity's evidence list grow with the
    row count rather than with what is known about it -- on the reference dataset that is
    the difference between a bounded artifact and a 1.6-million-string one. The records
    that merely agreed are counted, as `observations`, and the count is in the report.
    """
    observations: int = 0


@dataclass
class EntityAccumulator:
    """Fold records into entities in bounded memory, recording every disagreement.

    Bounded by identity cardinality, not by row count -- the same property, and the same
    caveat, as module 1's `IdentityIndex`: a source whose identity cardinality genuinely
    exceeds memory needs a spilling index, and that is a change to make when it is measured.
    """

    policy: ConflictPolicy = ConflictPolicy.FIRST_WINS
    identities: dict[str, ResolvedIdentity] = field(default_factory=dict)
    conflicts: list[AttributeConflict] = field(default_factory=list)
    conflicted_entities: set[str] = field(default_factory=set)
    keyless: dict[str, int] = field(default_factory=dict)
    """entity type -> records that named no derivable key for it. Not an error: a source
    frequently references a participant it does not describe (`docs/architecture.md` §2)."""

    def observe(
        self,
        entity_id: str,
        entity_type: str,
        natural_key: str,
        attributes: Mapping[str, str],
        evidence_record_id: str,
        row_number: int,
    ) -> tuple[bool, tuple[str, ...]]:
        """Fold one record's statement about one entity in.

        Returns `(created, changed_attributes)` -- whether this record established the
        entity, and which attributes it introduced or altered. The caller uses the second
        to decide which attribute versions to record.

        Raises:
            DataQualityError: under `REJECT`, on the first disagreement.
        """
        held = self.identities.get(entity_id)
        if held is None:
            held = ResolvedIdentity(
                entity_id=entity_id,
                entity_type=entity_type,
                natural_key=natural_key,
                first_row_number=row_number,
                attributes=dict(attributes),
                attribute_origin={name: (evidence_record_id, row_number) for name in attributes},
                citations=[evidence_record_id],
                observations=1,
            )
            self.identities[entity_id] = held
            return True, tuple(sorted(attributes))

        held.observations += 1
        changed: list[str] = []
        for name in sorted(attributes):
            offered = attributes[name]
            if name not in held.attributes:
                held.attributes[name] = offered
                held.attribute_origin[name] = (evidence_record_id, row_number)
                changed.append(name)
                continue
            current = held.attributes[name]
            if current == offered:
                continue
            origin_record, origin_row = held.attribute_origin[name]
            resolved = self._resolve(
                entity_id=entity_id,
                entity_type=entity_type,
                natural_key=natural_key,
                attribute=name,
                held_value=current,
                held_evidence_record_id=origin_record,
                held_row_number=origin_row,
                offered_value=offered,
                offered_evidence_record_id=evidence_record_id,
                offered_row_number=row_number,
            )
            if resolved != current:
                held.attributes[name] = resolved
                held.attribute_origin[name] = (evidence_record_id, row_number)
            changed.append(name)
        if changed and evidence_record_id not in held.citations:
            held.citations.append(evidence_record_id)
        return False, tuple(changed)

    def _resolve(self, **conflict: object) -> str:
        """Record one conflict and return the value the policy keeps.

        Raises:
            DataQualityError: under `REJECT`.
        """
        held_value = str(conflict["held_value"])
        offered_value = str(conflict["offered_value"])
        if self.policy is ConflictPolicy.REJECT:
            raise DataQualityError(
                f"{conflict['entity_type']}[{conflict['natural_key']}]."
                f"{conflict['attribute']} is {held_value!r} at row "
                f"{conflict['held_row_number']} and {offered_value!r} at row "
                f"{conflict['offered_row_number']}. Under ConflictPolicy.REJECT a "
                "disagreement means the identifying key does not identify: two different "
                "participants are sharing one address, and merging them would be "
                "irreversible."
            )
        resolved = held_value if self.policy is ConflictPolicy.FIRST_WINS else offered_value
        self.conflicts.append(
            AttributeConflict(resolved_value=resolved, policy=self.policy, **conflict)  # type: ignore[arg-type]
        )
        self.conflicted_entities.add(str(conflict["entity_id"]))
        return resolved

    def record_keyless(self, entity_type: str) -> None:
        """Count one record that supplied no derivable key for an entity type."""
        self.keyless[entity_type] = self.keyless.get(entity_type, 0) + 1

    def sequenced(self) -> Iterable[ResolvedIdentity]:
        """Yield every accumulated identity, sequenced by `entity_id` (`CONVENTIONS.md` §11)."""
        for entity_id in sorted(self.identities):
            yield self.identities[entity_id]


def interval_or_unknown(interval: TimeInterval | None, unknown: TimeInterval) -> TimeInterval:
    """Return the supplied interval, or the unbounded one when the source dated nothing."""
    return unknown if interval is None else interval
