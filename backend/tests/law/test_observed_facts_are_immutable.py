"""Observed facts are immutable (LAW-PROVENANCE, ADR-0004, ADR-0005).

"Inferred results never overwrite observed facts" is only a guarantee if it is impossible
rather than discouraged. Three layers hold it up and each has a gap the next one closes:
the types are frozen, so assignment fails; `revise` refuses an `OBSERVED` artifact, so the
copy path cannot route around the freeze; and run scoping (ADR-0013) means an inference
module addresses a different store entirely.

The third layer is enforced at the persistence boundary and is out of scope here. These
tests cover the two that live in `core/`, and the run-scoping test belongs with the
persistence adapters when they exist.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from causalog.core.aggregation import aggregate
from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.immutability import revise
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.temporal import Precision, TimeInterval
from causalog.core.types import (
    ConfidenceComponent,
    ConfidenceVector,
    Entity,
    Event,
    EvidenceRecord,
    Lifecycle,
    Relationship,
    State,
    Transition,
)

pytestmark = pytest.mark.law

INTERVAL = TimeInterval(
    t_earliest=datetime(2026, 1, 1, tzinfo=UTC),
    t_latest=datetime(2026, 1, 1, tzinfo=UTC),
    precision=Precision.EXACT,
    provenance=ProvenanceClass.OBSERVED,
    source="test-fixture",
)

CONFIDENCE = aggregate(
    [
        ConfidenceComponent(
            component_name="rule_support",
            value=0.9,
            provenance_class=ProvenanceClass.OBSERVED,
            evidence_record_ids=("evd:1",),
        )
    ]
)

LIFECYCLE = Lifecycle(
    state_names=("ALPHA", "BETA"),
    legal_transitions=(("ALPHA", "BETA"),),
    provenance_class=ProvenanceClass.ASSUMED,
)


def _observed_event() -> Event:
    return Event(
        event_id="evt:observed",
        event_type="SYNTHETIC",
        occurred_at=INTERVAL,
        trigger=None,
        source_entity_ids=(),
        target_entity_ids=(),
        changed_attributes=(),
        metadata=(),
        provenance_class=ProvenanceClass.OBSERVED,
        confidence=CONFIDENCE,
        is_actionable=False,
        source_record_ref="evd:1",
        evidence_record_ids=("evd:1",),
    )


def _inferred_event() -> Event:
    """An event carrying INFERRED provenance, built directly.

    It cannot be obtained by revising the observed one -- `revise` refuses that, which is
    the point of `test_an_observed_fact_cannot_be_reclassified_by_revision` below.
    """
    return Event(
        event_id="evt:inferred",
        event_type="SYNTHETIC",
        occurred_at=INTERVAL,
        trigger=None,
        source_entity_ids=(),
        target_entity_ids=(),
        changed_attributes=(),
        metadata=(),
        provenance_class=ProvenanceClass.INFERRED,
        confidence=CONFIDENCE,
        is_actionable=False,
        source_record_ref="evd:1",
        evidence_record_ids=("evd:1",),
    )


def _observed_entity() -> Entity:
    return Entity(
        entity_id=Entity.address("hash", "SYNTHETIC", "key-1"),
        entity_type="SYNTHETIC",
        natural_key="key-1",
        attributes=(),
        lifecycle=LIFECYCLE,
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=("evd:1",),
    )


FROZEN_ARTIFACTS: list[BaseModel] = [
    INTERVAL,
    CONFIDENCE,
    LIFECYCLE,
    _observed_event(),
    _observed_entity(),
    EvidenceRecord(
        evidence_record_id="evd:1",
        dataset_version="v1",
        source_locator="locator-1",
        source_timezone=None,
    ),
    State(
        state_id=State.address("ent:1", "ALPHA", INTERVAL),
        entity_id="ent:1",
        state_name="ALPHA",
        held_over=INTERVAL,
        derived_from_event_id="evt:observed",
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=("evd:1",),
    ),
    Transition(
        transition_id=Transition.address("sta:1", "sta:2", "evt:observed"),
        from_state_id="sta:1",
        to_state_id="sta:2",
        causing_event_id="evt:observed",
        provenance_class=ProvenanceClass.OBSERVED,
    ),
    Relationship(
        relationship_id="rel:1",
        relationship_type="BELONGS_TO",
        source_entity_id="ent:1",
        target_entity_id="ent:2",
        valid_over=INTERVAL,
        provenance_class=ProvenanceClass.OBSERVED,
        evidence_record_ids=("evd:1",),
    ),
    RunKey(
        dataset_version="v1",
        ontology_hash="hash",
        rule_pack_version="rp1",
        engine_version="0.1.0",
        seed=0,
    ),
    OutputEnvelope(
        run_id="run:0000000000000000",
        ontology_version="1.0.0",
        ontology_hash="hash",
        dataset_version="v1",
        rule_pack_version="rp1",
        engine_version="0.1.0",
        graph_projection_version="1",
        seed=0,
        execution_id="exec-1",
    ),
]


# ---------------------------------------------------------------------------------------
# layer 1: the types are frozen
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", FROZEN_ARTIFACTS, ids=lambda artifact: type(artifact).__name__)
def test_attribute_assignment_is_refused(artifact: BaseModel) -> None:
    """Every canonical artifact is frozen, whatever its provenance."""
    field_name = next(iter(type(artifact).model_fields))
    with pytest.raises(ValidationError):
        setattr(artifact, field_name, "mutated")


@pytest.mark.parametrize("artifact", FROZEN_ARTIFACTS, ids=lambda artifact: type(artifact).__name__)
def test_unknown_fields_are_refused(artifact: BaseModel) -> None:
    """`extra="forbid"`: a typo'd field name is a defect, never a silently stored extra."""
    assert type(artifact).model_config["extra"] == "forbid"
    assert type(artifact).model_config["frozen"] is True


