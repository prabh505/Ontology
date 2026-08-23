"""The evidence record: the only permitted link from an assertion back to its source.

LAW-EVIDENCE. An evidence record is the citation an inference points at; it is never the
thing an inference computes over (LAW-EVENT).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["EvidenceRecord"]


class EvidenceRecord(BaseModel):
    """A citation into a versioned dataset.

    `source_locator` is an opaque, dataset-version-scoped pointer (for example a file
    identifier plus a record offset). The raw record itself is never carried here and
    never appears in a log or an error message (`CONVENTIONS.md` §7, §8).

    `source_timezone` records the timezone the source expressed, or its absence. It lives
    here and never on an `Event` (`CONVENTIONS.md` §10).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_record_id: str
    dataset_version: str
    source_locator: str
    source_timezone: str | None
