"""Content-addressed identifier construction (`CONVENTIONS.md` §9).

Deterministic, content-addressed, sorted. No UUID4, no autoincrement, no
timestamp-as-identifier anywhere in the reasoning pipeline -- byte-identical reruns are
impossible otherwise.

    <type_prefix>:<sha256(canonical_payload)[:16]>

`canonical_payload` is a UTF-8 string with `|` separators, every collection sorted by its
canonical sort key, every float formatted per `CONVENTIONS.md` §11.

Why SHA-256 truncated to 16 hex characters
------------------------------------------
SHA-256 is in the standard library, is stable across interpreter versions and platforms,
and has no seed -- three properties a determinism guarantee needs and which `hash()` does
not have. Truncation to 16 hex characters keeps 64 bits. By the birthday bound a 64-bit
space reaches a one-in-a-million collision probability near six million distinct payloads
and an even chance near five billion, which is far above any plausible artifact count for
one dataset version. The truncation buys readable identifiers in logs, URLs, and Cypher.

A collision on *differing* payloads is a `CRITICAL` defect checked at insert by the
persistence port and never retried here (`CONVENTIONS.md` §9). Widening `DIGEST_LENGTH`
later changes every identifier in every store, so it is an `engine_version` bump and a
full re-derivation, never an in-place migration.

Reserved characters
-------------------
Three characters structure a payload: `|` between top-level fields, `,` between members of
a collection, `=` between the two halves of a pair. A leaf value may legitimately contain
any of them, so leaves are escaped rather than rejected -- an escape is injective, whereas
rejecting a character would make some admissible source values unrepresentable, and
silently stripping one would let two different inputs produce one identifier.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Final

from causalog.core.errors import ContractViolationError

__all__ = [
    "COLLECTION_SEPARATOR",
    "DIGEST_LENGTH",
    "FLOAT_QUANTIZATION_PLACES",
    "PAIR_SEPARATOR",
    "PAYLOAD_SEPARATOR",
    "IdentifierPrefix",
    "canonical_instant",
    "canonical_pairs",
    "canonical_payload",
    "canonical_sequence",
    "canonical_text",
    "digest",
    "format_float",
]

#: Every float is quantized to this many decimal places at every serialization boundary.
FLOAT_QUANTIZATION_PLACES: Final[int] = 6

#: The single admissible separator between top-level fields of a canonical payload.
PAYLOAD_SEPARATOR: Final[str] = "|"

#: The separator between members of a collection inside one field.
COLLECTION_SEPARATOR: Final[str] = ","

#: The separator between the two halves of a pair inside a collection.
PAIR_SEPARATOR: Final[str] = "="

#: Characters of the hex digest retained in an identifier.
DIGEST_LENGTH: Final[int] = 16

#: Leaf escapes, applied in sequence. The backslash rule must stay first: escaping it
#: after the others would double-escape the backslashes they introduce.
_LEAF_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("\\", "\\\\"),
    (PAYLOAD_SEPARATOR, "\\p"),
    (COLLECTION_SEPARATOR, "\\c"),
    (PAIR_SEPARATOR, "\\e"),
)


class IdentifierPrefix(str, Enum):
    """The closed set of identifier prefixes."""

    EVENT = "evt"
    ENTITY = "ent"
    STATE = "sta"
    TRANSITION = "trn"
    CANDIDATE_EDGE = "edg"
    EVIDENCE_RECORD = "evd"
    #: Added additively for module 9 (contracts.md 1.4.0), as ONTOLOGY, MAPPING and
    #: TIMELINE were before it. `EvidenceItem` carried a free-form identifier because
    #: nothing had yet needed to MINT one; module 9 mints thousands, and an
    #: unaddressed item is one a rerun cannot reproduce. No existing recipe moves.
    EVIDENCE_ITEM = "evi"
    SIMULATED_WORLD = "sim"
    RUN = "run"
    ONTOLOGY = "ont"
    MAPPING = "map"
    TIMELINE = "tml"
    RULE_PACK = "rul"
    #: Added additively for modules 11 and 12 and the pattern miner (contracts.md 1.5.0),
    #: as EVIDENCE_ITEM, ONTOLOGY, MAPPING and TIMELINE were before them. Each names an
    #: artifact that a rerun must reproduce byte-identically: a propagation report over one
    #: seed, a ranking over one outcome, and a structural pattern found across the whole
    #: run. No existing address recipe moves.
    PROPAGATION = "prp"
    ROOT_CAUSE = "rca"
    PATTERN = "pat"
    #: Added additively for module 13 (contracts.md 1.10.0), as PROPAGATION, ROOT_CAUSE and
    #: PATTERN were before it. An intervention is the input a simulated world is addressed
    #: BY, so it needs an address of its own: two runs handed the same change must produce
    #: the same identifier, and a world whose input cannot be named cannot be reproduced.
    #: No existing address recipe moves.
    INTERVENTION = "itv"
    #: Added additively for module 13 (contracts.md 1.10.0). A simulated world is addressed
    #: `sim:digest(base_graph_id | mutations)` (`CONVENTIONS.md` §9) and until now no graph
    #: had an address for that recipe's first half: `PromotedGraph` and `CausalGraph` are
    #: both scoped to a `run_id`, and one run holds BOTH, so a run identifier cannot
    #: distinguish the graph the engine states from the one it declined to state. Digesting
    #: the graph's own links separates them. No existing address recipe moves.
    CAUSAL_GRAPH = "cgr"


def format_float(value: float) -> str:
    """Return the one admissible text form of a float (`CONVENTIONS.md` §11).

    Quantized to `FLOAT_QUANTIZATION_PLACES`, always in fixed notation, and never `-0.0`.
    This is the only float formatter in the system: two boundaries that format floats
    differently produce two identifiers for one value, which is a determinism defect that
    surfaces as an unreproducible graph rather than as an exception.

    Raises:
        ContractViolationError: if the value is NaN or infinite. Neither has a canonical
            text form, and neither is an admissible confidence, weight, or magnitude.
    """
    if not math.isfinite(value):
        raise ContractViolationError(
            f"causalog.core.identifiers.format_float received {value!r}; a canonical "
            "payload admits only finite floats (CONVENTIONS.md §11)."
        )
    quantum = Decimal(1).scaleb(-FLOAT_QUANTIZATION_PLACES)
    quantized = Decimal(repr(value)).quantize(quantum)
    if quantized == 0:
        quantized = abs(quantized)
    return f"{quantized:.{FLOAT_QUANTIZATION_PLACES}f}"


def canonical_instant(moment: datetime) -> str:
    """Return the canonical text form of a UTC instant.

    ISO-8601 with an explicit offset, which is what `CONVENTIONS.md` §10 requires on the
    wire. A naive datetime is a defect and is refused here rather than silently assumed to
    be UTC -- assuming is how a local-time value enters the system and is never noticed.

    Raises:
        ContractViolationError: if the instant is naive or is not in UTC.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ContractViolationError(
            "causalog.core.identifiers.canonical_instant received a naive datetime; all "
            "instants are timezone-aware UTC (CONVENTIONS.md §10)."
        )
    if moment.utcoffset() != timedelta(0):
        raise ContractViolationError(
            f"causalog.core.identifiers.canonical_instant received offset "
            f"{moment.utcoffset()}; all instants are stored in UTC (CONVENTIONS.md §10)."
        )
    return moment.isoformat()


