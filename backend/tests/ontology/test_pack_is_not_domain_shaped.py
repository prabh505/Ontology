"""The DSL is not secretly shaped like logistics.

`docs/architecture.md` §1.5 states the residual honestly: the LAW-DOMAIN lint catches
vocabulary and cannot catch a reasoning package branching on a data *value*. The planned
cover is an ontology swap. This file is the part of that cover which can exist before a
pipeline does: it asserts that a deliberately unrelated domain loads through the identical
code path, and that the loader names no domain concept anywhere in its source.

**What this does NOT prove**, stated so a green run is not mistaken for more than it is:
swapping the pack changes the engine's *output*. That needs a pipeline, and the obligation
in `docs/architecture.md` §8 for `tests/ontology/test_ontology_swap.py` remains open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from causalog.ontology_runtime import PACK_DOCUMENT_NAME, ResolvedPack, load_pack
from causalog.ontology_runtime.diagnostics import Severity

# The banned stems of LAW-DOMAIN (CONVENTIONS.md §6, ADR-0019), applied here to the loader's
# own source. `ontology_runtime` is in the lint's scope as of ADR-0026; this test is the
# pytest-side statement of the same rule, so a scope regression in the script is visible.
BANNED_STEMS = ("warehous", "shipment", "order", "carrier", "customer", "deliver", "inventor")

UNRELATED_PACKS = ("hospital",)


@pytest.mark.parametrize("pack_id", UNRELATED_PACKS)
def test_an_unrelated_domain_loads_with_no_engine_change(packs_root: Path, pack_id: str) -> None:
    """The same call, the same code, a domain with nothing in common with the first one."""
    logistics = load_pack(packs_root / "dataco" / PACK_DOCUMENT_NAME)
    unrelated = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME)

    for loaded in (logistics, unrelated):
        assert not [item for item in loaded.diagnostics if item.severity is Severity.ERROR]

    assert unrelated.pack.entity_types
    assert unrelated.pack.event_types
    assert unrelated.pack.process_definitions
    assert unrelated.pack.measurement_definitions
    assert logistics.ontology_hash != unrelated.ontology_hash


def test_the_two_packs_share_no_behavioural_vocabulary(packs_root: Path) -> None:
    """The two domains must have no occurrence, flow, or metric in common.

    Entity types are excluded from this assertion deliberately. Both domains genuinely have
    a DEPARTMENT, and that is a coincidence between two organizations rather than evidence
    that the DSL is carrying one domain's structure -- an organizational noun is not a
    supply-chain concept. What must not overlap is the behavioural vocabulary: what happens,
    in what sequence, and what is measured. `EXCUSED` names the coincidence rather than
    letting a broad assertion be quietly weakened to accommodate it.
    """
    excused = {"DEPARTMENT"}
    logistics = load_pack(packs_root / "dataco" / PACK_DOCUMENT_NAME).pack
    unrelated = load_pack(packs_root / "hospital" / PACK_DOCUMENT_NAME).pack

    def behavioural(pack: ResolvedPack) -> set[str]:
        return {
            *(item.id for item in pack.event_types),
            *(item.id for item in pack.relationship_types),
            *(item.id for item in pack.process_definitions),
            *(item.id for item in pack.measurement_definitions),
            *(item.id for item in pack.event_categories),
        }

    assert not behavioural(logistics) & behavioural(unrelated)

    shared_entities = {item.id for item in logistics.entity_types} & {
        item.id for item in unrelated.entity_types
    }
    assert (
        shared_entities <= excused
    ), f"entity types shared beyond the excused coincidence: {sorted(shared_entities - excused)}"


def test_both_packs_inherit_the_same_structural_base(packs_root: Path) -> None:
    """Ordinal cost and severity are engine concepts; entity and event types are not.

    Sharing the base is the positive half of the previous test: what the two domains have in
    common must be structure, and nothing else.
    """
    logistics = load_pack(packs_root / "dataco" / PACK_DOCUMENT_NAME).pack
    unrelated = load_pack(packs_root / "hospital" / PACK_DOCUMENT_NAME).pack

    assert logistics.lineage == unrelated.lineage == ("_base",)
    assert {item.id for item in logistics.cost_classes} == {
        item.id for item in unrelated.cost_classes
    }
    assert {item.id for item in logistics.severity_classes} == {
        item.id for item in unrelated.severity_classes
    }


@pytest.mark.law
def test_the_loader_names_no_domain_concept(runtime_source_root: Path) -> None:
    """LAW-DOMAIN, applied to the one package built to keep the domain out.

    A loader that named a domain concept would be the domain leaking in through the door
    that exists to stop it.
    """
    offences: list[str] = []
    for path in sorted(runtime_source_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        offences.extend(f"{path.name}: {stem!r}" for stem in BANNED_STEMS if stem in text)

    assert not offences, "domain vocabulary in ontology_runtime: " + "; ".join(offences)
