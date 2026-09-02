"""`SourceReader` -- the seam a new dataset implements (extension seam 1 of 6)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

__all__ = ["RawRecord", "RawRecordBatch", "SourceDescription", "SourceReader"]


class RawRecord(BaseModel):
    """One record exactly as the source expressed it, plus its citation.

    This type exists ONLY in layers L2 and below. It may not cross out of
    `causalog.extraction` (LAW-EVENT).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_record_id: str
    fields: tuple[tuple[str, str], ...]


class RawRecordBatch(BaseModel):
    """A bounded, deterministically sequenced group of raw records."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_version: str
    batch_index: int
    records: tuple[RawRecord, ...]


class SourceDescription(BaseModel):
    """What is known about a source before a single record is read.

    Added with module 1. It exists so the Data Adapter can report HOW a source had to be
    read -- which codec won, which were rejected, how many bytes, which columns -- without
    importing the adapter that read it. Forbidden edge F4 permits only `orchestration` to
    import `causalog.persistence.*`, so a reader is SUPPLIED to module 1 and its findings
    have to travel on the seam rather than through its concrete type.

    Deliberately format-agnostic. A source that is not delimited leaves `field_separator`
    empty and says so through `separator_was_detected`; a source that cannot be hashed as
    one byte stream is not admissible here at all, because `dataset_version` would then
    identify nothing (ADR-0013).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_name: str
    """The file's BASENAME, never an absolute path. The description reaches a committed
    report, and an absolute path both breaks cross-machine determinism and publishes
    somebody's home directory."""

    byte_count: int
    content_sha256: str
    column_names: tuple[str, ...]

    encoding_chosen: str
    encoding_rejected: tuple[str, ...] = ()
    """Codecs tried and refused, strictest first. A non-empty tuple means the source is not
    what the strictest candidate expected, which is a data-quality finding."""

    first_undecodable_byte_offset: int | None = None
    first_undecodable_reason: str | None = None

    field_separator: str = ""
    """Empty when the concept does not apply to this source kind."""

    separator_was_detected: bool = False
    """False when the separator was assumed rather than determined. An assumed separator
    that is wrong parses a file into one column and reads as a profile full of nulls."""

    @property
    def encoding_fell_back(self) -> bool:
        """Return whether a stricter codec than the chosen one was rejected."""
        return bool(self.encoding_rejected)


@runtime_checkable
class SourceReader(Protocol):
    """Read a versioned dataset as deterministically sequenced batches.

    A new domain implements this and nothing else to be ingestible. Implementations must
    emit batches in a stable sequence for a given `dataset_version`; an unstable sequence
    breaks the determinism guarantee (`CONVENTIONS.md` §11).
    """

    def dataset_version(self) -> str:
        """Return the pinned version identifier, including the source content hash."""
        ...

    def describe(self) -> SourceDescription:
        """Return what is known about the source before any record is read."""
        ...

    def read(self) -> Iterator[RawRecordBatch]:
        """Yield every batch in the dataset in canonical sequence."""
        ...
