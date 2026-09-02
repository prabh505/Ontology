"""Generate the published JSON Schema from the DSL models.

The pydantic models in `dsl.py` are normative (ADR-0026); this module renders them as JSON
Schema so external tooling -- an editor, a CI linter, another language -- can validate a
pack without importing Python.

Generated, never hand-authored. A hand-authored schema beside a code validator is two
descriptions of one contract, free to disagree, and the disagreement surfaces as a pack that
one accepts and the other rejects. `scripts/export_ontology_schema.py --check` fails the
build if the published file is not what these models produce.
"""

from __future__ import annotations

import json
from typing import Any, Final

from causalog.ontology_runtime.dsl import PACK_SCHEMA_VERSION, DomainPack

__all__ = ["SCHEMA_IDENTIFIER", "render_schema"]

#: Stable identifier for the published schema. Versioned by the DSL, not by any pack.
SCHEMA_IDENTIFIER: Final[str] = (
    f"https://causalog.invalid/schema/domain-pack/{PACK_SCHEMA_VERSION}/ontology.schema.json"
)


def render_schema() -> str:
    """Return the published JSON Schema text: sorted keys, two-space indent, one newline.

    Deterministic in the same way `core.serialization` is deterministic, and for the same
    reason: a formatting difference must never read as a contract change in a diff.
    """
    schema: dict[str, Any] = DomainPack.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_IDENTIFIER
    schema["title"] = "CausaLog domain pack"
    schema["description"] = (
        "The declarative description of one domain (ADR-0026). Generated from "
        "causalog.ontology_runtime.dsl; edit the models, never this file."
    )
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
