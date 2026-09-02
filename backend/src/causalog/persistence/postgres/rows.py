"""Explicit row-to-model and model-to-row mapping.

There is no ORM here and no mapper that infers columns from annotations. The constraint is
stated in the brief and it is the right one for this system: **no ORM lazy-loading magic
in hot paths**. A lazy relationship on `Event.confidence` would turn one canonical-sequence
read of the largest table in the system into one query per row, and it would do it
invisibly -- the code reads identically whether the attribute is loaded or fetched.

So every function here takes a tuple in a stated column order and returns a validated
model, or takes a model and returns a tuple. The column orders live beside the SQL that
produces them (`sql.py`), and a mismatch surfaces as a pydantic validation error naming
the field rather than as a value silently landing in the wrong column.

Validation is never skipped on the way in. `from_canonical_json` re-runs every invariant
at the serialization boundary (`docs/contracts.md` §6), and so does construction here: a
row that has been sitting in a table since a previous engine version is untrusted input.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision, TemporalVerdict, TimeInterval
from causalog.core.types import (
    AmplifyingCause,
    CausalEdge,
    CausalEdgeKind,
    CausalEdgePayload,
    ConditionalCause,
    ConfidenceComponent,
    ConfidenceVector,
    ContributingCause,
    DirectCause,
    Entity,
    Event,
    EvidenceItem,
    EvidenceKind,
    EvidenceRecord,
    InhibitingCause,
    Lifecycle,
    Relationship,
    State,
    Transition,
)

__all__ = [
    "causal_edge_from_row",
    "confidence_vector_from_rows",
    "entity_from_row",
    "event_from_row",
    "evidence_item_from_row",
    "evidence_record_from_row",
    "interval_from_columns",
    "interval_to_columns",
    "payload_from_row",
    "quantized",
    "relationship_from_row",
    "state_from_row",
    "transition_from_row",
]


def quantized(value: Decimal | float) -> float:
    """Return a stored NUMERIC as a float.

    The column is `NUMERIC(9, 6)` precisely so this conversion is lossless in the
    direction that matters: six decimal places is the quantization every serialization
    boundary applies (`CONVENTIONS.md` §11), so a value that round-tripped through the
    database is already at the precision the contract expects. Storing `float8` instead
    would have reintroduced the drift the quantization exists to remove.
    """
    return float(value)


def interval_from_columns(
    t_earliest: datetime,
    t_latest: datetime,
    precision: str,
    provenance: str,
    source: str,
) -> TimeInterval:
    """Rebuild a `TimeInterval` from its five flattened columns.

    Every invariant is re-run by the constructor -- bounds tz-aware and UTC, EXACT implies
    a point, UNKNOWN implies ASSUMED and the sentinels. The database CHECKs assert the
    same things, deliberately: the schema defends against a writer that bypasses this
    code, and this defends against a schema that predates a contract change.
    """
    return TimeInterval(
        t_earliest=t_earliest,
        t_latest=t_latest,
        precision=Precision(precision),
        provenance=ProvenanceClass(provenance),
        source=source,
    )


def interval_to_columns(interval: TimeInterval) -> tuple[datetime, datetime, str, str, str]:
    """Flatten a `TimeInterval` into its five columns, in the schema's order."""
    return (
        interval.t_earliest,
        interval.t_latest,
        interval.precision.value,
        interval.provenance.value,
        interval.source,
    )


def confidence_vector_from_rows(
    scalar: Decimal | float,
    aggregation: str,
    provenance: str,
    component_rows: list[tuple[str, Decimal | float, str, tuple[str, ...]]],
) -> ConfidenceVector:
    """Rebuild a `ConfidenceVector` from its header row and its component rows.

    `component_rows` must already be sorted by name -- the SQL that produces them carries
    the `ORDER BY`, and the constructor refuses an unsorted vector. Sorting here instead
    would hide an unsequenced read (`CONVENTIONS.md` §11) behind a repair.
    """
    if not component_rows:
        raise ContractViolationError(
            "A stored ConfidenceVector has no components. An empty vector is a defect, "
            "not zero confidence (LAW-EVIDENCE); the row should never have been written."
        )
    return ConfidenceVector(
        components=tuple(
            ConfidenceComponent(
                component_name=name,
                value=quantized(value),
                provenance_class=ProvenanceClass(component_provenance),
                evidence_record_ids=evidence_ids,
            )
            for name, value, component_provenance, evidence_ids in component_rows
        ),
        scalar=quantized(scalar),
        aggregation=aggregation,
        provenance_class=ProvenanceClass(provenance),
    )


