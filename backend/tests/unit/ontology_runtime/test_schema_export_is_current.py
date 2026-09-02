"""The published JSON Schema is what the models produce, and nothing else.

The pydantic models are normative (ADR-0026) and the schema file is generated from them.
Two descriptions of one contract that are free to disagree eventually do, and the
disagreement surfaces as a pack one validator accepts and the other rejects, with nobody
able to say which is right. This test is the thing that stops them diverging.
"""

from __future__ import annotations

import json
from pathlib import Path

from causalog.ontology_runtime.schema_export import SCHEMA_IDENTIFIER, render_schema

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = REPO_ROOT / "ontology" / "_schema" / "ontology.schema.json"


def test_the_published_schema_matches_the_models() -> None:
    assert SCHEMA_PATH.is_file()

    published = SCHEMA_PATH.read_text(encoding="utf-8")

    assert published == render_schema(), (
        "ontology/_schema/ontology.schema.json is stale. Regenerate it rather than "
        "hand-editing: python scripts/export_ontology_schema.py --write"
    )


def test_rendering_is_deterministic() -> None:
    assert render_schema() == render_schema()


def test_the_schema_is_addressable_and_well_formed() -> None:
    schema = json.loads(render_schema())

    assert schema["$id"] == SCHEMA_IDENTIFIER
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert "pack_schema_version" in schema["properties"]
    assert "$defs" in schema
