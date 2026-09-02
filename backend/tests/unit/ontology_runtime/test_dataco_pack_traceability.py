"""The DataCo pack's constraints: every field traces, and no derived event pretends.

Two constraints from the module brief, made mechanical:

  * **Every field traces to a real column, or is explicitly marked.** An attribute declaring
    `origin: SOURCE_COLUMN` must name a column in `columns.manifest.yaml`. Anything else
    must be DERIVED or ASSUMED and must say what it was derived from or assumed.
  * **A derived event never masquerades as an observed one** (ADR-0029).

As of 2026-08-30 the manifest is VERIFIED against the real file: module 1 read it, pinned
it by hash in `datasets/dataco.pin.json`, and compared the two headers. This file asserts
that the claim is backed by a pin that exists and agrees -- a manifest that merely says
VERIFIED would be asserting its own correctness.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from causalog.core.provenance import ProvenanceClass
from causalog.ontology_runtime import PACK_DOCUMENT_NAME, ResolvedPack, load_pack
from causalog.ontology_runtime.dsl import AttributeOrigin, AttributeSpec, ObservationMode
from causalog.persistence.sources.pin import read_pin


@pytest.fixture(scope="module")
def manifest(packs_root: Path) -> dict[str, Any]:
    text = (packs_root / "dataco" / "columns.manifest.yaml").read_text(encoding="utf-8")
    loaded: dict[str, Any] = yaml.safe_load(text)
    return loaded


@pytest.fixture(scope="module")
def dataco(packs_root: Path) -> ResolvedPack:
    return load_pack(packs_root / "dataco" / PACK_DOCUMENT_NAME).pack


def _every_attribute(pack: ResolvedPack) -> Iterator[tuple[str, AttributeSpec]]:
    for entity_type in pack.entity_types:
        for attribute in entity_type.attributes:
            yield f"entity_types.{entity_type.id}.{attribute.name}", attribute
    for event_type in pack.event_types:
        for attribute in event_type.required_attributes:
            yield f"event_types.{event_type.id}.{attribute.name}", attribute


def test_every_source_column_attribute_names_a_manifest_column(
    dataco: ResolvedPack, manifest: dict[str, Any]
) -> None:
    columns = set(manifest["columns"])
    unknown = [
        f"{where} -> {attribute.source_column!r}"
        for where, attribute in _every_attribute(dataco)
        if attribute.origin is AttributeOrigin.SOURCE_COLUMN
        and attribute.source_column not in columns
    ]

    assert not unknown, "attributes naming a column the manifest does not list: " + "; ".join(
        unknown
    )


def test_every_non_source_attribute_states_why(dataco: ResolvedPack) -> None:
    for where, attribute in _every_attribute(dataco):
        if attribute.origin is AttributeOrigin.DERIVED:
            assert attribute.derivation_basis, f"{where} is DERIVED and states no basis"
        elif attribute.origin is AttributeOrigin.ASSUMED:
            assert attribute.assumption, f"{where} is ASSUMED and states no assumption"


def test_the_pack_uses_at_least_one_of_each_origin(dataco: ResolvedPack) -> None:
    """A pack that never marks anything DERIVED is not obviously honest; it may be lazy."""
    origins = {attribute.origin for _, attribute in _every_attribute(dataco)}

    assert AttributeOrigin.SOURCE_COLUMN in origins
    assert AttributeOrigin.DERIVED in origins


def test_derived_event_types_declare_a_basis_and_a_confidence(dataco: ResolvedPack) -> None:
    for event_type in dataco.event_types:
        if event_type.observation is not ObservationMode.DERIVED:
            continue
        assert event_type.derivation is not None, f"{event_type.id} is DERIVED with no basis"
        assert event_type.derivation.basis.strip()
        assert event_type.derivation.default_confidence.components


def test_no_derived_event_type_claims_observed_provenance(dataco: ResolvedPack) -> None:
    """ADR-0029, LAW-PROVENANCE. The single most consequential rule in this pack."""
    offenders = [
        event_type.id
        for event_type in dataco.event_types
        if event_type.observation is ObservationMode.DERIVED
        and event_type.provenance_class is ProvenanceClass.OBSERVED
    ]

    assert not offenders


def test_the_derived_share_is_declared_not_accidental(dataco: ResolvedPack) -> None:
    """DataCo logs one occurrence and implies the rest. Pin the ratio, not just the rule.

    If a future edit quietly reclassified a derived event as observed, the rule above would
    still pass for every *other* event type. This assertion is what notices.
    """
    observed = [
        event_type.id
        for event_type in dataco.event_types
        if event_type.observation is ObservationMode.OBSERVED
    ]

    assert observed == ["ORDER_PLACED"]


def test_actionability_is_always_assumed(dataco: ResolvedPack) -> None:
    """Risk R-15: nothing in any dataset establishes that an operator can act."""
    for event_type in dataco.event_types:
        assert event_type.actionability.provenance_class is ProvenanceClass.ASSUMED


def test_actionable_event_types_carry_a_cost_class(dataco: ResolvedPack) -> None:
    """Intervention ranking multiplies impact by cost; an absent cost would rank free."""
    for event_type in dataco.event_types:
        if event_type.actionability.actionable:
            assert event_type.actionability.cost_class is not None


def test_external_event_types_are_declared_and_unpopulated(dataco: ResolvedPack) -> None:
    assert dataco.external_event_types
    for external in dataco.external_event_types:
        assert external.status.value == "DECLARED_UNPOPULATED"
        assert external.note.strip()


def test_the_manifest_is_verified_against_a_pin_that_exists(
    manifest: dict[str, Any], packs_root: Path
) -> None:
    """Module 1 flipped this to VERIFIED on 2026-08-30, and VERIFIED has to mean something.

    Until then this test asserted the opposite -- that the manifest still said
    UNVERIFIED_AGAINST_LOCAL_FILE -- because a green traceability check meant "traces to the
    manifest", not "traces to the file", and something had to keep the two apart.

    The assertion is inverted rather than deleted, and it is STRONGER than the flip it
    permits: `verified_by` must name a `dataset_version` that a real, readable pin file
    carries. A manifest that merely says VERIFIED is a manifest asserting its own
    correctness, which is the DEF-0001 shape in one line of YAML.
    """
    assert manifest["verification"] == "VERIFIED"
    pinned_version = manifest["verified_by"]
    assert pinned_version, "VERIFIED with no `verified_by` names no evidence"

    pin_path = packs_root.parent.parent / "datasets" / "dataco.pin.json"
    assert pin_path.is_file(), (
        f"the manifest claims verification against {pinned_version!r} but there is no pin "
        f"at {pin_path}. Re-run `make import` (scripts/import_dataset.py)."
    )
    # Read through the real reader, not `json.load`. The pin is canonical JSON carrying a
    # schema envelope, and a test that reached past that envelope into raw keys would keep
    # passing after the pin's shape changed underneath it.
    pin = read_pin(pin_path)
    assert pin.dataset_version == pinned_version
    assert pin.content_sha256, "a pin without a content hash pins nothing"
    assert sorted(pin.header) == sorted(manifest["columns"]), (
        "the pinned file's header and the manifest's column list disagree, so one of them "
        "is not describing the file that was read"
    )