def canonical_text(value: str) -> str:
    """Escape a leaf value so it cannot be confused with payload structure.

    Injective: two different leaves never escape to one string, so `a|b` as a single leaf
    and `a`, `b` as two fields stay distinguishable.
    """
    escaped = value
    for raw, replacement in _LEAF_ESCAPES:
        escaped = escaped.replace(raw, replacement)
    return escaped


def canonical_sequence(values: Iterable[str]) -> str:
    """Encode an already-sequenced collection of leaves as one payload field.

    The caller sorts. This function never sorts, because the canonical sort key differs
    per collection (`CONVENTIONS.md` §11) and a helper that guessed would quietly produce
    a different identifier than the recipe specifies.
    """
    return COLLECTION_SEPARATOR.join(canonical_text(value) for value in values)


def canonical_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    """Encode key/value pairs as one payload field, sorted by key then value.

    Sorting here is safe and is done here precisely because every pair collection in the
    canonical types (attributes, changed attributes, metadata) shares one sort key.
    """
    encoded = sorted(
        f"{canonical_text(key)}{PAIR_SEPARATOR}{canonical_text(value)}" for key, value in pairs
    )
    return COLLECTION_SEPARATOR.join(encoded)


def canonical_payload(*fields: str) -> str:
    """Join already-encoded fields into a canonical payload.

    Raises:
        ContractViolationError: if a field contains a raw `|`. Every leaf must have passed
            through `canonical_text` first; an unescaped separator means the caller built
            the field by hand and two different inputs can now collide.
    """
    for field in fields:
        if PAYLOAD_SEPARATOR in field:
            raise ContractViolationError(
                "causalog.core.identifiers.canonical_payload received a field containing "
                f"an unescaped {PAYLOAD_SEPARATOR!r}; encode leaves with canonical_text "
                "before joining (CONVENTIONS.md §9)."
            )
    return PAYLOAD_SEPARATOR.join(fields)


def digest(prefix: IdentifierPrefix, payload: str) -> str:
    """Return `<prefix>:<sha256(canonical_payload)[:16]>`.

    Contract:
      * The caller is responsible for canonicalization; this function never sorts.
      * A collision on differing payloads is a `CRITICAL` defect, checked at insert by
        the persistence port, never retried here.
      * The payload is encoded UTF-8. The digest depends on nothing else -- no salt, no
        process state, no wall clock -- so the same payload yields the same identifier in
        any process, on any platform, in any interpreter session.
    """
    hashed = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix.value}:{hashed[:DIGEST_LENGTH]}"
