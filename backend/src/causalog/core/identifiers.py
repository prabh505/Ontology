"""Content-addressed identifier construction (`CONVENTIONS.md` §9).

Deterministic, content-addressed, sorted. No UUID4, no autoincrement, no
timestamp-as-identifier anywhere in the reasoning pipeline -- byte-identical reruns are
impossible otherwise.

    <type_prefix>:<sha256(canonical_payload)[:16]>

`canonical_payload` is a UTF-8 string with `|` separators, every collection sorted by its
canonical sort key, every float formatted per `CONVENTIONS.md` §11.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

__all__ = ["FLOAT_QUANTIZATION_PLACES", "PAYLOAD_SEPARATOR", "IdentifierPrefix", "digest"]

#: Every float is quantized to this many decimal places at every serialization boundary.
FLOAT_QUANTIZATION_PLACES: Final[int] = 6

#: The single admissible separator inside a canonical payload.
PAYLOAD_SEPARATOR: Final[str] = "|"

#: Characters of the hex digest retained in an identifier.
DIGEST_LENGTH: Final[int] = 16


class IdentifierPrefix(str, Enum):
    """The closed set of identifier prefixes."""

    EVENT = "evt"
    ENTITY = "ent"
    STATE = "sta"
    TRANSITION = "trn"
    CANDIDATE_EDGE = "edg"
    EVIDENCE_RECORD = "evd"
    SIMULATED_WORLD = "sim"
    RUN = "run"


def digest(prefix: IdentifierPrefix, canonical_payload: str) -> str:
    """Return `<prefix>:<sha256(canonical_payload)[:16]>`.

    Contract (draft -- see `CONTEXT.md` §6):
      * The caller is responsible for canonicalization; this function never sorts.
      * A collision on differing payloads is a `CRITICAL` defect, checked at insert by
        the persistence port, never retried here.
    """
    raise NotImplementedError("draft contract; implemented with module 3 (Entity Extractor)")
