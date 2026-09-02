"""The dataset pin: everything needed to prove which bytes a run consumed.

`datasets/<dataset_id>.pin.json` is committed; the bytes it describes are not
(`datasets/README.md`). The pin is therefore the only durable statement of what was read,
and it is written to be checkable rather than trusted -- re-hashing the file and rebuilding
the pin from the same mapping and pack must reproduce it exactly.

**The pin carries no timestamp.** A `pinned_at` field would make the file differ between two
runs over identical inputs, which is the determinism guarantee failing in the one artifact
whose whole job is to make a run reproducible (`CONVENTIONS.md` §11). When it was written is
recoverable from git; what it describes is not recoverable from anywhere else.
"""

from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from causalog.core.errors import DataQualityError
from causalog.core.serialization import from_canonical_json, to_canonical_json

__all__ = ["DatasetPin", "read_pin", "write_pin"]


class DatasetPin(BaseModel):
    """A pinned source file, the mapping it was read through, and the resulting version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    dataset_version: str

    source_file: str
    source_url: str
    byte_count: int
    content_sha256: str
    row_count: int
    header: tuple[str, ...]

    encoding_chosen: str
    encoding_rejected: tuple[str, ...]
    delimiter: str

    mapping_id: str
    mapping_version: str
    mapping_hash: str

    ontology_pack: str
    ontology_version: str
    ontology_hash: str


def write_pin(path: Path, pin: DatasetPin) -> str:
    """Write the pin as canonical JSON and return the text written.

    Canonical rather than pretty: the file is compared byte-for-byte by the determinism
    test, and a formatter that sorts keys differently on another platform would make an
    identical run look like a changed one.
    """
    text = to_canonical_json(pin)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return text


def read_pin(path: Path) -> DatasetPin:
    """Read a pin back, revalidating every field.

    Raises:
        DataQualityError: if the file is absent or is not a well-formed pin.
    """
    if not path.is_file():
        raise DataQualityError(
            f"No dataset pin at {path}. A run consumes a pinned dataset; an unpinned file "
            "cannot be shown to be the file a previous conclusion was drawn from."
        )
    # Through `from_canonical_json`, matching `write_pin`. The canonical form carries a
    # schema envelope, so a raw `model_validate` sees `schema_version` and `type` as
    # unexpected fields and refuses a pin this module wrote itself.
    try:
        return from_canonical_json(DatasetPin, path.read_text(encoding="utf-8"))
    except ValidationError as failure:
        raise DataQualityError(
            f"Dataset pin at {path} is not a well-formed pin: {failure}"
        ) from failure
    except JSONDecodeError as failure:
        raise DataQualityError(f"Dataset pin at {path} is not valid JSON: {failure}") from failure
