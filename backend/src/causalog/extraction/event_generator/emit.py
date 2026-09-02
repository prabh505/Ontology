"""Module 4's entry point: mapped records in, `Event` values out. The LAW-EVENT boundary.

ADR-0004 names this the highest-risk module in the system: a row-to-events mapping error is
invisible downstream and corrupts every conclusion. Three properties are therefore
structural here rather than reviewed.

**A heuristic cannot mint an OBSERVED event.** Not "does not"; cannot. An emitted event
takes its `provenance_class` from the pack's `EventTypeSpec`, and the pack refuses `OBSERVED`
on a type declared `DERIVED` (ADR-0029, `ontology_runtime.dsl`). There is no parameter, no
override and no branch by which a condition-tree emission reaches `OBSERVED`. The emission
rule names no provenance class at all, so there is nothing to get wrong.

**One occurrence is one event, however many records witness it.** A source whose records are
sub-items of a larger transaction records that transaction's occurrences once per sub-item.
Emitting one event per record would multiply every downstream count by the average sub-item
count and would look, from the inside, exactly like a busier business. Records witnessing the
same occurrence -- same type, same participants, same interval, same recorded attributes --
corroborate it: they
become one event whose `evidence_record_ids` names all of them and whose `source_record_ref`
names the first in canonical sequence. That is precisely the distinction `Event` was built
for.

**Two passes, because the evidence set is part of the identity.** `event_id` addresses
`evidence_record_ids(sorted)` (`CONVENTIONS.md` §9), which is not known until every record
has been read. Pass A accumulates the citation set per occurrence; pass B materialises each
event once, at its first witnessing record. The alternative -- holding every event's fields
in memory through one pass -- is the same information at many times the size, and module 1
already established that two exact passes beat one approximate one here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from causalog.core.aggregation import aggregate
from causalog.core.identifiers import (
    canonical_pairs,
    canonical_sequence,
    canonical_text,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision, TimeInterval, canonical_interval
from causalog.core.types.confidence import ConfidenceComponent, ConfidenceVector
from causalog.core.types.event import Event
from causalog.extraction.event_generator.conditions import ConditionCounters, evaluate
from causalog.extraction.event_generator.participants import (
    ParticipantPlan,
    Participants,
    ResolvedParticipants,
)
from causalog.extraction.event_generator.temporal import occurred_at, unknown_interval
from causalog.ingestion.schema_mapper.apply import MappedRecordBatch, RecordView, address_of
from causalog.ingestion.schema_mapper.dsl import EventEmissionSpec, SchemaMappingSpec
from causalog.ontology_runtime.dsl import (
    AttributeOrigin,
    EventTypeSpec,
    ObservationMode,
    ResolvedPack,
)

__all__ = [
    "GAP_MARKER_SUPPORT",
    "OBSERVED_RULE_SUPPORT",
    "EmissionOutcome",
    "EventBuilder",
    "MissingEventPolicy",
    "OccurrenceIndex",
]

#: The extraction confidence of an event whose occurrence a column records directly.
#:
#: Engine policy, not domain policy, which is why it is a constant here rather than a pack
#: declaration. `Event.confidence` answers "how sure are we this event was correctly derived
#: from its evidence" (ADR-0009), and for an OBSERVED type the derivation is a declared,
#: exhaustive, non-heuristic column binding. There is no partial credit available: either
#: the source recorded the occurrence, or the pack would not have declared the type
#: OBSERVED. It does not weaken `provenance_class` and it is not the confidence of any
#: causal claim.
OBSERVED_RULE_SUPPORT: Final[float] = 1.0

#: The extraction confidence of a gap marker under `EMIT_GAP_MARKER`.
#:
#: Zero, and deliberately the only value that cannot be mistaken for evidence. A gap marker
#: exists because a process definition expects a step and NO FIELD WITNESSES IT; any
#: positive number would be a claim about support that does not exist. The marker's value is
#: that the shape of the process stays visible, not that the occurrence is likely.
GAP_MARKER_SUPPORT: Final[float] = 0.0

#: The component name both of the above are recorded under. It is in
#: `core.aggregation.DEFAULT_COMPONENT_WEIGHTS`, which is a closed set that is part of
#: `confidence_schema_version`: a new name here would be a schema change, not a label.
_SUPPORT_COMPONENT: Final[str] = "rule_support"

#: Characters of the occurrence digest retained. Internal to this module and NOT an
#: `IdentifierPrefix` value: it addresses a grouping decision, not an artifact, and a reader
#: must never mistake it for an `evt:` identifier.
_OCCURRENCE_DIGEST_LENGTH: Final[int] = 24


class MissingEventPolicy(str, Enum):
    """What happens where a process definition expects a step no field supports (ADR-0040).

    Configurable because it changes what the causal engine can conclude, and stamped into
    the event quality report for the same reason: a consumer reading a run's events must be
    able to tell which policy produced them without asking how it was invoked.
    """

    RECORD_GAP = "RECORD_GAP"
    """Emit nothing; record the gap. The default. A fabricated event is a real node the
    causal engine can attach edges to, and one with no supporting field has UNKNOWN
    precision -- so LAW-TIME returns UNDETERMINED for every pair it touches and it can never
    be promoted. It would add graph mass carrying no verifiable content. The process shape
    is preserved in the coverage report, where it can be read without being reasoned over,
    and module 5 already owns timeline gap markers (risk R-02)."""

    EMIT_GAP_MARKER = "EMIT_GAP_MARKER"
    """Emit the expected event with the unbounded UNKNOWN interval, the pack's declared
    provenance class, and zero rule support. Chosen when a consumer needs a complete
    sequence with explicitly weak links rather than a sequence with holes."""


@dataclass
class EmissionOutcome:
    """Per-rule counts of what happened while a pass walked the records."""

    fired: dict[str, int] = field(default_factory=dict)
    suppressed_missing_participant: dict[str, int] = field(default_factory=dict)
    orphaned: dict[str, int] = field(default_factory=dict)

    def count(self, table: dict[str, int], event_type: str) -> None:
        """Increment one counter."""
        table[event_type] = table.get(event_type, 0) + 1


@dataclass
class OccurrenceIndex:
    """Pass-A accumulator: which occurrences exist, and which records witness each.

    Bounded by the number of distinct OCCURRENCES and their citations, never by the record
    count times the rule count. The distinction matters on a source of sub-items: one
    occurrence witnessed by every sub-item of its transaction is a single entry here with
    several citations, not several entries.
    """

    citations: dict[str, list[str]] = field(default_factory=dict)
    first_witness: dict[str, tuple[int, str]] = field(default_factory=dict)

    def witness(self, key: str, evidence_record_id: str, row_number: int) -> None:
        """Record that one record witnesses one occurrence."""
        entries = self.citations.setdefault(key, [])
        if evidence_record_id not in entries:
            entries.append(evidence_record_id)
        current = self.first_witness.get(key)
        candidate = (row_number, evidence_record_id)
        if current is None or candidate < current:
            self.first_witness[key] = candidate

    def is_first_witness(self, key: str, evidence_record_id: str, row_number: int) -> bool:
        """Return whether this record is the one that materialises the occurrence."""
        return self.first_witness.get(key) == (row_number, evidence_record_id)

    def evidence_for(self, key: str) -> tuple[str, ...]:
        """Return every citation for one occurrence, sequenced."""
        return tuple(sorted(set(self.citations.get(key, ()))))

    @property
    def occurrence_count(self) -> int:
        """Return the number of distinct occurrences seen."""
        return len(self.citations)


def occurrence_key(
    event_type: str,
    entity_ids: tuple[str, ...],
    interval: TimeInterval,
    changed_attributes: tuple[tuple[str, str], ...],
) -> str:
    """Return the grouping address of one occurrence.

    Everything the event's content address uses EXCEPT its citations. Two records producing
    this key produced the same occurrence and are corroborating witnesses; two records
    producing different keys produced different occurrences, however similar they look.

    Deliberately not built with `core.identifiers.digest`: that function stamps an
    `IdentifierPrefix`, and this addresses a grouping decision rather than an artifact. A
    value that looked like an `evt:` identifier and was not one would be read as one.
    """
    payload = "|".join(
        (
            canonical_text(event_type),
            canonical_sequence(sorted(entity_ids)),
            canonical_interval(interval),
            canonical_pairs(changed_attributes),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_OCCURRENCE_DIGEST_LENGTH]


class EventBuilder:
    """Turn one emission rule plus one record into one `Event`, or into nothing.

    Holds no state about the run. Every judgement it makes is read from the pack: the
    provenance class, the actionability flag, the confidence components, the participants,
    and which attributes the event records. The only numbers this file supplies are the two
    extraction-confidence constants above, and both are engine policy with their reasoning
    written beside them.
    """

    def __init__(
        self,
        pack: ResolvedPack,
        mapping: SchemaMappingSpec,
        ontology_hash: str,
    ) -> None:
        """Compile the pack and the mapping into the lookups the per-record path needs."""
        self._ontology_hash = ontology_hash
        self._types: dict[str, EventTypeSpec] = {item.id: item for item in pack.event_types}
        self._emissions: tuple[EventEmissionSpec, ...] = tuple(
            sorted(
                (item for item in mapping.event_emissions if item.event_type in self._types),
                key=lambda item: item.event_type,
            )
        )
        self._participants = Participants(
            ontology_hash=ontology_hash,
            plans={item.id: ParticipantPlan.build(item) for item in pack.event_types},
        )
        self._recorded_attributes: dict[str, tuple[str, ...]] = {
            item.id: tuple(
                sorted(
                    attribute.name
                    for attribute in item.required_attributes
                    if attribute.origin is AttributeOrigin.SOURCE_COLUMN
                )
            )
            for item in pack.event_types
        }

    @property
    def emissions(self) -> tuple[EventEmissionSpec, ...]:
        """Return the emission rules this builder will evaluate, canonically sequenced."""
        return self._emissions

    def event_types(self) -> tuple[str, ...]:
        """Return every event type the pack declares, sequenced."""
        return tuple(sorted(self._types))

    def witnessed(
        self,
        record: RecordView,
        emission: EventEmissionSpec,
        known: frozenset[str],
        counters: ConditionCounters,
        outcome: EmissionOutcome,
    ) -> tuple[str, ResolvedParticipants, TimeInterval, tuple[tuple[str, str], ...]] | None:
        """Return the occurrence this record witnesses under one rule, or `None`.

        `None` means one of three things, and all three are counted rather than raised: the
        condition did not hold, a required participant was absent, or the record named no
        participant at all. The counts reach the quality report, because a rule that never
        fires and a rule that cannot fire are indistinguishable without them.
        """
        event_type = emission.event_type
        if not evaluate(emission.when, record, event_type=event_type, counters=counters):
            return None
        resolved = self._participants.resolve(record, event_type, known)
        if resolved.missing_required:
            outcome.count(outcome.suppressed_missing_participant, event_type)
            return None
        if resolved.is_orphan:
            outcome.count(outcome.orphaned, event_type)
        interval = occurred_at(emission.occurred_at, record, event_type)
        changed = self._changed_attributes(record, event_type)
        key = occurrence_key(event_type, resolved.entity_ids, interval, changed)
        outcome.count(outcome.fired, event_type)
        return key, resolved, interval, changed

    def build(
        self,
        record: RecordView,
        emission: EventEmissionSpec,
        resolved: ResolvedParticipants,
        interval: TimeInterval,
        changed: tuple[tuple[str, str], ...],
        evidence_record_ids: tuple[str, ...],
    ) -> Event:
        """Materialise one event from its occurrence and its full citation set."""
        spec = self._types[emission.event_type]
        citations = tuple(sorted(set(evidence_record_ids) | {record.evidence_record_id}))
        return Event(
            event_id=Event.address(
                ontology_hash=self._ontology_hash,
                event_type=spec.id,
                entity_ids=resolved.entity_ids,
                occurred_at=interval,
                changed_attributes=changed,
                evidence_record_ids=citations,
            ),
            event_type=spec.id,
            occurred_at=interval,
            trigger=self._trigger(record, emission),
            source_entity_ids=resolved.source_entity_ids,
            target_entity_ids=resolved.target_entity_ids,
            changed_attributes=changed,
            metadata=self._metadata(emission, spec, gap_marker=False),
            provenance_class=spec.provenance_class,
            confidence=self.confidence(spec, citations),
            is_actionable=spec.actionability.actionable,
            source_record_ref=min(citations),
            evidence_record_ids=citations,
        )

    def build_gap_marker(
        self,
        event_type: str,
        anchor_entity_id: str,
        evidence_record_id: str,
        process_id: str,
    ) -> Event:
        """Materialise the explicit gap marker `EMIT_GAP_MARKER` calls for.

        The unbounded UNKNOWN interval, the pack's declared provenance class, and zero rule
        support. Nothing about it is a claim that the occurrence happened; it is a claim
        that the process definition expects it and the dataset does not witness it.
        """
        spec = self._types[event_type]
        interval = unknown_interval(
            f"process[{process_id}] expects {event_type} and no field in this dataset "
            "witnesses it; the occurrence is unplaced and unclaimed (ADR-0040)"
        )
        citations = (evidence_record_id,)
        component = ConfidenceComponent(
            component_name=_SUPPORT_COMPONENT,
            value=GAP_MARKER_SUPPORT,
            provenance_class=ProvenanceClass.ASSUMED,
            evidence_record_ids=citations,
        )
        return Event(
            event_id=Event.address(
                ontology_hash=self._ontology_hash,
                event_type=event_type,
                entity_ids=(anchor_entity_id,),
                occurred_at=interval,
                changed_attributes=(),
                evidence_record_ids=citations,
            ),
            event_type=event_type,
            occurred_at=interval,
            trigger=None,
            source_entity_ids=(anchor_entity_id,),
            target_entity_ids=(),
            changed_attributes=(),
            metadata=self._metadata(None, spec, gap_marker=True, process_id=process_id),
            provenance_class=spec.provenance_class,
            confidence=aggregate((component,), "weighted_mean_v1"),
            is_actionable=spec.actionability.actionable,
            source_record_ref=evidence_record_id,
            evidence_record_ids=citations,
        )

    def confidence(self, spec: EventTypeSpec, citations: tuple[str, ...]) -> ConfidenceVector:
        """Materialise this event type's declared confidence against real evidence.

        For a DERIVED type every component name, value, aggregator and provenance class
        comes from the pack. The pack's own component type carries no evidence records --
        a pack has none; they are minted when a record is read -- which is exactly the gap
        this function closes.

        For an OBSERVED type there is nothing in the pack to read, because an OBSERVED type
        declares no derivation. It gets the single engine-level component documented at the
        top of this file.
        """
        if spec.observation is ObservationMode.OBSERVED or spec.derivation is None:
            return aggregate(
                (
                    ConfidenceComponent(
                        component_name=_SUPPORT_COMPONENT,
                        value=OBSERVED_RULE_SUPPORT,
                        provenance_class=ProvenanceClass.OBSERVED,
                        evidence_record_ids=citations,
                    ),
                ),
                "weighted_mean_v1",
            )
        declared = spec.derivation.default_confidence
        return aggregate(
            tuple(
                ConfidenceComponent(
                    component_name=component.component_name,
                    value=component.value,
                    provenance_class=declared.provenance_class,
                    evidence_record_ids=citations,
                )
                for component in declared.components
            ),
            declared.aggregation,
        )

    def _changed_attributes(
        self, record: RecordView, event_type: str
    ) -> tuple[tuple[str, str], ...]:
        """Return the attributes this event records, read from the mapped record.

        Only the event type's own `required_attributes` with origin `SOURCE_COLUMN`. An
        attribute the pack declares as `DERIVED` or `ASSUMED` has no mapped value by
        definition, and manufacturing one here would put a number on an event that no column
        stands behind.
        """
        found: list[tuple[str, str]] = []
        for name in self._recorded_attributes[event_type]:
            value = record.value(address_of(event_type, name))
            if value is not None:
                found.append((name, value))
        return tuple(sorted(found))

    def _trigger(self, record: RecordView, emission: EventEmissionSpec) -> str | None:
        """Return the proximate mechanism the rule declares, if it declares one (ADR-0020)."""
        if emission.trigger_attribute is None:
            return None
        return record.value(address_of(emission.event_type, emission.trigger_attribute))

    def _metadata(
        self,
        emission: EventEmissionSpec | None,
        spec: EventTypeSpec,
        *,
        gap_marker: bool,
        process_id: str | None = None,
    ) -> tuple[tuple[str, str], ...]:
        """Return the traceability pairs carried on the event, sequenced.

        Small on purpose, and excluded from the content address by `Event.address`, so
        adding a pair here never re-identifies an event. It answers "how did this get made"
        for a reader holding one event and nothing else.
        """
        pairs = [("observation_mode", spec.observation.value)]
        if gap_marker:
            pairs.append(("emission", "GAP_MARKER"))
            if process_id is not None:
                pairs.append(("process", process_id))
        elif emission is not None:
            pairs.append(("emission", "RULE"))
            pairs.append(("occurred_at_policy", emission.occurred_at.policy.value))
        return tuple(sorted(pairs))


def canonical_events(events: Iterable[Event]) -> tuple[Event, ...]:
    """Return events in the canonical sequence `(t_earliest, t_latest, event_id)`.

    `CONVENTIONS.md` §11. **This is a rendering sequence, not a precedence claim**: two
    events that sort adjacently may be temporally incomparable, and reading a sort position
    as a precedence is the exact tie-break `core.temporal` refuses to make.
    """
    return tuple(sorted(events, key=lambda event: (*event.occurred_at.sort_key(), event.event_id)))


def precision_of(event: Event) -> Precision:
    """Return one event's timestamp precision, for the quality report's distribution."""
    return event.occurred_at.precision


BatchSource = Callable[[], Iterable[MappedRecordBatch]]
"""A re-iterable source of mapped records.

A callable rather than an iterable because generation makes two passes and a generator
cannot be walked twice. Taking a factory makes the second pass a caller-visible requirement
rather than a silent one that fails on the second call with an empty result.
"""
