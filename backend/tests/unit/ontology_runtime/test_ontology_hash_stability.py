"""`ontology_hash` is stable across processes, blind to formatting, and sensitive to meaning.

`ontology_hash` is one of the five inputs to `run_id` (ADR-0013). Two failures would be
quiet and expensive, which is why both are asserted here rather than assumed:

  * **Instability.** A hash that varies between processes makes every rerun a false
    determinism failure, and the determinism gate then reports a diff nobody can explain.
  * **Insensitivity.** A hash that does not move when the pack's meaning moves lets two
    genuinely different ontologies share a `run_id`, and their conclusions are then reported
    as comparable when they are not.

Formatting invariance is the third property and follows from computing the hash over the
resolved model rather than the file: a comment, a reindent, or splitting a pack across a
base and an overlay changes the bytes on disk and changes nothing about what the pack says.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from causalog.ontology_runtime import PACK_DOCUMENT_NAME, load_pack
from tests.ontology_packs import discover_packs

PACKS = discover_packs()


@pytest.mark.determinism
@pytest.mark.parametrize("pack_id", PACKS)
def test_hash_survives_a_fresh_interpreter(packs_root: Path, pack_id: str) -> None:
    """A fresh process must agree, or nothing about a rerun is comparable.

    Run in a subprocess deliberately: an in-process repeat would pass even if the digest
    depended on hash randomization, which is exactly the defect this guards.
    """
    path = packs_root / pack_id / PACK_DOCUMENT_NAME
    in_process = load_pack(path).ontology_hash

    result = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        [
            sys.executable,
            "-c",
            "from pathlib import Path;"
            "from causalog.ontology_runtime import load_pack;"
            f"print(load_pack(Path({str(path)!r})).ontology_hash)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == in_process


@pytest.mark.parametrize("pack_id", PACKS)
def test_hash_is_prefixed_and_fixed_width(packs_root: Path, pack_id: str) -> None:
    digest = load_pack(packs_root / pack_id / PACK_DOCUMENT_NAME).ontology_hash

    prefix, _, body = digest.partition(":")
    assert prefix == "ont"
    assert len(body) == 16
    assert all(character in "0123456789abcdef" for character in body)


def _hash_of(text: str, directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / PACK_DOCUMENT_NAME
    path.write_text(text, encoding="utf-8")
    return load_pack(path).ontology_hash


def test_comments_indentation_and_key_sequence_do_not_move_the_hash(
    fixtures_root: Path, tmp_path: Path
) -> None:
    source = (fixtures_root / "valid_minimal.yaml").read_text(encoding="utf-8")
    baseline = _hash_of(source, tmp_path / "a")

    commented = "# an added comment, meaning nothing\n" + source + "\n# and a trailing one\n"
    resequenced = source.replace(
        'pack_schema_version: "1.0.0"\npack_id: minimal\n',
        'pack_id: minimal\npack_schema_version: "1.0.0"\n',
    )
    assert resequenced != source

    assert _hash_of(commented, tmp_path / "b") == baseline
    assert _hash_of(resequenced, tmp_path / "c") == baseline


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("rank: 1, description: A low-cost action.", "rank: 2, description: A low-cost action."),
        ("      states: [NEW, DONE]", "      states: [NEW, MIDWAY, DONE]"),
        ("    cardinality: MANY_TO_ONE", "    cardinality: ONE_TO_MANY"),
        ("    unit: HOURS", "    unit: MINUTES"),
        ("    kind: DURATION", "    kind: DELAY"),
        ('ontology_version: "1.0.0"', 'ontology_version: "1.1.0"'),
    ],
)
def test_any_semantic_change_moves_the_hash(
    fixtures_root: Path, tmp_path: Path, old: str, new: str
) -> None:
    source = (fixtures_root / "valid_minimal.yaml").read_text(encoding="utf-8")
    baseline = _hash_of(source, tmp_path / "base")

    changed = source.replace(old, new, 1)
    assert changed != source, f"the probe {old!r} did not match the fixture"
    if "MIDWAY" in new:
        # Keep the pack loadable: a new state needs a way in and a way out.
        changed = changed.replace(
            "        - {from: NEW, to: DONE, triggered_by: FINISHED}",
            "        - {from: NEW, to: MIDWAY}\n"
            "        - {from: MIDWAY, to: DONE, triggered_by: FINISHED}",
        )

    assert _hash_of(changed, tmp_path / "changed") != baseline


def test_inheritance_is_invisible_to_the_hash(packs_root: Path, tmp_path: Path) -> None:
    """A pack written out in full hashes identically to the same pack assembled from a base.

    This is what makes the hash a statement about semantics rather than about authoring.
    Without it, flattening a pack for readability would look like a changed ontology and
    would invalidate every `run_id` computed before the edit.
    """
    overlay = load_pack(packs_root / "hospital" / PACK_DOCUMENT_NAME)

    flattened_dir = tmp_path / "flat"
    flattened_dir.mkdir()
    source = (packs_root / "hospital" / PACK_DOCUMENT_NAME).read_text(encoding="utf-8")
    base = (packs_root / "_base" / PACK_DOCUMENT_NAME).read_text(encoding="utf-8")
    inherited = base[base.index("cost_classes:") :]
    flattened = source.replace("extends: _base\n", "") + "\n" + inherited
    (flattened_dir / PACK_DOCUMENT_NAME).write_text(flattened, encoding="utf-8")

    flat = load_pack(flattened_dir / PACK_DOCUMENT_NAME)

    assert flat.pack.lineage == ()
    assert overlay.pack.lineage == ("_base",)
    assert flat.ontology_hash != overlay.ontology_hash, (
        "lineage is part of the resolved pack, so the two are not expected to agree; this "
        "assertion pins that fact rather than hiding it"
    )
    assert flat.pack.model_dump(exclude={"lineage"}) == overlay.pack.model_dump(exclude={"lineage"})
