"""Every shipped pack loads, and says the same thing twice.

These are the packs the distribution ships. If one of them stops loading, the engine has no
domain at all -- so this is the first test in the module and the cheapest one to read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from causalog.ontology_runtime import PACK_DOCUMENT_NAME, PACK_SCHEMA_VERSION, load_pack
from causalog.ontology_runtime.diagnostics import Severity
from tests.ontology_packs import discover_packs

SHIPPED_PACKS = discover_packs()


def test_discovery_finds_the_packs_the_repository_ships() -> None:
    """A glob that found nothing would parameterise nothing, and nothing reports as green.

    Every other test in this module is parameterised over `SHIPPED_PACKS`, so this is the
    one assertion that has to name packs literally. It is a floor, not an inventory: adding
    a domain must not require editing it.
    """
    assert {"_base", "dataco", "hospital"} <= set(SHIPPED_PACKS)


@pytest.mark.parametrize("pack_id", SHIPPED_PACKS)
def test_shipped_pack_loads_without_errors(packs_root: Path, pack_id: str) -> None:
    loaded = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME)

    assert loaded.pack.pack_id == pack_id
    assert loaded.pack.pack_schema_version == PACK_SCHEMA_VERSION
    assert not [item for item in loaded.diagnostics if item.severity is Severity.ERROR]


@pytest.mark.parametrize("pack_id", SHIPPED_PACKS)
def test_every_pack_reports_the_check_it_could_not_run(packs_root: Path, pack_id: str) -> None:
    """No rule pack exists yet, so rule coverage is UNCHECKED and must say so.

    The whole point of the `NOT_RUNNABLE` severity: a check that cannot run must never be
    silently skipped, because a skipped check is indistinguishable from a passing one
    (DEF-0001, OQ-014). When rule packs land, this assertion is what forces someone to
    notice that the check can now actually run.
    """
    loaded = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME)

    codes = {item.code for item in loaded.unchecked}
    assert "ONT-N-RULE-COVERAGE" in codes


def test_supplying_a_rule_pack_turns_the_unchecked_check_into_a_real_one(
    packs_root: Path,
) -> None:
    loaded = load_pack(
        packs_root / "hospital" / PACK_DOCUMENT_NAME,
        produced_event_types=["ADMITTED"],
    )

    assert not loaded.unchecked
    uncovered = {
        item.path.split(".")[-1]
        for item in loaded.warnings
        if item.code == "ONT-W-NO-PRODUCING-RULE"
    }
    assert "ADMITTED" not in uncovered
    assert "TRIAGED" in uncovered


@pytest.mark.parametrize("pack_id", SHIPPED_PACKS)
def test_loading_twice_yields_the_same_hash(packs_root: Path, pack_id: str) -> None:
    path = packs_root / pack_id / PACK_DOCUMENT_NAME

    assert load_pack(path).ontology_hash == load_pack(path).ontology_hash


def test_the_shipped_packs_have_distinct_hashes(packs_root: Path) -> None:
    """Two different domains must never address to one ontology.

    They would collide in `run_id`, and two runs over unrelated domains would then be
    reported as the same Run (ADR-0013).
    """
    hashes = {
        pack_id: load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME).ontology_hash
        for pack_id in SHIPPED_PACKS
    }

    assert len(set(hashes.values())) == len(SHIPPED_PACKS)
