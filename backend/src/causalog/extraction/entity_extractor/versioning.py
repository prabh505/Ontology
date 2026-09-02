"""Attribute history: what was recorded about an entity, when, and on whose authority.

Why history is not on `Entity`
------------------------------
`Entity` is frozen and its content address deliberately excludes `attributes`
(`docs/contracts.md` §5): the identity of a participant is what it IS, not what has been
recorded about it, so enriching an entity must not rename it. That decision has a
consequence this module has to answer for -- an entity cannot carry its own history,
because a second version would either mutate a frozen artifact or mint a second identifier
for one participant. `core.immutability.revise` refuses an `OBSERVED` artifact for exactly
that reason.

So history is a **separate artifact keyed by `entity_id`**. It is the record of what
changed and when it was observed to change; the entity carries the value the reconciliation
policy resolved to. The two never disagree, because the entity's value is the last version
the policy accepted.

What `observed_at` means, and what it does not
----------------------------------------------
It is the instant the SOURCE dates its statement to, read from the address the mapping's
identity binding declares. It is not the instant the value changed -- no source in this
project records that -- and the distinction matters: two versions with `UNKNOWN` intervals
are sequenced by record, not by time, and nothing here pretends otherwise. A consumer that
wants "the value as of T" must check the precision before believing the answer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.temporal import TimeInterval

__all__ = ["EntityAttributeVersion", "EntityHistory", "HistoryAccumulator"]


class EntityAttributeVersion(BaseModel):
    """One recorded value of one attribute of one entity, with its citation.

    A version exists only where the value CHANGED. A record that repeated the value already
    held introduced nothing and produces no version -- a history in which every row is an
    entry is a copy of the source, not a history of the entity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    attribute: str = Field(min_length=1)
    value: str
    observed_at: TimeInterval
    evidence_record_id: str
    row_number: int = Field(ge=1)
    superseded: bool = False
    """True once a later version of the same attribute exists. Recorded rather than derived
    at read time so a consumer holding one version alone can tell whether it is current."""

    def sort_key(self) -> tuple[str, tuple[object, object], int]:
        """Return the canonical sequence key: attribute, then interval, then record."""
        return (self.attribute, self.observed_at.sort_key(), self.row_number)


class EntityHistory(BaseModel):
    """Every recorded version of every attribute of one entity, canonically sequenced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: str
    natural_key: str
    versions: tuple[EntityAttributeVersion, ...] = ()

    @property
    def changed_attributes(self) -> tuple[str, ...]:
        """Return the attributes that took more than one value, sequenced."""
        counts: dict[str, int] = {}
        for version in self.versions:
            counts[version.attribute] = counts.get(version.attribute, 0) + 1
        return tuple(sorted(name for name, count in counts.items() if count > 1))

    def versions_of(self, attribute: str) -> tuple[EntityAttributeVersion, ...]:
        """Return every version of one attribute, in sequence."""
        return tuple(item for item in self.versions if item.attribute == attribute)


@dataclass
class HistoryAccumulator:
    """Collect attribute versions as records arrive, in bounded-per-entity memory."""

    versions: dict[str, list[EntityAttributeVersion]] = field(default_factory=dict)
    _latest: dict[tuple[str, str], int] = field(default_factory=dict)

    def record(
        self,
        entity_id: str,
        attribute: str,
        value: str,
        observed_at: TimeInterval,
        evidence_record_id: str,
        row_number: int,
    ) -> None:
        """Add one version, marking any earlier version of the same attribute superseded."""
        entries = self.versions.setdefault(entity_id, [])
        previous = self._latest.get((entity_id, attribute))
        if previous is not None:
            earlier = entries[previous]
            entries[previous] = earlier.model_copy(update={"superseded": True})
        self._latest[(entity_id, attribute)] = len(entries)
        entries.append(
            EntityAttributeVersion(
                entity_id=entity_id,
                attribute=attribute,
                value=value,
                observed_at=observed_at,
                evidence_record_id=evidence_record_id,
                row_number=row_number,
            )
        )

    def history_for(self, entity_id: str, entity_type: str, natural_key: str) -> EntityHistory:
        """Return one entity's history, canonically sequenced."""
        entries = sorted(self.versions.get(entity_id, ()), key=lambda item: item.sort_key())
        return EntityHistory(
            entity_id=entity_id,
            entity_type=entity_type,
            natural_key=natural_key,
            versions=tuple(entries),
        )

    def version_count(self) -> int:
        """Return the total number of recorded versions."""
        return sum(len(entries) for entries in self.versions.values())

    def entities_with_changes(self) -> Iterable[str]:
        """Yield the identifiers of entities whose attributes changed at least once."""
        for entity_id in sorted(self.versions):
            counts: dict[str, int] = {}
            for version in self.versions[entity_id]:
                counts[version.attribute] = counts.get(version.attribute, 0) + 1
            if any(count > 1 for count in counts.values()):
                yield entity_id
