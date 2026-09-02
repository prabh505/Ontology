"""The canonical serialization contract: stable, versioned, round-trippable.

`CONVENTIONS.md` §11 requires that identical inputs produce **byte-identical** outputs.
Pydantic's own JSON output is not sufficient for that on its own: float repr varies, key
sequence follows declaration rather than name, and there is no version stamp to tell a
reader which shape they are looking at. This module closes those three gaps.

The rules, all of which exist to make two runs comparable with `diff`:

  * **Keys are sorted.** Every mapping, at every depth, by key.
  * **Floats are quantized** to `FLOAT_QUANTIZATION_PLACES` through the one formatter in
    `causalog.core.identifiers`, so a value that differs only in the sixteenth decimal
    place does not read as a changed output.
  * **Instants are ISO-8601 with an explicit offset**, always UTC.
  * **Separators are fixed** and there is no trailing whitespace, so formatting can never
    account for a diff.
  * **The payload is versioned.** `to_canonical_json` wraps the artifact in an envelope
    carrying `schema_version` and the type name, so a stored artifact says what it is
    instead of relying on the reader to remember.

Round-trip is the test that keeps this honest: `from_canonical_json(to_canonical_json(x))`
must equal `x` for every canonical type, and re-serializing must reproduce the same bytes.

This module performs no I/O. It converts between objects and strings; opening a file or a
socket is the caller's business, and `core/` may not do it (forbidden edge F1).
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Final, TypeVar

from pydantic import BaseModel

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import canonical_instant, format_float

__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "canonical_form",
    "from_canonical_json",
    "to_canonical_json",
]

#: The version of the canonical wire shape itself, not of any one artifact's schema.
#: Bump on any change to how values are encoded -- key sequence, float resolution, instant
#: format, envelope shape. The per-artifact schema versions live in `CONTEXT.md` §7 and
#: move independently.
CANONICAL_SCHEMA_VERSION: Final[str] = "1.0.0"

_SCHEMA_VERSION_KEY: Final[str] = "schema_version"
_TYPE_KEY: Final[str] = "type"
_PAYLOAD_KEY: Final[str] = "payload"

ModelT = TypeVar("ModelT", bound=BaseModel)


def canonical_form(value: Any) -> Any:  # noqa: ANN401 -- total over arbitrary field values by design
    """Return a JSON-ready form of a value with every canonical rule applied.

    Recursive, and deliberately total over the types the canonical models can hold: a value
    this function does not recognise raises rather than falling through to `str()`, because
    a silent stringification is how an unnoticed type change turns into an unreproducible
    output.

    Raises:
        ContractViolationError: on a value of a type the canonical form does not cover.
    """
    if isinstance(value, BaseModel):
        return {key: canonical_form(item) for key, item in sorted(dict(value).items())}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        # Checked before int: bool is a subclass of int and would otherwise become 1/0.
        return value
    if isinstance(value, datetime):
        return canonical_instant(value)
    if isinstance(value, float):
        return format_float(value)
    if value is None or isinstance(value, int | str):
        return value
    if isinstance(value, dict):
        return {str(key): canonical_form(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple | list):
        return [canonical_form(item) for item in value]
    raise ContractViolationError(
        f"causalog.core.serialization.canonical_form received {type(value).__name__}, "
        "which has no canonical encoding; add one deliberately rather than letting the "
        "value be stringified (CONVENTIONS.md §11)."
    )


def to_canonical_json(artifact: BaseModel) -> str:
    """Serialize an artifact to its one canonical JSON text.

    Deterministic: the same artifact yields the same bytes in any process, on any platform.
    Floats are emitted as quantized **strings** rather than JSON numbers, because a JSON
    number is re-formatted by whichever parser reads it next and the byte-identity
    guarantee would not survive the round trip through another language's encoder.

    **Round-trip precondition.** Quantization to six decimal places is lossy, so
    `from_canonical_json(to_canonical_json(x)) == x` holds exactly when `x` already carries
    only quantized floats. That is the intended state of every artifact -- `CONVENTIONS.md`
    §11 quantizes at every boundary and `causalog.core.aggregation` quantizes on the way in
    -- and the round-trip test asserts it over quantized values for that reason. An
    artifact holding an unquantized float has already lost the byte-identity guarantee
    before it reaches this function; the loss is surfaced here rather than caused here.
    """
    envelope = {
        _PAYLOAD_KEY: canonical_form(artifact),
        _SCHEMA_VERSION_KEY: CANONICAL_SCHEMA_VERSION,
        _TYPE_KEY: type(artifact).__name__,
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def from_canonical_json(model_type: type[ModelT], text: str) -> ModelT:
    """Deserialize canonical JSON text back into an artifact.

    Every invariant runs again on the way in, so a hand-edited or downgraded payload cannot
    reintroduce a state the constructor would have refused. That is what makes the LAW-TIME
    guarantee hold for stored data and not only for freshly built objects.

    Raises:
        ContractViolationError: if the envelope is malformed, carries a different schema
            version, or names a different artifact type. None of the three is repaired: a
            payload that does not say what it is cannot be validated against anything.
    """
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError as error:
        raise ContractViolationError(
            "causalog.core.serialization.from_canonical_json received text that is not "
            f"JSON: {error.msg} at position {error.pos}."
        ) from error
    if not isinstance(envelope, dict) or _PAYLOAD_KEY not in envelope:
        raise ContractViolationError(
            "causalog.core.serialization.from_canonical_json received a payload with no "
            "canonical envelope; an artifact without its envelope cannot be verified and "
            "is a defect (CONVENTIONS.md §11)."
        )
    version = envelope.get(_SCHEMA_VERSION_KEY)
    if version != CANONICAL_SCHEMA_VERSION:
        raise ContractViolationError(
            f"causalog.core.serialization.from_canonical_json received schema version "
            f"{version!r}; this engine reads {CANONICAL_SCHEMA_VERSION!r}. A version "
            "mismatch is a migration, never a best-effort parse."
        )
    stated_type = envelope.get(_TYPE_KEY)
    if stated_type != model_type.__name__:
        raise ContractViolationError(
            f"causalog.core.serialization.from_canonical_json was asked for "
            f"{model_type.__name__} but the payload declares {stated_type!r}."
        )
    return model_type.model_validate(envelope[_PAYLOAD_KEY])
