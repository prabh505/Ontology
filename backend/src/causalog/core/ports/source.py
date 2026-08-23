"""`SourceReader` -- the seam a new dataset implements (extension seam 1 of 6)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

__all__ = ["RawRecord", "RawRecordBatch", "SourceReader"]


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

    def read(self) -> Iterator[RawRecordBatch]:
        """Yield every batch in the dataset in canonical sequence."""
        ...
