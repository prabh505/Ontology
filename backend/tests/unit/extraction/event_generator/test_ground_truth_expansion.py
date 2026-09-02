"""The ground truth: twenty hand-built records against a hand-derived expansion.

`CONVENTIONS.md` §3 wants at least one test per stated failure mode; this is the other kind
-- the one that says what the module is FOR. Every expectation it reads comes from
`tests/fixtures/dataco/expansion.py`, which was written by reading the pack's prose against
the fixture's status columns by hand, before this module produced anything. Keep it forever.

It asserts equality, not shape: the exact event set per order, the exact totals per type,
the exact participants and interval of two fully specified occurrences, and that every
identifier equals the address recipe recomputed from the fields the test just checked.
"""

from __future__ import annotations

from collections import Counter

import pytest

from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision
from causalog.core.types.entity import Entity
from causalog.core.types.event import Event
from extraction_harness import Expansion, Harness, expand
from fixtures.dataco.expansion import (
    EXPECTED_ATTRIBUTE_CONFLICTS,
    EXPECTED_ENTITY_COUNTS,
    EXPECTED_EVENT_COUNTS,
    EXPECTED_EVENT_TOTAL,
    EXPECTED_LINE_EVENTS,
    EXPECTED_NEVER_EMITTED,
    EXPECTED_ORDER_EVENTS,
    GROUND_TRUTH_DATASET_VERSION,
    ORDERS,
    OrderCase,
    rows,
)


@pytest.fixture(scope="module")
def expansion() -> Expansion:
    return expand(rows(), GROUND_TRUTH_DATASET_VERSION)


def _entity_id(harness: Harness, entity_type: str, natural_key: str) -> str:
    return Entity.address(harness.ontology_hash, entity_type, natural_key)


def test_the_expansion_produces_exactly_the_expected_event_total(expansion: Expansion) -> None:
    _harness, _extraction, generation = expansion
    assert len(generation.events) == EXPECTED_EVENT_TOTAL


def test_every_event_type_produces_exactly_the_expected_count(expansion: Expansion) -> None:
    _harness, _extraction, generation = expansion
    counted = Counter(event.event_type for event in generation.events)
    assert dict(counted) == {name: count for name, count in EXPECTED_EVENT_COUNTS.items() if count}


@pytest.mark.parametrize("case", ORDERS, ids=lambda case: f"order-{case.reference}")
def test_each_order_produces_exactly_its_hand_derived_event_set(
    expansion: Expansion, case: OrderCase
) -> None:
    """The order-scoped events of one order are exactly the hand-derived set.

    Order-scoped means the event type names no line among its participants, so however many
    lines an order carries, its lines witness ONE occurrence between them. That the count is
    one is asserted here as well as the set: deduplication failing would show up as a set
    that still matched and a count that did not.
    """
    harness, _extraction, generation = expansion
    order_id = _entity_id(harness, "ORDER", str(case.reference))
    line_scoped = EXPECTED_LINE_EVENTS[case.reference]
    order_scoped = [
        event
        for event in generation.events
        if order_id in event.source_entity_ids + event.target_entity_ids
        and event.event_type not in line_scoped
    ]
    assert {event.event_type for event in order_scoped} == EXPECTED_ORDER_EVENTS[case.reference]
    assert len(order_scoped) == len(EXPECTED_ORDER_EVENTS[case.reference])


@pytest.mark.parametrize("case", ORDERS, ids=lambda case: f"order-{case.reference}")
def test_each_line_produces_exactly_its_hand_derived_event_set(
    expansion: Expansion, case: OrderCase
) -> None:
    """Every line of one order produces exactly the hand-derived line-scoped set."""
    harness, _extraction, generation = expansion
    line_references = [
        record["Order Item Id"] for record in rows() if record["Order Id"] == str(case.reference)
    ]
    assert len(line_references) == case.lines
    for reference in line_references:
        line_id = _entity_id(harness, "ORDER_ITEM", reference)
        produced = {
            event.event_type
            for event in generation.events
            if line_id in event.source_entity_ids + event.target_entity_ids
        }
        assert produced == EXPECTED_LINE_EVENTS[case.reference]


def test_the_pack_declares_one_event_type_no_record_can_witness(expansion: Expansion) -> None:
    _harness, _extraction, generation = expansion
    assert generation.report.event_types_never_emitted == EXPECTED_NEVER_EMITTED


def test_the_two_lines_of_one_order_produce_one_placement_between_them(
    expansion: Expansion,
) -> None:
    """Occurrence deduplication, stated as the case it exists for.

    Order 1 carries two lines. One purchase was placed. Emitting per record would produce
    two `ORDER_PLACED` events and would make the fixture look like sixteen purchases.
    """
    harness, _extraction, generation = expansion
    order_id = _entity_id(harness, "ORDER", "1")
    placements = [
        event for event in generation.of_type("ORDER_PLACED") if order_id in event.source_entity_ids
    ]
    assert len(placements) == 1
    assert len(placements[0].evidence_record_ids) == 2, (
        "both lines must appear as citations: they corroborate one occurrence, and dropping "
        "either would lose the evidence that it was witnessed twice"
    )
    assert placements[0].source_record_ref in placements[0].evidence_record_ids


