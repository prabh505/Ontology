"""A resolved pack survives the canonical wire format with its identity intact.

The property that matters is the last one: `hash(pack) == hash(read(write(pack)))`. Without
it, a pack persisted with a run and read back later would address to a different ontology
than the one the run actually used, and every stored `run_id` would become unverifiable.

Reuses `core.serialization` rather than a second encoder. A module reaching for pydantic's
own `model_dump_json` gets output that looks correct and is not byte-stable
(`docs/contracts.md` §9); this test is where that would be caught for the ontology layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from causalog.core.errors import ContractViolationError
from causalog.core.serialization import from_canonical_json, to_canonical_json
from causalog.ontology_runtime import PACK_DOCUMENT_NAME, ResolvedPack, load_pack, ontology_hash
from tests.ontology_packs import discover_packs

PACKS = discover_packs()


@pytest.mark.parametrize("pack_id", PACKS)
def test_pack_round_trips_to_an_identical_model(packs_root: Path, pack_id: str) -> None:
    loaded = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME)

    restored = from_canonical_json(ResolvedPack, to_canonical_json(loaded.pack))

    assert restored == loaded.pack


@pytest.mark.parametrize("pack_id", PACKS)
def test_round_tripping_preserves_the_hash(packs_root: Path, pack_id: str) -> None:
    loaded = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME)

    restored = from_canonical_json(ResolvedPack, to_canonical_json(loaded.pack))

    assert ontology_hash(restored) == loaded.ontology_hash


@pytest.mark.determinism
@pytest.mark.parametrize("pack_id", PACKS)
def test_serializing_twice_yields_identical_bytes(packs_root: Path, pack_id: str) -> None:
    loaded = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME)

    assert to_canonical_json(loaded.pack) == to_canonical_json(loaded.pack)


@pytest.mark.parametrize("pack_id", PACKS)
def test_the_wire_form_carries_its_envelope(packs_root: Path, pack_id: str) -> None:
    """An artifact without its envelope cannot be verified and is a defect."""
    loaded = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME)

    text = to_canonical_json(loaded.pack)

    assert '"type":"ResolvedPack"' in text
    assert '"schema_version"' in text


def test_a_payload_missing_its_envelope_is_refused(packs_root: Path) -> None:
    loaded = load_pack(packs_root / "hospital" / PACK_DOCUMENT_NAME)
    text = to_canonical_json(loaded.pack)
    stripped = text[text.index('"payload":') + len('"payload":') : text.rindex(',"schema_version"')]

    with pytest.raises(ContractViolationError):
        from_canonical_json(ResolvedPack, stripped)


def test_deserialization_reruns_the_invariants(packs_root: Path) -> None:
    """A hand-edited payload cannot reintroduce a state the constructor would refuse.

    Here: an event type marked DERIVED with its derivation removed. The model validator that
    refuses it at construction must also refuse it on the way in from the wire, or a pack
    edited in storage could put a basis-free derived event into the engine.
    """
    loaded = load_pack(packs_root / "hospital" / PACK_DOCUMENT_NAME)
    text = to_canonical_json(loaded.pack)
    assert '"observation":"OBSERVED"' in text
    tampered = text.replace('"observation":"OBSERVED"', '"observation":"DERIVED"', 1)

    with pytest.raises(ContractViolationError):
        from_canonical_json(ResolvedPack, tampered)