def evidence_record_from_row(row: tuple[Any, ...]) -> EvidenceRecord:
    """Column order: evidence_record_id, dataset_version, source_locator, source_timezone."""
    return EvidenceRecord(
        evidence_record_id=row[0],
        dataset_version=row[1],
        source_locator=row[2],
        source_timezone=row[3],
    )


def evidence_item_from_row(row: tuple[Any, ...], supporting_ids: tuple[str, ...]) -> EvidenceItem:
    """Column order: evidence_item_id, kind, description, strength, verification, provenance."""
    return EvidenceItem(
        evidence_item_id=row[0],
        kind=EvidenceKind(row[1]),
        description=row[2],
        supporting_ids=supporting_ids,
        strength=quantized(row[3]),
        verification=row[4],
        provenance_class=ProvenanceClass(row[5]),
    )


def entity_from_row(
    row: tuple[Any, ...],
    attributes: tuple[tuple[str, str], ...],
    lifecycle_states: tuple[str, ...],
    lifecycle_transitions: tuple[tuple[str, str], ...],
    evidence_record_ids: tuple[str, ...],
) -> Entity:
    """Column order: entity_id, entity_type, natural_key, provenance_class."""
    return Entity(
        entity_id=row[0],
        entity_type=row[1],
        natural_key=row[2],
        attributes=attributes,
        lifecycle=Lifecycle(
            state_names=lifecycle_states,
            legal_transitions=lifecycle_transitions,
            # ASSUMED by contract: a lifecycle is configuration read from the ontology
            # pack, never something the source observed (docs/contracts.md §5).
            provenance_class=ProvenanceClass.ASSUMED,
        ),
        provenance_class=ProvenanceClass(row[3]),
        evidence_record_ids=evidence_record_ids,
    )


def event_from_row(
    row: tuple[Any, ...],
    confidence: ConfidenceVector,
    source_entity_ids: tuple[str, ...],
    target_entity_ids: tuple[str, ...],
    changed_attributes: tuple[tuple[str, str], ...],
    metadata: tuple[tuple[str, str], ...],
    evidence_record_ids: tuple[str, ...],
) -> Event:
    """Rebuild an `Event` from its row and its already-fetched child collections.

    Column order: event_id, event_type, t_earliest, t_latest, time_precision,
    time_provenance, time_source, trigger_mechanism, provenance_class, is_actionable,
    source_record_ref.
    """
    return Event(
        event_id=row[0],
        event_type=row[1],
        occurred_at=interval_from_columns(row[2], row[3], row[4], row[5], row[6]),
        trigger=row[7],
        source_entity_ids=source_entity_ids,
        target_entity_ids=target_entity_ids,
        changed_attributes=changed_attributes,
        metadata=metadata,
        provenance_class=ProvenanceClass(row[8]),
        confidence=confidence,
        is_actionable=row[9],
        source_record_ref=row[10],
        evidence_record_ids=evidence_record_ids,
    )


def state_from_row(row: tuple[Any, ...], evidence_record_ids: tuple[str, ...]) -> State:
    """Rebuild a `State` from its row.

    Column order: state_id, entity_id, state_name, valid_from, valid_to,
    valid_precision, valid_provenance, valid_source, derived_from_event_id,
    provenance_class.

    The system-time columns are deliberately absent from the returned model. System time
    is a storage concern: it appears in no `causalog.core` type, in no content address, and
    in no output envelope, and no reasoning module may read it (ADR-0032). A `State`
    carrying its own `system_from` would put insertion wall-clock inside a reasoning input.
    """
    return State(
        state_id=row[0],
        entity_id=row[1],
        state_name=row[2],
        held_over=interval_from_columns(row[3], row[4], row[5], row[6], row[7]),
        derived_from_event_id=row[8],
        provenance_class=ProvenanceClass(row[9]),
        evidence_record_ids=evidence_record_ids,
    )


def transition_from_row(row: tuple[Any, ...]) -> Transition:
    """Column order: transition_id, from_state_id, to_state_id, causing_event_id, provenance."""
    return Transition(
        transition_id=row[0],
        from_state_id=row[1],
        to_state_id=row[2],
        causing_event_id=row[3],
        provenance_class=ProvenanceClass(row[4]),
    )