def test_the_one_observed_occurrence_is_placed_by_its_column(expansion: Expansion) -> None:
    """`ORDER_PLACED` for order 1: fully specified, participants and interval included."""
    harness, _extraction, generation = expansion
    order_id = _entity_id(harness, "ORDER", "1")
    event = next(
        item for item in generation.of_type("ORDER_PLACED") if order_id in item.source_entity_ids
    )
    assert event.provenance_class is ProvenanceClass.OBSERVED
    assert event.source_entity_ids == (order_id,)
    assert set(event.target_entity_ids) == {
        _entity_id(harness, "CUSTOMER", "501"),
        _entity_id(harness, "MARKET_REGION", "Pacific Asia,Southeast Asia"),
    }
    assert event.occurred_at.precision is Precision.MINUTE
    assert event.occurred_at.provenance is ProvenanceClass.ASSUMED
    assert event.occurred_at.t_earliest.isoformat() == "2018-01-01T09:00:00+00:00"
    assert dict(event.changed_attributes) == {
        "order_reference": "1",
        "payment_type": "DEBIT",
        "placed_at": "1/1/2018 09:00",
        "order_profit": "91.25",
    }
    assert event.is_actionable is False


def test_the_delayed_shipment_is_derived_arithmetic_and_never_observed(
    expansion: Expansion,
) -> None:
    """`SHIPMENT_DELAYED` for order 10: the type a lifecycle walk could never produce."""
    harness, _extraction, generation = expansion
    order_id = _entity_id(harness, "ORDER", "10")
    event = next(
        item
        for item in generation.of_type("SHIPMENT_DELAYED")
        if order_id in item.source_entity_ids
    )
    assert event.provenance_class is ProvenanceClass.INFERRED
    assert event.occurred_at.precision is Precision.UNKNOWN
    assert dict(event.changed_attributes) == {
        "actual_shipping_days": "6",
        "scheduled_shipping_days": "1",
    }
    assert event.is_actionable is True
    assert event.confidence.provenance_class is ProvenanceClass.ASSUMED
    assert {component.component_name for component in event.confidence.components} == {
        "rule_support",
        "temporal_support",
    }


def test_the_delivered_instant_is_the_dispatch_instant_advanced_by_recorded_days(
    expansion: Expansion,
) -> None:
    """`SHIPMENT_DELIVERED` for order 1: dispatch + 3 days, at DAY precision, INFERRED."""
    harness, _extraction, generation = expansion
    order_id = _entity_id(harness, "ORDER", "1")
    event = next(
        item
        for item in generation.of_type("SHIPMENT_DELIVERED")
        if order_id in item.source_entity_ids
    )
    # Order 1 is placed 1 January and dispatched four days later; three realised shipping
    # days put arrival on the 8th, spanning the whole day because the anchor does.
    assert event.occurred_at.t_earliest.isoformat() == "2018-01-08T00:00:00+00:00"
    assert event.occurred_at.precision is Precision.DAY
    assert event.occurred_at.provenance is ProvenanceClass.INFERRED
    assert event.occurred_at.kind.value == "INFERRED"


def test_every_identifier_equals_the_address_recipe_recomputed(expansion: Expansion) -> None:
    """No event carries an identifier that its own fields do not produce.

    `CONVENTIONS.md` §9 states the recipe; this recomputes it from the fields every other
    test in this file has just checked, so the identifiers are verified against the
    specification rather than against a recorded output.
    """
    harness, _extraction, generation = expansion
    for event in generation.events:
        assert event.event_id == Event.address(
            ontology_hash=harness.ontology_hash,
            event_type=event.event_type,
            entity_ids=tuple(sorted(set(event.source_entity_ids + event.target_entity_ids))),
            occurred_at=event.occurred_at,
            changed_attributes=event.changed_attributes,
            evidence_record_ids=event.evidence_record_ids,
        )
    assert len({event.event_id for event in generation.events}) == len(generation.events)


def test_extraction_produces_exactly_the_expected_entities(expansion: Expansion) -> None:
    _harness, extraction, _generation = expansion
    counted = Counter(entity.entity_type for entity in extraction.entities)
    assert dict(counted) == EXPECTED_ENTITY_COUNTS


def test_the_one_planted_disagreement_is_recorded_and_resolved(expansion: Expansion) -> None:
    _harness, extraction, _generation = expansion
    assert extraction.report.conflicts_total == EXPECTED_ATTRIBUTE_CONFLICTS
    conflict = extraction.report.conflicts[0]
    assert conflict.entity_type == "CUSTOMER"
    assert conflict.attribute == "customer_state"
    assert {conflict.held_value, conflict.offered_value} == {"PR", "NY"}
    assert conflict.resolved_value == "PR", "FIRST_WINS keeps the earlier record's value"
