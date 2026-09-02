"""Module 3's entry point: mapped records in, `Entity` values and their history out.

Driven entirely by data. The pack declares which entity types exist, what attributes they
have and what lifecycle they move through; the mapping declares which columns compose each
identifying key and which instant dates a statement about each type. Nothing in this file
names an entity type, an attribute, or a column, and `entity_type` is carried as an opaque
string that nothing here branches on (LAW-DOMAIN, ADR-0002).

Three refusals, each of which is a decision this module could have made silently
-----------------------------------------------------------------------------------
**A record with no derivable key yields no entity.** It is counted, per entity type, and
reported. It is not an error: a source frequently references a participant it does not
describe (`docs/architecture.md` §2). Minting an entity from a partial key would produce
one participant per hole.

**Identity is the content address and nothing else.** No similarity, no fuzzy match, no
normalisation beyond the transforms the mapping declared. Two keys that differ are two
participants, and merging them would be irreversible and invisible.

**An attribute the pack does not declare is not carried.** The mapping's coverage check
already refuses a binding to an undeclared concept; this is the second gate, and it exists
because an attribute that reached an entity without a declaration would be a value no
consumer could interpret and no ontology swap could move.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TimeInterval,
)
from causalog.core.types.entity import Entity, Lifecycle
from causalog.extraction.entity_extractor.identity import (
    AttributeConflict,
    ConflictPolicy,
    EntityAccumulator,
)
from causalog.extraction.entity_extractor.report import (
    EntityTypeReconciliation,
    ReconciliationReport,
)
from causalog.extraction.entity_extractor.versioning import EntityHistory, HistoryAccumulator
from causalog.ingestion.schema_mapper.apply import MappedRecordBatch, RecordView, address_of
from causalog.ingestion.schema_mapper.dsl import SchemaMappingSpec
from causalog.ontology_runtime.dsl import EntityTypeSpec, ResolvedPack

__all__ = [
    "CONFLICT_EXAMPLE_LIMIT",
    "EntityExtractor",
    "ExtractionResult",
    "undated",
]

#: Conflict examples kept **per `(entity_type, attribute)`**, not per run.
#:
#: The count is exact and uncapped; only the examples are capped, so a pathological source
#: cannot produce a report larger than the dataset it describes. The cap is per KIND for a
#: reason found by measurement: a flat cap of 100 over the reference dataset filled the list
#: with one entity type's 46,575 conflicts and showed none of another type's 15,590, so the
#: report was complete in its arithmetic and unrepresentative in the one part a reader
#: actually looks at. Per kind, every distinct disagreement appears at least once.
#:
#: The report prints the cap beside the exact total, because a silently truncated list reads
#: as a complete one (`CONVENTIONS.md` §11 on no silent caps).
CONFLICT_EXAMPLE_LIMIT = 10


def undated(reason: str) -> TimeInterval:
    """Return the unbounded interval used when a source dates a statement not at all.

    `ASSUMED` provenance and the unbounded sentinels, which is the one representation that
    claims nothing (`CONVENTIONS.md` §10). `reason` reaches `TimeInterval.source`, so a
    consumer holding the interval alone can tell WHY it is unbounded without inferring it
    from the bounds.
    """
    return TimeInterval(
        t_earliest=UNKNOWN_EARLIEST,
        t_latest=UNKNOWN_LATEST,
        precision=Precision.UNKNOWN,
        provenance=ProvenanceClass.ASSUMED,
        source=reason,
    )


@dataclass(frozen=True)
class ExtractionResult:
    """What one extraction produced: the entities, their history, and the report."""

    entities: tuple[Entity, ...]
    histories: tuple[EntityHistory, ...]
    report: ReconciliationReport

    def entity_ids(self) -> frozenset[str]:
        """Return every minted identifier, for a consumer resolving participants."""
        return frozenset(entity.entity_id for entity in self.entities)

    def by_id(self, entity_id: str) -> Entity | None:
        """Return one entity by identifier, or `None`."""
        for entity in self.entities:
            if entity.entity_id == entity_id:
                return entity
        return None


class EntityExtractor:
    """Fold mapped records into entities under one pack, one mapping, and one policy."""

    def __init__(
        self,
        pack: ResolvedPack,
        mapping: SchemaMappingSpec,
        ontology_hash: str,
        *,
        policy: ConflictPolicy = ConflictPolicy.FIRST_WINS,
    ) -> None:
        """Compile the pack and mapping into the lookups the per-record path needs."""
        self._ontology_hash = ontology_hash
        self._policy = policy
        self._types: dict[str, EntityTypeSpec] = {item.id: item for item in pack.entity_types}
        self._lifecycles: dict[str, Lifecycle] = {
            item.id: _lifecycle_of(item) for item in pack.entity_types
        }
        self._attributes: dict[str, tuple[str, ...]] = {
            item.id: tuple(sorted(attribute.name for attribute in item.attributes))
            for item in pack.entity_types
        }
        self._observed_at: dict[str, str | None] = {
            binding.entity_type: (
                None if binding.observed_at is None else binding.observed_at.address
            )
            for binding in mapping.identity_bindings
        }
        # Only the entity types the MAPPING gives a key to can ever be extracted. A type the
        # pack declares and the mapping does not key is reported by coverage, not silently
        # skipped here.
        self._keyed: tuple[str, ...] = tuple(
            sorted(
                binding.entity_type
                for binding in mapping.identity_bindings
                if binding.entity_type in self._types
            )
        )

    def extract(
        self, batches: Iterable[MappedRecordBatch], envelope: OutputEnvelope
    ) -> ExtractionResult:
        """Fold every record of every batch, then materialise entities, history and report."""
        accumulator = EntityAccumulator(policy=self._policy)
        history = HistoryAccumulator()
        records_read = 0
        observed: dict[str, int] = dict.fromkeys(self._keyed, 0)
        for batch in batches:
            for record in batch.records:
                records_read += 1
                self._observe(RecordView.of(record), accumulator, history, observed)
        return self._materialise(accumulator, history, records_read, observed, envelope)

    def _observe(
        self,
        record: RecordView,
        accumulator: EntityAccumulator,
        history: HistoryAccumulator,
        observed: dict[str, int],
    ) -> None:
        """Fold one mapped record into every entity type it names a key for."""
        for entity_type in self._keyed:
            natural_key = record.natural_key(entity_type)
            if natural_key is None:
                accumulator.record_keyless(entity_type)
                continue
            observed[entity_type] += 1
            entity_id = Entity.address(self._ontology_hash, entity_type, natural_key)
            attributes = {
                name: value
                for name in self._attributes[entity_type]
                for value in [record.value(address_of(entity_type, name))]
                if value is not None
            }
            _created, changed = accumulator.observe(
                entity_id=entity_id,
                entity_type=entity_type,
                natural_key=natural_key,
                attributes=attributes,
                evidence_record_id=record.evidence_record_id,
                row_number=record.row_number,
            )
            if not changed:
                continue
            when = self._dated(record, entity_type)
            held = accumulator.identities[entity_id].attributes
            for name in changed:
                history.record(
                    entity_id=entity_id,
                    attribute=name,
                    value=held[name],
                    observed_at=when,
                    evidence_record_id=record.evidence_record_id,
                    row_number=record.row_number,
                )

    def _dated(self, record: RecordView, entity_type: str) -> TimeInterval:
        """Return the instant this record dates its statement about `entity_type` to."""
        address = self._observed_at.get(entity_type)
        if address is None:
            return undated(
                f"mapping.identity_bindings[{entity_type}] declares no observed_at; the "
                "source dates its statements about this entity type not at all"
            )
        found = record.interval(address)
        if found is None:
            return undated(
                f"mapping.identity_bindings[{entity_type}].observed_at = {address}, which "
                "this record does not supply"
            )
        return found

    def _materialise(
        self,
        accumulator: EntityAccumulator,
        history: HistoryAccumulator,
        records_read: int,
        observed: dict[str, int],
        envelope: OutputEnvelope,
    ) -> ExtractionResult:
        """Build the frozen artifacts from the accumulated state."""
        entities: list[Entity] = []
        histories: list[EntityHistory] = []
        created: dict[str, int] = dict.fromkeys(self._keyed, 0)
        versions: dict[str, int] = dict.fromkeys(self._keyed, 0)
        changing: dict[str, int] = dict.fromkeys(self._keyed, 0)
        conflicted: dict[str, int] = dict.fromkeys(self._keyed, 0)
        conflicts: dict[str, int] = dict.fromkeys(self._keyed, 0)

        for identity in accumulator.sequenced():
            created[identity.entity_type] += 1
            entities.append(
                Entity(
                    entity_id=identity.entity_id,
                    entity_type=identity.entity_type,
                    natural_key=identity.natural_key,
                    attributes=tuple(sorted(identity.attributes.items())),
                    lifecycle=self._lifecycles[identity.entity_type],
                    provenance_class=ProvenanceClass.OBSERVED,
                    evidence_record_ids=tuple(sorted(set(identity.citations))),
                )
            )
            record = history.history_for(
                identity.entity_id, identity.entity_type, identity.natural_key
            )
            versions[identity.entity_type] += len(record.versions)
            if record.changed_attributes:
                changing[identity.entity_type] += 1
            if record.versions:
                histories.append(record)
        for entity_id in accumulator.conflicted_entities:
            conflicted[accumulator.identities[entity_id].entity_type] += 1
        for conflict in accumulator.conflicts:
            conflicts[conflict.entity_type] += 1

        report = ReconciliationReport(
            envelope=envelope,
            conflict_policy=self._policy,
            records_read=records_read,
            per_entity_type=tuple(
                EntityTypeReconciliation(
                    entity_type=entity_type,
                    entities_created=created[entity_type],
                    records_observed=observed.get(entity_type, 0),
                    entities_conflicted=conflicted[entity_type],
                    conflicts=conflicts[entity_type],
                    records_without_key=accumulator.keyless.get(entity_type, 0),
                    attribute_versions=versions[entity_type],
                    entities_with_changed_attributes=changing[entity_type],
                )
                for entity_type in self._keyed
            ),
            conflicts=_representative(accumulator.conflicts),
            conflict_examples_capped_at=CONFLICT_EXAMPLE_LIMIT,
            conflicts_total=len(accumulator.conflicts),
            not_checked=_not_checked(accumulator.conflicts),
        )
        return ExtractionResult(
            entities=tuple(entities),
            histories=tuple(histories),
            report=report,
        )


def _representative(conflicts: list[AttributeConflict]) -> tuple[AttributeConflict, ...]:
    """Return up to `CONFLICT_EXAMPLE_LIMIT` examples of EACH kind of disagreement.

    Kind is `(entity_type, attribute)`. Sequenced by kind and then by the sequence the
    conflicts arrived in, so the list is deterministic and a reader sees every distinct
    disagreement rather than many instances of whichever one happened to be first.
    """
    per_kind: dict[tuple[str, str], list[AttributeConflict]] = {}
    for conflict in conflicts:
        kept = per_kind.setdefault((conflict.entity_type, conflict.attribute), [])
        if len(kept) < CONFLICT_EXAMPLE_LIMIT:
            kept.append(conflict)
    return tuple(item for key in sorted(per_kind) for item in per_kind[key])


def _lifecycle_of(spec: EntityTypeSpec) -> Lifecycle:
    """Build the canonical `Lifecycle` from a pack's declaration.

    An entity type the pack gives no lifecycle still gets one, holding a single declared
    state and no transitions: `Lifecycle` refuses an empty `state_names` because a type with
    no declared states has nothing to check an observation against, and a lifecycle that
    admits everything would be indistinguishable from one nobody wrote. The single state is
    named for the type itself, so what it means is legible at the point of use.
    """
    if spec.lifecycle is None:
        return Lifecycle(
            state_names=(spec.id,),
            legal_transitions=(),
            provenance_class=ProvenanceClass.ASSUMED,
        )
    return Lifecycle(
        state_names=tuple(sorted(set(spec.lifecycle.states))),
        legal_transitions=tuple(
            sorted(
                {
                    (transition.from_state, transition.to_state)
                    for transition in spec.lifecycle.transitions
                }
            )
        ),
        provenance_class=ProvenanceClass.ASSUMED,
    )


def _not_checked(conflicts: list[AttributeConflict]) -> tuple[str, ...]:
    """Assemble the explicit list of checks this module did not perform."""
    items = [
        "**Whether two different participants share an identifying key.** Identity is the "
        "content address of the key the mapping declares. If that key is not unique in the "
        "world, two participants become one entity here, and nothing downstream can see it. "
        "An attribute disagreement is the only symptom this module can report, and a source "
        "that agrees about the wrong thing produces no symptom at all.",
        "**Whether an attribute value is TRUE.** Extraction records what the mapped record "
        "said, not whether the source was right about the world.",
        "**Whether the mapping bound the RIGHT concept.** That a column reaches the concept "
        "it should is risk R-16 and is checked nowhere in this repository.",
        "**Persistence of attribute history.** `entity_attribute` is keyed "
        "`(entity_id, attribute_name)` and holds ONE value per attribute, so the versions "
        "counted here cannot currently be stored. They are an in-memory artifact of this "
        "run; see the open question in `CONTEXT.md` §8.",
    ]
    if conflicts:
        items.append(
            "**Which side of a conflict is correct.** The policy chose a value by record "
            "sequence. Nothing here established that the value it kept is the right one, "
            "and no ground truth exists to establish it against."
        )
    return tuple(items)
