"""Hypothesis strategies for the canonical types.

Domain-neutral by default (`CONVENTIONS.md` §14): every generated name is a synthetic
token, and nothing here reaches for the reference dataset's vocabulary.

Floats are generated already quantized to six decimal places. That is not a convenience --
it is the state `CONVENTIONS.md` §11 requires every artifact to be in, and generating
unquantized values would test a shape the system never stores while making the round-trip
property fail for a reason that has nothing to do with serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import strategies as st

from causalog.core.aggregation import AGGREGATORS, aggregate
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import (
    UNKNOWN_EARLIEST,
    UNKNOWN_LATEST,
    Precision,
    TimeInterval,
)
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

#: Bounded well inside `datetime.min`/`datetime.max` so that arithmetic in a test cannot
#: overflow, which would fail for a reason unrelated to the property under test.
EARLIEST_GENERATED = datetime(2000, 1, 1, tzinfo=UTC)
LATEST_GENERATED = datetime(2030, 1, 1, tzinfo=UTC)

#: The precisions that describe a *placed* instant. `UNKNOWN` is excluded because it has
#: its own fixed bounds and is generated separately by `unknown_intervals`.
PLACED_PRECISIONS = [
    Precision.SECOND,
    Precision.MINUTE,
    Precision.HOUR,
    Precision.DAY,
]

#: The component names `weighted_mean_v1` declares a weight for (prd.md §49).
WEIGHTED_COMPONENT_NAMES = [
    "rule_support",
    "temporal_support",
    "historical_support",
    "statistical_support",
    "evidence_count",
    "graph_connectivity",
]


def tokens() -> st.SearchStrategy[str]:
    """Return non-empty synthetic identifier text, including separator characters.

    The separators are deliberately in the alphabet: a payload encoder that mishandles
    `|`, `,`, or `=` produces colliding identifiers, and that is exactly what the identifier
    property tests exist to catch.

    Whitespace-only draws are mapped away rather than filtered out. Several canonical types
    reject a blank string, and a filter that discarded those draws would spend the budget
    rejecting rather than exploring; prefixing keeps every draw useful and still lets a
    space appear inside the token.
    """
    return st.text(
        alphabet=st.sampled_from("abcdefgh0123456789_-|,=\\ "), min_size=1, max_size=12
    ).map(lambda drawn: drawn if drawn.strip() else f"a{drawn}")


def quantized_unit_floats() -> st.SearchStrategy[float]:
    """Return floats in `[0.0, 1.0]` already at the canonical resolution."""
    return st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False).map(
        lambda value: round(value, FLOAT_QUANTIZATION_PLACES)
    )


def utc_instants() -> st.SearchStrategy[datetime]:
    """Return timezone-aware UTC instants inside the generated range."""
    return st.datetimes(
        min_value=EARLIEST_GENERATED.replace(tzinfo=None),
        max_value=LATEST_GENERATED.replace(tzinfo=None),
        timezones=st.just(UTC),
    )


def provenance_classes() -> st.SearchStrategy[ProvenanceClass]:
    """Return any of the five provenance classes."""
    return st.sampled_from(list(ProvenanceClass))


@st.composite
def placed_intervals(draw: st.DrawFn) -> TimeInterval:
    """Return an interval whose instant was placed: EXACT, coarse, or INFERRED.

    Never `UNKNOWN`. Use `intervals` when the absent case should also be generated.
    """
    first = draw(utc_instants())
    second = draw(utc_instants())
    earliest, latest = min(first, second), max(first, second)
    provenance = draw(
        st.sampled_from(
            [ProvenanceClass.OBSERVED, ProvenanceClass.ASSUMED, ProvenanceClass.INFERRED]
        )
    )
    # EXACT requires equal bounds, and an INFERRED interval may never claim EXACT.
    exact = draw(st.booleans()) and provenance is not ProvenanceClass.INFERRED
    if exact:
        return TimeInterval(
            t_earliest=earliest,
            t_latest=earliest,
            precision=Precision.EXACT,
            provenance=provenance,
            source=draw(tokens()),
        )
    return TimeInterval(
        t_earliest=earliest,
        t_latest=latest,
        precision=draw(st.sampled_from(PLACED_PRECISIONS)),
        provenance=provenance,
        source=draw(tokens()),
    )


@st.composite
def unknown_intervals(draw: st.DrawFn) -> TimeInterval:
    """Return the one admissible shape of an absent instant."""
    return TimeInterval(
        t_earliest=UNKNOWN_EARLIEST,
        t_latest=UNKNOWN_LATEST,
        precision=Precision.UNKNOWN,
        provenance=ProvenanceClass.ASSUMED,
        source=draw(tokens()),
    )


def intervals() -> st.SearchStrategy[TimeInterval]:
    """Return any admissible interval, placed or absent."""
    return st.one_of(placed_intervals(), unknown_intervals())


@st.composite
def confidence_components(draw: st.DrawFn) -> ConfidenceComponent:
    """Return one component drawn from the weighted component names."""
    return ConfidenceComponent(
        component_name=draw(st.sampled_from(WEIGHTED_COMPONENT_NAMES)),
        value=draw(quantized_unit_floats()),
        provenance_class=draw(provenance_classes()),
        evidence_record_ids=tuple(
            sorted(draw(st.lists(tokens(), min_size=1, max_size=3, unique=True)))
        ),
    )


def component_sets() -> st.SearchStrategy[list[ConfidenceComponent]]:
    """Return a non-empty set of components with distinct names."""
    return st.lists(
        confidence_components(),
        min_size=1,
        max_size=6,
        unique_by=lambda component: component.component_name,
    )


@st.composite
def confidence_vectors(draw: st.DrawFn) -> ConfidenceVector:
    """Return a vector built through `aggregate`, which is the only sanctioned path."""
    return aggregate(draw(component_sets()), draw(st.sampled_from(sorted(AGGREGATORS))))


@st.composite
def evidence_items(draw: st.DrawFn) -> EvidenceItem:
    """Return one re-verifiable justification."""
    return EvidenceItem(
        evidence_item_id=draw(tokens()),
        kind=draw(st.sampled_from(list(EvidenceKind))),
        description=draw(tokens()),
        supporting_ids=tuple(sorted(draw(st.lists(tokens(), min_size=1, max_size=3, unique=True)))),
        strength=draw(quantized_unit_floats()),
        verification=draw(tokens()),
        provenance_class=draw(provenance_classes()),
    )


@st.composite
def evidence_records(draw: st.DrawFn) -> EvidenceRecord:
    """Return one citation into a versioned dataset."""
    return EvidenceRecord(
        evidence_record_id=draw(tokens()),
        dataset_version=draw(tokens()),
        source_locator=draw(tokens()),
        source_timezone=draw(st.none() | tokens()),
    )


@st.composite
def lifecycles(draw: st.DrawFn) -> Lifecycle:
    """Return a declared state space whose transitions stay inside it."""
    names = tuple(sorted(draw(st.lists(tokens(), min_size=1, max_size=4, unique=True))))
    transitions = tuple(
        sorted(
            draw(
                st.lists(
                    st.tuples(st.sampled_from(names), st.sampled_from(names)),
                    max_size=4,
                    unique=True,
                )
            )
        )
    )
    return Lifecycle(
        state_names=names,
        legal_transitions=transitions,
        provenance_class=ProvenanceClass.ASSUMED,
    )


@st.composite
def entities(draw: st.DrawFn) -> Entity:
    """Return an entity whose identifier agrees with its own address recipe."""
    ontology_hash, entity_type = draw(tokens()), draw(tokens())
    natural_key = draw(tokens())
    return Entity(
        entity_id=Entity.address(ontology_hash, entity_type, natural_key),
        entity_type=entity_type,
        natural_key=natural_key,
        attributes=tuple(
            sorted(
                draw(
                    st.lists(
                        st.tuples(tokens(), tokens()),
                        max_size=3,
                        unique_by=lambda pair: pair[0],
                    )
                )
            )
        ),
        lifecycle=draw(lifecycles()),
        provenance_class=draw(provenance_classes()),
        evidence_record_ids=tuple(
            sorted(draw(st.lists(tokens(), min_size=1, max_size=2, unique=True)))
        ),
    )


@st.composite
def events(
    draw: st.DrawFn,
    occurred_at: TimeInterval | None = None,
    event_id: str | None = None,
) -> Event:
    """Return an event, optionally pinned to a supplied interval and identifier.

    Pinning the interval matters for the LAW-TIME tests, which need two events whose
    intervals stand in a chosen relation rather than a random one. Pinning the identifier
    matters because a generated pair can collide, and an edge from an event to itself is
    refused -- correctly, but for a reason unrelated to the property under test.
    """
    interval = occurred_at if occurred_at is not None else draw(intervals())
    citations = tuple(sorted(draw(st.lists(tokens(), min_size=1, max_size=3, unique=True))))
    return Event(
        event_id=event_id if event_id is not None else draw(tokens()),
        event_type=draw(tokens()),
        occurred_at=interval,
        trigger=draw(st.none() | tokens()),
        source_entity_ids=tuple(sorted(draw(st.lists(tokens(), max_size=2, unique=True)))),
        target_entity_ids=tuple(sorted(draw(st.lists(tokens(), max_size=2, unique=True)))),
        changed_attributes=tuple(
            sorted(
                draw(
                    st.lists(
                        st.tuples(tokens(), tokens()),
                        max_size=2,
                        unique_by=lambda pair: pair[0],
                    )
                )
            )
        ),
        metadata=(),
        provenance_class=draw(provenance_classes()),
        confidence=draw(confidence_vectors()),
        is_actionable=draw(st.booleans()),
        source_record_ref=draw(st.sampled_from(citations)),
        evidence_record_ids=citations,
    )


@st.composite
def states(draw: st.DrawFn) -> State:
    """Return a state whose identifier agrees with its own address recipe."""
    entity_id, state_name = draw(tokens()), draw(tokens())
    held_over = draw(intervals())
    return State(
        state_id=State.address(entity_id, state_name, held_over),
        entity_id=entity_id,
        state_name=state_name,
        held_over=held_over,
        derived_from_event_id=draw(tokens()),
        provenance_class=draw(provenance_classes()),
        evidence_record_ids=tuple(
            sorted(draw(st.lists(tokens(), min_size=1, max_size=2, unique=True)))
        ),
    )


@st.composite
def transitions(draw: st.DrawFn) -> Transition:
    """Return a transition whose identifier agrees with its own address recipe."""
    from_state_id, to_state_id = draw(tokens()), draw(tokens())
    causing_event_id = draw(tokens())
    return Transition(
        transition_id=Transition.address(from_state_id, to_state_id, causing_event_id),
        from_state_id=from_state_id,
        to_state_id=to_state_id,
        causing_event_id=causing_event_id,
        provenance_class=draw(provenance_classes()),
    )


@st.composite
def relationships(draw: st.DrawFn) -> Relationship:
    """Return a structural, non-causal edge between two entities."""
    return Relationship(
        relationship_id=draw(tokens()),
        relationship_type=draw(tokens()),
        source_entity_id=draw(tokens()),
        target_entity_id=draw(tokens()),
        valid_over=draw(intervals()),
        provenance_class=draw(provenance_classes()),
        evidence_record_ids=tuple(
            sorted(draw(st.lists(tokens(), min_size=1, max_size=2, unique=True)))
        ),
    )


@st.composite
def edge_payloads(draw: st.DrawFn) -> CausalEdgePayload:
    """Return one payload from each branch of the taxonomy."""
    kind = draw(st.sampled_from(list(CausalEdgeKind)))
    if kind is CausalEdgeKind.DIRECT:
        return DirectCause()
    if kind is CausalEdgeKind.CONDITIONAL:
        return ConditionalCause(
            condition_expression=draw(tokens()), condition_holds=draw(st.booleans())
        )
    if kind is CausalEdgeKind.CONTRIBUTING:
        return ContributingCause(
            joint_cause_group_id=draw(tokens()),
            co_cause_event_ids=tuple(
                sorted(draw(st.lists(tokens(), min_size=1, max_size=3, unique=True)))
            ),
        )
    if kind is CausalEdgeKind.AMPLIFYING:
        return AmplifyingCause(
            magnitude_multiplier=draw(
                st.floats(min_value=1.000001, max_value=10.0).map(
                    lambda value: round(value, FLOAT_QUANTIZATION_PLACES)
                )
            )
        )
    return InhibitingCause(
        magnitude_multiplier=draw(
            st.floats(min_value=0.0, max_value=0.999999).map(
                lambda value: round(value, FLOAT_QUANTIZATION_PLACES)
            )
        )
    )


@st.composite
def causal_edges(draw: st.DrawFn) -> CausalEdge:
    """Return an edge built through `between`, the only LAW-TIME-checking constructor.

    The cause is pinned strictly before the effect so the pair is always admissible; the
    rejected pairings are exercised deliberately in `tests/law/`.
    """
    cause = draw(
        events(
            occurred_at=TimeInterval(
                t_earliest=EARLIEST_GENERATED,
                t_latest=EARLIEST_GENERATED,
                precision=Precision.EXACT,
                provenance=ProvenanceClass.OBSERVED,
                source=draw(tokens()),
            ),
            event_id="evt:cause",
        )
    )
    effect = draw(
        events(
            occurred_at=TimeInterval(
                t_earliest=LATEST_GENERATED,
                t_latest=LATEST_GENERATED,
                precision=Precision.EXACT,
                provenance=ProvenanceClass.OBSERVED,
                source=draw(tokens()),
            ),
            event_id="evt:effect",
        )
    )
    return CausalEdge.between(
        source_event=cause,
        target_event=effect,
        payload=draw(edge_payloads()),
        confidence=draw(confidence_vectors()),
        evidence=tuple(draw(st.lists(evidence_items(), min_size=1, max_size=2))),
        propagation_weight=draw(quantized_unit_floats()),
        provenance_class=draw(
            st.sampled_from(
                [
                    ProvenanceClass.INFERRED,
                    ProvenanceClass.STATISTICAL,
                    ProvenanceClass.ASSUMED,
                    ProvenanceClass.SIMULATED,
                ]
            )
        ),
        run_id=draw(tokens()),
    )