def relationship_from_row(
    row: tuple[Any, ...], evidence_record_ids: tuple[str, ...]
) -> Relationship:
    """Rebuild a `Relationship` from its row.

    Column order: relationship_id, relationship_type, source_entity_id,
    target_entity_id, valid_from, valid_to, valid_precision, valid_provenance,
    valid_source, provenance_class.
    """
    return Relationship(
        relationship_id=row[0],
        relationship_type=row[1],
        source_entity_id=row[2],
        target_entity_id=row[3],
        valid_over=interval_from_columns(row[4], row[5], row[6], row[7], row[8]),
        provenance_class=ProvenanceClass(row[9]),
        evidence_record_ids=evidence_record_ids,
    )


def payload_from_row(
    edge_kind: str,
    condition_expression: str | None,
    condition_holds: bool | None,
    joint_cause_group_id: str | None,
    co_cause_event_ids: tuple[str, ...],
    magnitude_multiplier: Decimal | float | None,
) -> CausalEdgePayload:
    """Rebuild the typed payload from the sparse union columns (ADR-0022).

    The five kinds are payload *types*, not string labels, so the reconstruction is a
    dispatch and not a cast. The database CHECKs already refuse an incomplete payload --
    an `AMPLIFYING` row with a NULL multiplier cannot exist -- and this function refuses it
    a second time rather than trusting the schema, because the schema is one migration
    away from the code at all times.
    """
    kind = CausalEdgeKind(edge_kind)
    if kind is CausalEdgeKind.DIRECT:
        return DirectCause()
    if kind is CausalEdgeKind.CONDITIONAL:
        if condition_expression is None or condition_holds is None:
            raise ContractViolationError(
                "A stored CONDITIONAL edge has no condition. The absence of the "
                "expression makes the claim unrecheckable, which is what "
                "ConditionalCause.condition_expression exists to prevent (ADR-0022)."
            )
        return ConditionalCause(
            condition_expression=condition_expression, condition_holds=condition_holds
        )
    if kind is CausalEdgeKind.CONTRIBUTING:
        if not joint_cause_group_id or not co_cause_event_ids:
            raise ContractViolationError(
                "A stored CONTRIBUTING edge names no joint cause group or no co-causes. "
                "A contributing cause is conjunctive: without its group it is a direct "
                "cause wearing the wrong label (ADR-0022)."
            )
        return ContributingCause(
            joint_cause_group_id=joint_cause_group_id, co_cause_event_ids=co_cause_event_ids
        )
    if magnitude_multiplier is None:
        raise ContractViolationError(
            f"A stored {kind.value} edge has no magnitude_multiplier. The multiplier IS "
            "the claim for these two kinds (ADR-0022)."
        )
    if kind is CausalEdgeKind.AMPLIFYING:
        return AmplifyingCause(magnitude_multiplier=quantized(magnitude_multiplier))
    return InhibitingCause(magnitude_multiplier=quantized(magnitude_multiplier))


def causal_edge_from_row(
    row: tuple[Any, ...],
    payload: CausalEdgePayload,
    confidence: ConfidenceVector,
    evidence: tuple[EvidenceItem, ...],
) -> CausalEdge:
    """Rebuild a `CausalEdge` from its row, its payload, and its evidence.

    Column order: causal_edge_id, source_event_id, target_event_id, propagation_weight,
    provenance_class, temporal_verdict, temporally_unverifiable, run_id.

    Constructed directly rather than through `CausalEdge.between`, because `between` takes
    the two `Event` objects so it can evaluate LAW-TIME, and a read from storage has
    identifiers rather than intervals. `docs/contracts.md` §6 states this limit exactly
    (DEF-0002): the stored `temporal_verdict` is re-*validated* here -- a `VIOLATION`
    value and an `OBSERVED` provenance are refused by the model -- but it is not
    re-*derived*, and it cannot be from this row alone. The projection drift check is
    where a laundered verdict would surface, not here.
    """
    return CausalEdge(
        causal_edge_id=row[0],
        source_event_id=row[1],
        target_event_id=row[2],
        payload=payload,
        confidence=confidence,
        evidence=evidence,
        propagation_weight=quantized(row[3]),
        provenance_class=ProvenanceClass(row[4]),
        temporal_verdict=TemporalVerdict(row[5]),
        temporally_unverifiable=row[6],
        run_id=row[7],
    )