# ---------------------------------------------------------------------------------------
# layer 2: the copy path cannot route around the freeze
# ---------------------------------------------------------------------------------------


def test_revising_an_observed_event_raises() -> None:
    """The copy path is guarded as well as the assignment path.

    The gap a freeze alone would leave: producing a modified copy is how a frozen
    object is "changed", so the copy path needs the same guard.
    """
    with pytest.raises(LawViolationError):
        revise(_observed_event(), event_type="REWRITTEN")


def test_revising_an_observed_entity_raises() -> None:
    """The guard is on the provenance class, not on one type."""
    with pytest.raises(LawViolationError):
        revise(_observed_entity(), natural_key="rewritten")


def test_the_refusal_names_the_law() -> None:
    """An operator reading the log must be able to tell this from a validation slip."""
    with pytest.raises(LawViolationError) as raised:
        revise(_observed_event(), event_type="REWRITTEN")
    assert "LAW-PROVENANCE" in str(raised.value)


def test_an_observed_fact_cannot_be_reclassified_by_revision() -> None:
    """The sharpest form of the guarantee.

    Downgrading `provenance_class` would be the obvious way around the refusal: relabel the
    observation as inferred, then revise it freely. The guard reads the provenance of the
    artifact it was handed, so the first step already fails and there is no second step.
    """
    with pytest.raises(LawViolationError):
        revise(_observed_event(), provenance_class=ProvenanceClass.INFERRED)


def test_a_non_observed_artifact_may_be_revised_into_a_new_version() -> None:
    """Revision still works where the law permits it.

    The law must not be satisfied by forbidding all revision: an inferred artifact is
    versionable, and the result is a new object rather than a mutated one.
    """
    inferred = _inferred_event()
    revised = revise(inferred, event_type="REVISED")
    assert revised.event_type == "REVISED"
    assert inferred.event_type == "SYNTHETIC"
    assert revised is not inferred


def test_a_revision_is_revalidated_rather_than_copied_blindly() -> None:
    """A revision must not be able to reach a state the constructor would have refused."""
    with pytest.raises(ContractViolationError):
        revise(_inferred_event(), source_record_ref="evd:not-in-the-citations")


def test_revising_an_undeclared_field_is_refused() -> None:
    """An unknown field would be dropped silently and the change would appear applied."""
    with pytest.raises(ContractViolationError):
        revise(_inferred_event(), no_such_field="value")


def test_an_empty_revision_is_refused() -> None:
    """A revision that changes nothing is a defect, not a copy."""
    with pytest.raises(ContractViolationError):
        revise(_inferred_event())


# ---------------------------------------------------------------------------------------
# confidence is never a bare float (LAW-EVIDENCE)
# ---------------------------------------------------------------------------------------


def test_event_confidence_is_a_decomposition_not_a_float() -> None:
    """Confidence on an Event is a vector, not a scalar.

    LAW-EVIDENCE: "A bare float is a defect." It holds on the event, not only on the
    edge -- prd.md §20 put a scalar `Confidence` on Event, and OQ-005 recorded the
    conflict; this is the resolution made structural.
    """
    annotation = Event.model_fields["confidence"].annotation
    assert annotation is ConfidenceVector
    assert not any(field.annotation is float for field in Event.model_fields.values())
