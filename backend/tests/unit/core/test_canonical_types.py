"""The draft core contracts must hold the properties the Laws depend on.

These assert structure, not behaviour -- no module is implemented yet.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from causalog.core.provenance import WEAKEST_FIRST, ProvenanceClass
from causalog.core.run import OutputEnvelope, RunKey
from causalog.core.types import (
    ConfidenceVector,
    Entity,
    Event,
    EvidenceRecord,
    Relationship,
    State,
    Transition,
)

FROZEN_TYPES = [
    Entity,
    Event,
    State,
    Transition,
    Relationship,
    EvidenceRecord,
    ConfidenceVector,
    RunKey,
    OutputEnvelope,
]


@pytest.mark.parametrize("model", FROZEN_TYPES, ids=lambda m: m.__name__)
def test_canonical_types_are_immutable(model: type) -> None:
    """ADR-0004: a correction emits a new value; it never mutates an existing one."""
    assert model.model_config["frozen"] is True


@pytest.mark.parametrize("model", FROZEN_TYPES, ids=lambda m: m.__name__)
def test_canonical_types_reject_unknown_fields(model: type) -> None:
    """Validate on entry, not on use (`CONVENTIONS.md` §7)."""
    assert model.model_config["extra"] == "forbid"


@pytest.mark.parametrize(
    "model", [Entity, Event, State, Transition, Relationship], ids=lambda m: m.__name__
)
def test_every_assertion_carries_a_provenance_class(model: type) -> None:
    """LAW-PROVENANCE: the field is required on every assertion the system holds."""
    field = model.model_fields["provenance_class"]
    assert field.is_required()


def test_provenance_is_a_closed_set_of_five() -> None:
    assert {member.value for member in ProvenanceClass} == {
        "OBSERVED",
        "ASSUMED",
        "STATISTICAL",
        "INFERRED",
        "SIMULATED",
    }


def test_weakest_first_ranks_every_class_exactly_once() -> None:
    """Aggregation across mixed provenance takes the weakest class present (ADR-0005)."""
    assert len(WEAKEST_FIRST) == len(ProvenanceClass)
    assert set(WEAKEST_FIRST) == set(ProvenanceClass)
    assert WEAKEST_FIRST[-1] is ProvenanceClass.OBSERVED


def test_confidence_is_never_a_bare_float() -> None:
    """LAW-EVIDENCE: the components are part of the contract, not an optional extra."""
    assert ConfidenceVector.model_fields["components"].is_required()
    with pytest.raises(ValidationError):
        ConfidenceVector(scalar=0.9, provenance_class=ProvenanceClass.INFERRED)  # type: ignore[call-arg]


def test_run_key_carries_all_five_reproducibility_inputs() -> None:
    """ADR-0013: anything absent here is an input that can change output unnoticed."""
    assert set(RunKey.model_fields) == {
        "dataset_version",
        "ontology_hash",
        "rule_pack_version",
        "engine_version",
        "seed",
    }


def test_event_carries_ontology_declared_actionability() -> None:
    """ADR-0008: the flag lives on the Event so L6 never reads the ontology (edge F3)."""
    field = Event.model_fields["is_actionable"]
    assert field.is_required()


def test_trigger_is_optional_and_distinct_from_any_edge_field() -> None:
    """ADR-0020: a trigger is a property of one event, never a relation between two.

    If `trigger` ever becomes an identifier field pointing at another event, this test is
    the tripwire -- that shape is the rejected Option B, a causal claim wearing the costume
    of an observed fact.
    """
    assert "trigger" in Event.model_fields
    edge_shaped = {name for name in Event.model_fields if name.endswith(("_event_id", "_edge_id"))}
    assert edge_shaped == set(), f"Event holds edge-shaped fields: {edge_shaped}"


def test_output_envelope_carries_run_id_and_execution_id_separately() -> None:
    """The two identifiers mean different things (ADR-0013)."""
    fields = set(OutputEnvelope.model_fields)
    assert {"run_id", "execution_id"} <= fields
    assert "graph_projection_version" in fields
