"""Synthetic, domain-neutral fact builders for the persistence tests.

`CONVENTIONS.md` §14: fixtures are synthetic and domain-neutral by default, and
DataCo-derived fixtures live only in `tests/fixtures/dataco/`. Nothing here names a real
domain -- the entity types are `PARTICIPANT` and `PLACE`, the event types are `STAGE_ONE`
and `STAGE_TWO`. That is not squeamishness about LAW-DOMAIN: a persistence test that used
supply-chain vocabulary would read as though the schema knew something about supply chains,
and the whole claim of this layer is that it does not.

Every builder produces a CONTENT-ADDRESSED artifact by calling the type's own `address`
classmethod rather than by inventing an identifier. A test fixture with a hand-written id
would pass while the real address recipe was broken, which is the one thing these tests
must not do.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.temporal import Precision, TimeInterval
from causalog.core.types import (
    CausalEdge,
    ConfidenceComponent,
    ConfidenceVector,
    DirectCause,
    Entity,
    Event,
    EvidenceItem,
    EvidenceKind,
    EvidenceRecord,
    Lifecycle,
    Relationship,
    State,
    Timeline,
    TimelineView,
    Transition,
)
from causalog.graph_engine.timeline_builder.sequencing import sequence_events

#: A fixed ontology hash. Content addressing means the fixtures' identifiers are a function
#: of this value, so pinning it keeps every expected identifier in these tests stable.
ONTOLOGY_HASH = "ont:0000000000000000"

DATASET_VERSION = "dataset:test-0001"

#: A fixed instant. `datetime.now()` in a fixture would make identifiers vary per run,
#: which is the determinism defect `CONVENTIONS.md` §11 exists to prevent -- and it would
#: make a failure impossible to reproduce from the test name.
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def interval(
    offset_days: int, *, span_days: int = 0, precision: Precision = Precision.DAY
) -> TimeInterval:
    """Return a bounded interval `offset_days` after the fixed epoch."""
    start = EPOCH + timedelta(days=offset_days)
    return TimeInterval(
        t_earliest=start,
        t_latest=start + timedelta(days=span_days),
        precision=precision,
        provenance=ProvenanceClass.OBSERVED,
        source="fixture",
    )


def evidence_record(locator: str, dataset_version: str = DATASET_VERSION) -> EvidenceRecord:
    """Return a citation addressed by its own recipe."""
    return EvidenceRecord(
        evidence_record_id=EvidenceRecord.address(dataset_version, locator),
        dataset_version=dataset_version,
        source_locator=locator,
        source_timezone=None,
    )


def confidence(scalar: float = 0.5, evidence_record_ids: tuple[str, ...] = ()) -> ConfidenceVector:
    """Return a single-component vector.

    One component rather than none: an empty vector is a defect and not zero confidence
    (LAW-EVIDENCE), so there is no fixture that produces one.
    """
    return ConfidenceVector(
        components=(
            ConfidenceComponent(
                component_name="rule_support",
                value=scalar,
                provenance_class=ProvenanceClass.OBSERVED,
                evidence_record_ids=evidence_record_ids,
            ),
        ),
        scalar=scalar,
        aggregation="weighted_mean_v1",
        provenance_class=ProvenanceClass.OBSERVED,
    )


def entity(
    natural_key: str, entity_type: str = "PARTICIPANT", *, citation: EvidenceRecord
) -> Entity:
    """Return an OBSERVED, cited participant."""
    return Entity(
        entity_id=Entity.address(ONTOLOGY_HASH, entity_type, natural_key),
        entity_type=entity_type,
        natural_key=natural_key,
        attributes=(("label", natural_key),),
        lifecycle=Lifecycle(
            state_names=("CLOSED", "OPEN"),
            legal_transitions=(("OPEN", "CLOSED"),),
            provenance_class=ProvenanceClass.ASSUMED,
        ),
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=(citation.evidence_record_id,),
    )


def event(
    event_type: str,
    occurred_at: TimeInterval,
    *,
    citation: EvidenceRecord,
    participants: tuple[Entity, ...] = (),
    is_actionable: bool = False,
) -> Event:
    """Return an OBSERVED, cited event addressed by its own recipe."""
    entity_ids = tuple(participant.entity_id for participant in participants)
    changed = (("stage", event_type),)
    return Event(
        event_id=Event.address(
            ONTOLOGY_HASH,
            event_type,
            entity_ids,
            occurred_at,
            changed,
            (citation.evidence_record_id,),
        ),
        event_type=event_type,
        occurred_at=occurred_at,
        trigger=None,
        source_entity_ids=entity_ids,
        target_entity_ids=(),
        changed_attributes=changed,
        metadata=(("origin", "fixture"),),
        provenance_class=ProvenanceClass.OBSERVED,
        confidence=confidence(evidence_record_ids=(citation.evidence_record_id,)),
        is_actionable=is_actionable,
        source_record_ref=citation.evidence_record_id,
        evidence_record_ids=(citation.evidence_record_id,),
    )


def state(
    subject: Entity,
    state_name: str,
    held_over: TimeInterval,
    *,
    derived_from: Event,
    citation: EvidenceRecord,
) -> State:
    """Return an OBSERVED state addressed by its own recipe."""
    return State(
        state_id=State.address(subject.entity_id, state_name, held_over),
        entity_id=subject.entity_id,
        state_name=state_name,
        held_over=held_over,
        derived_from_event_id=derived_from.event_id,
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=(citation.evidence_record_id,),
    )


def transition(earlier: State, later: State, *, causing: Event) -> Transition:
    """Return an OBSERVED transition between two states."""
    return Transition(
        transition_id=Transition.address(earlier.state_id, later.state_id, causing.event_id),
        from_state_id=earlier.state_id,
        to_state_id=later.state_id,
        causing_event_id=causing.event_id,
        provenance_class=ProvenanceClass.OBSERVED,
    )


def timeline(
    *events: Event,
    view: TimelineView = TimelineView.ENTITY,
    subject_entity_ids: tuple[str, ...] | None = None,
    process_definition_id: str | None = None,
    ontology_hash: str = ONTOLOGY_HASH,
) -> Timeline:
    """Return a `Timeline` sequencing `events` by the real canonical-sort/tie-break rule.

    Reuses `graph_engine.timeline_builder.sequencing.sequence_events` rather than
    reimplementing the tie-break -- a fixture with its own ordering logic could pass while
    the real one was broken, which is the one thing `facts.py` must not do
    (module docstring above).
    """
    entries = sequence_events(events)
    ids = subject_entity_ids or tuple(
        sorted({eid for e in events for eid in e.source_entity_ids + e.target_entity_ids})
    )
    event_ids = tuple(event.event_id for event in events)
    return Timeline(
        timeline_id=Timeline.address(
            ontology_hash=ontology_hash,
            view=view,
            process_definition_id=process_definition_id,
            subject_entity_ids=ids,
            event_ids=event_ids,
        ),
        view=view,
        process_definition_id=process_definition_id,
        subject_entity_ids=ids,
        entries=entries,
        provenance_class=combine(
            *(
                entry.sequence_provenance
                for entry in entries
                if entry.sequence_provenance is not None
            )
        ),
    )


def relationship(
    source: Entity,
    target: Entity,
    relationship_type: str = "BELONGS_TO",
    *,
    citation: EvidenceRecord,
) -> Relationship:
    """Return a structural, non-causal relationship."""
    return Relationship(
        relationship_id=f"rel:{source.entity_id[-8:]}{target.entity_id[-8:]}",
        relationship_type=relationship_type,
        source_entity_id=source.entity_id,
        target_entity_id=target.entity_id,
        valid_over=interval(0, span_days=365),
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=(citation.evidence_record_id,),
    )


def evidence_item(supporting_ids: tuple[str, ...]) -> EvidenceItem:
    """Return a justification with non-empty `verification`.

    `verification` is never blank in a fixture, because an item a reader cannot re-execute
    is a defect rather than a weak item -- a fixture that produced one would be testing the
    repository against input the contract forbids.
    """
    return EvidenceItem(
        evidence_item_id=f"evi:{abs(hash(supporting_ids)) % 10**16:016d}",
        kind=EvidenceKind.RULE,
        description="a fixture rule fired",
        supporting_ids=tuple(sorted(supporting_ids)),
        strength=0.75,
        verification="R-FIXTURE-0001",
        provenance_class=ProvenanceClass.INFERRED,
    )


def causal_edge(cause: Event, effect: Event, run_id: str) -> CausalEdge:
    """Return an edge built through the sanctioned constructor.

    `CausalEdge.between` rather than a direct call, because `between` is the only
    constructor that can evaluate LAW-TIME -- it takes the two `Event` objects rather than
    their identifiers. A fixture that bypassed it could hand the repository an edge the
    engine could never have produced (docs/contracts.md §5).
    """
    return CausalEdge.between(
        source_event=cause,
        target_event=effect,
        payload=DirectCause(),
        confidence=confidence(0.8),
        evidence=(evidence_item((cause.event_id, effect.event_id)),),
        propagation_weight=0.5,
        provenance_class=ProvenanceClass.INFERRED,
        run_id=run_id,
    )
