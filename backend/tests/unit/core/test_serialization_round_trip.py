"""Canonical serialization is stable, versioned, and round-trips (`CONVENTIONS.md` §11).

Determinism is asserted end to end by `scripts/check_determinism.py`, which diffs two runs
byte for byte. That gate can only be trusted if the encoding underneath it is itself
byte-stable, which is what these properties pin down.

The failure they guard against is quiet: an encoder whose key sequence follows field
declaration, or whose float repr varies by platform, produces a diff on every rerun. The
gate then reports a determinism failure whose cause is the gate's own encoder, and the real
signal is lost in the noise.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel

from causalog.core.errors import ContractViolationError
from causalog.core.run import OutputEnvelope, Run, RunKey
from causalog.core.serialization import (
    CANONICAL_SCHEMA_VERSION,
    from_canonical_json,
    to_canonical_json,
)
from causalog.core.temporal import TimeInterval
from causalog.core.types import (
    CausalEdge,
    ConfidenceVector,
    Entity,
    Event,
    EvidenceItem,
    EvidenceRecord,
    Relationship,
    State,
    Transition,
)
from tests.unit.core.strategies import (
    causal_edges,
    confidence_vectors,
    entities,
    events,
    evidence_items,
    evidence_records,
    intervals,
    relationships,
    states,
    tokens,
    transitions,
)

pytestmark = pytest.mark.property

#: One strategy per canonical type, so a type added without a round-trip test is visible.
ROUND_TRIP_CASES = [
    (TimeInterval, intervals()),
    (ConfidenceVector, confidence_vectors()),
    (EvidenceItem, evidence_items()),
    (EvidenceRecord, evidence_records()),
    (Entity, entities()),
    (Event, events()),
    (State, states()),
    (Transition, transitions()),
    (Relationship, relationships()),
    (CausalEdge, causal_edges()),
]


@pytest.mark.parametrize(
    ("model_type", "strategy"), ROUND_TRIP_CASES, ids=lambda case: getattr(case, "__name__", "")
)
def test_every_canonical_type_round_trips(
    model_type: type[BaseModel], strategy: st.SearchStrategy[BaseModel]
) -> None:
    """Serialize, deserialize, and get the same artifact back."""

    @given(strategy)
    def check(artifact: BaseModel) -> None:
        assert from_canonical_json(model_type, to_canonical_json(artifact)) == artifact

    check()


@pytest.mark.parametrize(
    ("model_type", "strategy"), ROUND_TRIP_CASES, ids=lambda case: getattr(case, "__name__", "")
)
def test_serialization_is_byte_stable(
    model_type: type[BaseModel], strategy: st.SearchStrategy[BaseModel]
) -> None:
    """Encoding one artifact twice yields identical bytes.

    Repeated encoding of one artifact, and re-encoding after a round trip, agree byte
    for byte. Without this the determinism gate reports a diff on every rerun.
    """

    @given(strategy)
    def check(artifact: BaseModel) -> None:
        first = to_canonical_json(artifact)
        assert to_canonical_json(artifact) == first
        assert to_canonical_json(from_canonical_json(model_type, first)) == first

    check()


@given(events())
def test_the_envelope_states_the_schema_version_and_the_type(event: Event) -> None:
    """An artifact without its envelope cannot be verified and is a defect."""
    import json

    envelope = json.loads(to_canonical_json(event))
    assert envelope["schema_version"] == CANONICAL_SCHEMA_VERSION
    assert envelope["type"] == "Event"
    assert "payload" in envelope


@given(events())
def test_keys_are_sorted_at_every_depth(event: Event) -> None:
    """Sorted keys are what make two runs comparable with a plain text diff."""
    import json

    def assert_sorted(node: object) -> None:
        if isinstance(node, dict):
            assert list(node) == sorted(node)
            for value in node.values():
                assert_sorted(value)
        elif isinstance(node, list):
            for value in node:
                assert_sorted(value)

    assert_sorted(json.loads(to_canonical_json(event)))


@given(tokens())
def test_a_run_round_trips_with_its_key(seed_token: str) -> None:
    """`Run` re-derives its own identifier on the way in, so a tampered payload fails."""
    key = RunKey(
        dataset_version=seed_token,
        ontology_hash=seed_token,
        rule_pack_version=seed_token,
        engine_version="0.1.0",
        seed=0,
    )
    from datetime import UTC, datetime

    run = Run(run_id=key.address(), key=key, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert from_canonical_json(Run, to_canonical_json(run)) == run


def test_an_envelope_from_another_schema_version_is_refused() -> None:
    """A version mismatch is a migration, never a best-effort parse."""
    envelope = '{"payload":{},"schema_version":"0.0.1-from-the-future","type":"OutputEnvelope"}'
    with pytest.raises(ContractViolationError):
        from_canonical_json(OutputEnvelope, envelope)


def test_a_payload_declaring_another_type_is_refused() -> None:
    """Validating an Entity payload as an Event would half-succeed and mislead."""
    envelope = f'{{"payload":{{}},"schema_version":"{CANONICAL_SCHEMA_VERSION}","type":"Entity"}}'
    with pytest.raises(ContractViolationError):
        from_canonical_json(Event, envelope)


def test_text_without_an_envelope_is_refused() -> None:
    """A bare payload cannot say what it is, so it cannot be validated against anything."""
    with pytest.raises(ContractViolationError):
        from_canonical_json(Event, '{"event_id":"evt:1"}')


def test_text_that_is_not_json_is_refused() -> None:
    """A parse failure surfaces as a contract violation.

    Reported as a contract violation rather than a raw JSONDecodeError crossing the
    module boundary (`CONVENTIONS.md` §7).
    """
    with pytest.raises(ContractViolationError):
        from_canonical_json(Event, "not json at all")
