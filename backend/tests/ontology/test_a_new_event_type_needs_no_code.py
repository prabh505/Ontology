"""The claim `docs/architecture.md` §5.3 makes about module 4, tested rather than asserted.

> | 4 Event Generator | **none** -- reads `ontology.yaml` for event types and precision |

A table saying the reasoning-code diff is zero is a promise. This is the test: add an event
type to a pack, add one emission rule to its mapping, rerun the pipeline, and get new events
out. Nothing under `backend/src/` is touched, and the test PROVES that rather than asserting
it -- it hashes the whole distribution before and after and compares.

Domain-neutral by construction. Every identifier the new declaration needs -- the category,
the severity class, the anchor entity type, the attribute the condition reads -- is
DISCOVERED from the pack under test rather than written here, so this test says nothing
about any domain and would pass unchanged against a pack for a different one.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

import causalog
from causalog.extraction.entity_extractor import ExtractionResult
from causalog.extraction.event_generator import GenerationResult
from causalog.ingestion.schema_mapper import inspect_mapping
from causalog.ontology_runtime import load_pack
from extraction_harness import PACKS_ROOT, Harness, build_batches, envelope_for, harness_for
from fixtures.dataco.expansion import GROUND_TRUTH_DATASET_VERSION, rows
from ontology_packs import discover_packs

DISTRIBUTION = Path(causalog.__file__).resolve().parent

#: The identifier the added type is declared under. Deliberately not a word from any domain:
#: it names what the test does, which is to check that adding a type is enough.
ADDED_EVENT_TYPE = "SEAM_PROVED"


def _distribution_fingerprint() -> str:
    """Return one digest over every source file in the distribution."""
    digest = hashlib.sha256()
    for path in sorted(DISTRIBUTION.rglob("*.py")):
        digest.update(path.relative_to(DISTRIBUTION).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _copy_pack(pack_id: str, destination: Path) -> Path:
    target = destination / pack_id
    shutil.copytree(PACKS_ROOT / pack_id, target)
    for inherited in (PACKS_ROOT / "_base",):
        if inherited.exists():
            shutil.copytree(inherited, destination / inherited.name)
    return target


def _add_event_type(pack_path: Path, mapping_path: Path) -> tuple[str, str]:
    """Add one derived event type and one emission rule. Returns the anchor type and address.

    Everything is read from the RESOLVED pack: the first declared category and severity
    class, the anchor entity type of the first process definition, and the first attribute
    of that entity type the mapping actually supplies. Resolved rather than authored,
    because a pack inherits most of its vocabulary from the base it extends (ADR-0027) and
    reading the authored document alone would see only what this pack added. Writing any of
    these literally here would make the test a statement about one domain.
    """
    resolved = load_pack(pack_path).pack
    document = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))

    category = resolved.event_categories[0].id
    severity = resolved.severity_classes[0].id
    anchor = resolved.process_definitions[0].anchor_entity_type
    anchor_type = next(item for item in resolved.entity_types if item.id == anchor)
    supplied = {
        f"{binding.get('entity_type')}.{binding.get('attribute')}"
        for binding in mapping["column_bindings"]
    }
    attribute = next(
        item.name for item in anchor_type.attributes if f"{anchor}.{item.name}" in supplied
    )

    document["event_types"].append(
        {
            "id": ADDED_EVENT_TYPE,
            "description": "Added by a test to prove the seam carries a new type.",
            "category": category,
            "observation": "DERIVED",
            "provenance_class": "INFERRED",
            "participants": [{"role": "SUBJECT", "entity_type": anchor}],
            "actionability": {"actionable": False, "severity_class": severity},
            "derivation": {
                "basis": "Implied by the anchor being described at all.",
                "default_confidence": {
                    "aggregation": "weighted_mean_v1",
                    "provenance_class": "ASSUMED",
                    "components": [{"component_name": "rule_support", "value": 0.5}],
                },
            },
        }
    )
    mapping.setdefault("event_emissions", []).append(
        {
            "event_type": ADDED_EVENT_TYPE,
            "rationale": "Added by a test; fires wherever the anchor attribute is present.",
            "when": {
                "op": "IS_PRESENT",
                "operands": [{"op": "ATTRIBUTE", "concept": anchor, "attribute": attribute}],
            },
            "occurred_at": {
                "policy": "UNKNOWN",
                "derivation": "no column places this occurrence",
            },
        }
    )
    pack_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    mapping_path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return anchor, f"{anchor}.{attribute}"


def _harness_at(pack_path: Path, mapping_path: Path) -> Harness:
    loaded = load_pack(pack_path)
    mapping, coverage = inspect_mapping(mapping_path, loaded.pack)
    assert not coverage.errors, coverage.render()
    return Harness(loaded.pack, loaded.ontology_hash, mapping)


def _generate(harness: Harness) -> tuple[ExtractionResult, GenerationResult]:
    batches = build_batches(rows(), harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    extraction = harness.extract(batches, envelope)
    return extraction, harness.generate(batches, extraction, envelope)


def test_the_pack_directory_is_where_a_new_type_is_added(tmp_path: Path) -> None:
    """Adding an event type produces new events with no change under `backend/src/`."""
    before_fingerprint = _distribution_fingerprint()

    baseline_harness = harness_for()
    _baseline_extraction, baseline = _generate(baseline_harness)
    assert not baseline.of_type(ADDED_EVENT_TYPE)

    pack_directory = _copy_pack("dataco", tmp_path)
    anchor, _address = _add_event_type(
        pack_directory / "ontology.yaml", pack_directory / "mapping.yaml"
    )
    extended_harness = _harness_at(
        pack_directory / "ontology.yaml", pack_directory / "mapping.yaml"
    )
    extraction, extended = _generate(extended_harness)

    added = extended.of_type(ADDED_EVENT_TYPE)
    assert added, "the added event type produced nothing; the seam did not carry it"

    anchors = {entity.entity_id for entity in extraction.entities if entity.entity_type == anchor}
    assert len(added) == len(anchors), (
        "one occurrence per anchor was expected: the condition fires on every record and "
        "the participants name only the anchor, so records of one anchor corroborate one "
        "occurrence"
    )
    assert _distribution_fingerprint() == before_fingerprint, (
        "a file under backend/src changed while adding an event type. The seam's whole "
        "claim is that it does not (docs/architecture.md §5.3)."
    )


def test_the_added_type_changes_the_ontology_hash(tmp_path: Path) -> None:
    """A different vocabulary is a different run, and the identifier has to say so."""
    pack_directory = _copy_pack("dataco", tmp_path)
    before = load_pack(pack_directory / "ontology.yaml").ontology_hash
    _add_event_type(pack_directory / "ontology.yaml", pack_directory / "mapping.yaml")
    after = load_pack(pack_directory / "ontology.yaml").ontology_hash
    assert before != after


def test_the_added_type_re_addresses_nothing_that_already_existed(tmp_path: Path) -> None:
    """A new declaration must not silently rename the events that were already there.

    It DOES rename them, and that is correct: `ontology_hash` participates in every content
    address (`CONVENTIONS.md` §9), because the same occurrence under a different vocabulary
    is a different claim. What must hold is that the SET of pre-existing occurrences is
    unchanged apart from its identifiers -- nothing appeared, nothing vanished.
    """
    pack_directory = _copy_pack("dataco", tmp_path)
    baseline = _harness_at(pack_directory / "ontology.yaml", pack_directory / "mapping.yaml")
    _extraction, before = _generate(baseline)
    _add_event_type(pack_directory / "ontology.yaml", pack_directory / "mapping.yaml")
    extended = _harness_at(pack_directory / "ontology.yaml", pack_directory / "mapping.yaml")
    _extraction, after = _generate(extended)

    def shape(result: GenerationResult) -> list[tuple[str, str, int]]:
        return sorted(
            (event.event_type, event.occurred_at.precision.value, len(event.evidence_record_ids))
            for event in result.events
            if event.event_type != ADDED_EVENT_TYPE
        )

    assert shape(before) == shape(after)


@pytest.mark.parametrize("pack_id", discover_packs())
def test_every_shipped_pack_states_which_of_its_types_can_be_witnessed(pack_id: str) -> None:
    """A pack with no mapping still has to be assessable; one with a mapping must resolve.

    Pack discovery is derived from the pack directory (ADR-0030), so a domain added later is
    covered by this without anybody editing a list.
    """
    loaded = load_pack(PACKS_ROOT / pack_id / "ontology.yaml")
    mapping_path = PACKS_ROOT / pack_id / "mapping.yaml"
    if not mapping_path.exists():
        pytest.skip(f"pack '{pack_id}' ships no mapping; nothing binds it to a source yet")
    _mapping, coverage = inspect_mapping(mapping_path, loaded.pack)
    assert not coverage.errors, coverage.render()
    witnessed = {
        finding.subject
        for finding in coverage.warnings
        if finding.code == "MAP-W-EVENT-TYPE-NEVER-EMITTED"
    }
    declared = {f"event_types[{item.id}]" for item in loaded.pack.event_types}
    assert witnessed <= declared
