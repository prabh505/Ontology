"""The two-pass generation run, and the artifacts it produces.

Pass A reads every record and answers one question per occurrence: which records witness it.
Pass B reads every record again and materialises each occurrence exactly once, at its first
witness, with the full citation set pass A assembled. `event_id` addresses
`evidence_record_ids(sorted)` (`CONVENTIONS.md` §9), so the identity of an event is not
knowable until every witness has been seen -- which is what makes the second pass a
requirement rather than a preference.

Both passes stream. Peak memory is a function of the number of distinct OCCURRENCES and
their citations, never of the record count times the rule count.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from causalog.core.errors import ContractViolationError
from causalog.core.run import OutputEnvelope
from causalog.core.temporal import Precision
from causalog.core.types.event import Event
from causalog.extraction.event_generator.conditions import ConditionCounters
from causalog.extraction.event_generator.coverage import (
    ProcessCoverage,
    ProcessCoverageAccumulator,
)
from causalog.extraction.event_generator.emit import (
    BatchSource,
    EmissionOutcome,
    EventBuilder,
    MissingEventPolicy,
    OccurrenceIndex,
    canonical_events,
)
from causalog.extraction.event_generator.quality import (
    EventQualityReport,
    EventTypeTally,
)
from causalog.ingestion.schema_mapper.apply import RecordView
from causalog.ingestion.schema_mapper.dsl import SchemaMappingSpec
from causalog.ontology_runtime.dsl import ResolvedPack

__all__ = ["EventGenerator", "GenerationResult", "StreamedGeneration"]


@dataclass
class _Tally:
    """Running counts over a stream of events, so a report never needs the events.

    Every figure the quality report states is a fold, and folding as the events go past is
    what lets a large expansion produce an honest account of itself. Holding the log to
    count it would make the account affordable only for runs small enough not to need one.
    """

    total: int = 0
    gap_markers: int = 0
    orphans: int = 0
    unplaced: int = 0
    complete: bool = False
    by_type: dict[str, int] = field(default_factory=dict)
    by_provenance: dict[str, int] = field(default_factory=dict)
    by_precision: dict[str, int] = field(default_factory=dict)
    by_kind: dict[str, int] = field(default_factory=dict)

    def observe(self, event: Event) -> None:
        """Fold one event in."""
        self.total += 1
        _bump(self.by_type, event.event_type)
        _bump(self.by_provenance, event.provenance_class.value)
        _bump(self.by_precision, event.occurred_at.precision.value)
        _bump(self.by_kind, event.occurred_at.kind.value)
        if event.occurred_at.precision is Precision.UNKNOWN:
            self.unplaced += 1
        if not event.source_entity_ids and not event.target_entity_ids:
            self.orphans += 1


def _bump(table: dict[str, int], key: str) -> None:
    """Increment one counter."""
    table[key] = table.get(key, 0) + 1


@dataclass(frozen=True)
class StreamedGeneration:
    """A stream of events and the report that describes it once the stream is exhausted.

    The report is a callable rather than a field because it cannot be produced until every
    event has passed: a report offered mid-stream would carry partial counts, and a partial
    count is indistinguishable from a complete one once it is written down.
    """

    events: Iterator[Event]
    report: Callable[[], EventQualityReport]


@dataclass(frozen=True)
class GenerationResult:
    """What one generation run produced: the events and the report that bounds them."""

    events: tuple[Event, ...]
    report: EventQualityReport

    def of_type(self, event_type: str) -> tuple[Event, ...]:
        """Return every event of one type, in canonical sequence."""
        return tuple(event for event in self.events if event.event_type == event_type)


class EventGenerator:
    """Emit `Event` values from mapped records under one pack, mapping and policy."""

    def __init__(
        self,
        pack: ResolvedPack,
        mapping: SchemaMappingSpec,
        ontology_hash: str,
        *,
        missing_event_policy: MissingEventPolicy = MissingEventPolicy.RECORD_GAP,
    ) -> None:
        """Compile the pack and mapping into the per-record lookups."""
        self._pack = pack
        self._builder = EventBuilder(pack, mapping, ontology_hash)
        self._policy = missing_event_policy
        self._processes = tuple(pack.process_definitions)
        # Which entity types each event type's participants name. Process coverage reads it
        # to decide whether a step can be attributed to an instance at all -- a step whose
        # event type names no participant of the anchor's type is UNMEASURED, and reporting
        # it as missing would be a quantified claim about something never counted.
        self._participant_types = {
            item.id: frozenset(participant.entity_type for participant in item.participants)
            for item in pack.event_types
        }

    def generate(
        self,
        source: BatchSource,
        anchor_entity_ids: frozenset[str],
        known_entity_ids: frozenset[str],
        envelope: OutputEnvelope,
        *,
        conflict_policy: str,
    ) -> GenerationResult:
        """Run both passes and COLLECT every event, in the canonical sequence.

        Convenience over `stream`, for a caller that wants the whole log in hand: the
        fixture tests, and any dataset small enough that holding it is free.

        **It is not free on a large one.** The reference dataset expands to more events than
        an 8 GB machine can hold as models at once, measured rather than predicted --
        `tests/integration/test_full_expansion_budget.py` records the numbers. A caller
        working at that scale uses `stream` and writes each event out as it arrives.

        Args:
            source: a callable returning a fresh iterable of mapped record batches. Called
                twice; a generator passed directly would be empty on the second call, which
                is why the parameter is a factory.
            anchor_entity_ids: the identifiers of entities that anchor a process definition.
            known_entity_ids: every identifier module 3 minted, for orphan detection.
            envelope: the output envelope this run's artifacts carry.
            conflict_policy: module 3's identity policy, recorded in the report.
        """
        streamed = self.stream(
            source,
            anchor_entity_ids,
            known_entity_ids,
            envelope,
            conflict_policy=conflict_policy,
        )
        events = canonical_events(streamed.events)
        return GenerationResult(events=events, report=streamed.report())

    def stream(
        self,
        source: BatchSource,
        anchor_entity_ids: frozenset[str],
        known_entity_ids: frozenset[str],
        envelope: OutputEnvelope,
        *,
        conflict_policy: str,
    ) -> StreamedGeneration:
        """Run both passes, YIELDING each event as it is materialised.

        Peak memory is then a function of the number of distinct OCCURRENCES and their
        citations -- which pass A must hold to address an event at all -- and never of the
        events themselves. On the reference dataset that is the difference between an
        expansion that completes and one that swaps.

        **Events arrive in record sequence, not in the canonical one.** The canonical
        sequence `(t_earliest, t_latest, event_id)` is a total sort over the whole log
        (`CONVENTIONS.md` §11) and cannot be produced by a stream. A caller that needs it
        sorts after collecting, or -- for a store -- reads back under an explicit sort
        clause on that key, which is what §11 requires of every query feeding the pipeline
        anyway. The sequence is a rendering concern in both cases and is **never** a
        precedence claim.

        The report is available only once the stream is exhausted, which is why it is a
        method on the returned object rather than a field: a report offered before the
        counts were complete would be a report about part of a run.
        """
        index = OccurrenceIndex()
        counters = ConditionCounters()
        outcome = EmissionOutcome()
        # Pass B re-evaluates the same conditions over the same records, so its counts would
        # be exactly pass A's counted twice. They are discarded into a sink rather than
        # summed, and the report carries pass A's.
        discard_counts = ConditionCounters()
        discard_outcome = EmissionOutcome()
        records_read = 0

        for batch in source():
            for entry in batch.records:
                records_read += 1
                record = RecordView.of(entry)
                for emission in self._builder.emissions:
                    witnessed = self._builder.witnessed(
                        record, emission, known_entity_ids, counters, outcome
                    )
                    if witnessed is None:
                        continue
                    key, _resolved, _interval, _changed = witnessed
                    index.witness(key, record.evidence_record_id, record.row_number)

        coverage = ProcessCoverageAccumulator(
            definitions=self._processes, participant_types=self._participant_types
        )
        first_record_for: dict[str, str] = {}
        tally = _Tally()

        def _events() -> Iterator[Event]:
            """Pass B: materialise each occurrence once, at its first witness."""
            for batch in source():
                for entry in batch.records:
                    record = RecordView.of(entry)
                    for emission in self._builder.emissions:
                        witnessed = self._builder.witnessed(
                            record, emission, known_entity_ids, discard_counts, discard_outcome
                        )
                        if witnessed is None:
                            continue
                        key, resolved, interval, changed = witnessed
                        coverage.observe(
                            anchor_entity_ids, emission.event_type, resolved.entity_ids
                        )
                        for entity_id in resolved.entity_ids:
                            first_record_for.setdefault(entity_id, record.evidence_record_id)
                        if not index.is_first_witness(
                            key, record.evidence_record_id, record.row_number
                        ):
                            continue
                        event = self._builder.build(
                            record,
                            emission,
                            resolved,
                            interval,
                            changed,
                            index.evidence_for(key),
                        )
                        tally.observe(event)
                        yield event

            for definition in self._processes:
                for entity_id in sorted(anchor_entity_ids):
                    coverage.register(definition.id, entity_id)
            witnessable = frozenset(item.event_type for item in self._builder.emissions)
            for marker in self._gap_markers(coverage, witnessable, first_record_for):
                tally.observe(marker)
                tally.gap_markers += 1
                yield marker
            tally.complete = True

        def _report() -> EventQualityReport:
            if not tally.complete:
                raise ContractViolationError(
                    "the event quality report was requested before the stream was "
                    "exhausted. Its counts would describe part of a run, and a partial "
                    "count is indistinguishable from a complete one once it is written "
                    "down."
                )
            witnessable = frozenset(item.event_type for item in self._builder.emissions)
            return self._report(
                tally,
                coverage.results(witnessable),
                outcome,
                counters,
                records_read,
                envelope,
                conflict_policy,
            )

        return StreamedGeneration(events=_events(), report=_report)

    def _gap_markers(
        self,
        coverage: ProcessCoverageAccumulator,
        witnessable: frozenset[str],
        first_record_for: dict[str, str],
    ) -> tuple[Event, ...]:
        """Return the markers `EMIT_GAP_MARKER` calls for, or nothing under `RECORD_GAP`.

        Under `RECORD_GAP` -- the default -- this returns nothing at all and the gaps live
        only in the coverage report. That is the whole of ADR-0040: the shape of the process
        stays visible where it can be read, and nothing enters the event store that the
        causal engine could attach an edge to.
        """
        if self._policy is MissingEventPolicy.RECORD_GAP:
            return ()
        markers: list[Event] = []
        for definition in sorted(self._processes, key=lambda item: item.id):
            table = coverage.anchors[definition.id]
            for anchor_entity_id in sorted(table):
                evidence = first_record_for.get(anchor_entity_id)
                if evidence is None:
                    # Nothing was ever emitted for this anchor, so no record of it is in
                    # hand to cite. A marker with no citation would violate LAW-EVIDENCE, so
                    # the gap stays in the report where it needs none.
                    continue
                for step in coverage.gaps_for(definition, table[anchor_entity_id]):
                    if step in witnessable:
                        # A step that CAN be witnessed and was not is a fact about this
                        # instance. Marking it would assert an occurrence the dataset
                        # actively did not record, which is a different claim from
                        # "no field could ever record it".
                        continue
                    markers.append(
                        self._builder.build_gap_marker(
                            step, anchor_entity_id, evidence, definition.id
                        )
                    )
        return tuple(markers)

    def _report(
        self,
        tally: _Tally,
        coverage: tuple[ProcessCoverage, ...],
        outcome: EmissionOutcome,
        counters: ConditionCounters,
        records_read: int,
        envelope: OutputEnvelope,
        conflict_policy: str,
    ) -> EventQualityReport:
        """Assemble every count the quality report states, from the streaming tally.

        Reads counters rather than a list of events on purpose: the report is the artifact
        that says what the run produced, and requiring the run to be held in memory to
        produce it would make the honest account of a large expansion the one thing a large
        expansion could not afford.
        """
        specs = {item.id: item for item in self._pack.event_types}
        rules = {emission.event_type for emission in self._builder.emissions}
        tallies = tuple(
            EventTypeTally(
                event_type=event_type,
                observation_mode=spec.observation.value,
                provenance_class=spec.provenance_class.value,
                has_emission_rule=event_type in rules,
                events=tally.by_type.get(event_type, 0),
                records_witnessing=outcome.fired.get(event_type, 0),
                suppressed_missing_participant=outcome.suppressed_missing_participant.get(
                    event_type, 0
                ),
                orphaned=outcome.orphaned.get(event_type, 0),
            )
            for event_type, spec in sorted(specs.items())
        )
        return EventQualityReport(
            envelope=envelope,
            missing_event_policy=self._policy.value,
            conflict_policy=conflict_policy,
            records_read=records_read,
            events_total=tally.total,
            gap_markers_emitted=tally.gap_markers,
            by_event_type=tallies,
            by_provenance_class=tuple(sorted(tally.by_provenance.items())),
            by_precision=tuple(sorted(tally.by_precision.items())),
            by_timestamp_kind=tuple(sorted(tally.by_kind.items())),
            orphan_events=tally.orphans,
            unevaluable_conditions=counters.sequenced(),
            process_coverage=coverage,
            event_types_never_emitted=tuple(
                sorted(name for name in specs if not tally.by_type.get(name))
            ),
            not_checked=_not_checked(tally.unplaced),
        )


def _not_checked(unplaced: int) -> tuple[str, ...]:
    """Assemble the explicit list of checks this module did not perform."""
    return (
        "**Whether a derived occurrence actually occurred.** Every DERIVED event is a "
        "reconstruction from fields that imply it. That the implication holds is the pack "
        "author's claim and the mapping author's claim; nothing in this repository can "
        "check either, and a wrong one produces silently wrong causality rather than an "
        "error. This is risk R-16.",
        "**Whether the emission rule matches the pack's stated basis.** The two are written "
        "in different files on purpose so they can be read against each other. Nothing "
        "mechanically compares prose to an operator tree.",
        "**Causal accuracy.** There is no causal ground truth in this dataset "
        "(`CONVENTIONS.md` §14), so nothing here or downstream can measure it. No test in "
        "this module asserts that any event is a cause of any other; none may.",
        f"**Whether {unplaced:,} unplaced events belong where a timeline puts them.** An "
        "UNKNOWN interval excludes nothing and claims nothing. Sorting such an event into a "
        "sequence is a rendering choice and never a precedence claim.",
        "**Persistence.** No event was written to PostgreSQL: forbidden edge F4 permits only "
        "`orchestration` to import `causalog.persistence`, and no orchestration pipeline "
        "exists yet (OQ-014). This run ends at these artifacts.",
    )
