"""`mapping_hash`: the content address of a schema mapping.

The same recipe as `ontology_hash` (ADR-0028), through the same two functions, for the same
reason: two runs that interpreted the same bytes differently are different runs, and the
identifier has to say so. `mapping_hash` reaches `run_id` through `dataset_version` rather
than through `RunKey`, which is frozen -- see `compose_dataset_version`.

Nothing here re-implements hashing. A second hashing path would be a second answer to
"what is this mapping", free to disagree with the first.
"""

from __future__ import annotations

from causalog.core.identifiers import IdentifierPrefix, digest
from causalog.core.serialization import to_canonical_json
from causalog.ingestion.schema_mapper.dsl import SchemaMappingSpec

__all__ = ["mapping_hash"]


def mapping_hash(mapping: SchemaMappingSpec) -> str:
    """Return `map:<sha256(canonical_mapping)[:16]>`.

    Computed through `to_canonical_json`, so the hash is invariant to comments, indentation
    and key sequence in the YAML, and sensitive to every declared binding, transform,
    dropped column and rationale.
    """
    return digest(IdentifierPrefix.MAPPING, to_canonical_json(mapping))
