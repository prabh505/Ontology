"""A generic delimited-text `SourceReader`: probe the bytes, then stream them.

**This module reports what the source said and nothing else.** It does not clean, does not
coerce, does not interpret a column, and does not decide a type. Those are module 1's job
(profiling and cleaning) and module 2's job (mapping), and keeping them out of here is what
lets a new domain supply a reader without supplying a policy.

Encoding is DETECTED, not declared
----------------------------------
A dataset whose encoding is asserted in code is a dataset whose encoding is wrong the day
the publisher changes it, silently, as mojibake. So the reader probes an ordered list of
candidate codecs by strict-decoding a bounded prefix AND the tail of the file, and takes
the first that decodes both cleanly. The candidate that was chosen, the candidates that
failed, and the byte offset of the first sequence that defeated the strictest candidate are
all recorded on the probe, so a fallback is visible in the data-quality report rather than
being a fact only the reader knows.

The tail is probed as well as the prefix on purpose: a file that is ASCII for its first
megabyte and Latin-1 thereafter decodes cleanly as UTF-8 from a prefix alone, which is the
exact shape of a detector that reports success for a check it did not really perform.

Determinism
-----------
Batches are emitted in file sequence with a monotonic `batch_index`, and every record's
`evidence_record_id` is content-addressed over `(dataset_version, row_number)`. Reading the
same bytes twice yields the same identifiers in the same sequence, on any platform
(`CONVENTIONS.md` §11).
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from causalog.core.errors import DataQualityError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.ports.source import RawRecord, RawRecordBatch, SourceDescription

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_ENCODING_CANDIDATES",
    "DelimitedTextSource",
    "DialectProbe",
    "EncodingProbe",
    "SourceProbe",
    "compose_dataset_version",
    "probe_source",
]

#: Codecs tried in sequence, strictest first. UTF-8 before its BOM variant before the two
#: single-byte codecs, because `latin-1` decodes ANY byte sequence without error -- it can
#: never fail, so it must be last or it would win every probe and no fallback would ever be
#: reported.
DEFAULT_ENCODING_CANDIDATES: Final[tuple[str, ...]] = ("utf-8", "utf-8-sig", "cp1252", "latin-1")

#: Rows per emitted batch. Bounds memory independently of file size.
DEFAULT_BATCH_SIZE: Final[int] = 10_000

#: Bytes read from each end of the file when probing the encoding and the dialect.
_PROBE_WINDOW_BYTES: Final[int] = 1_048_576

#: Bytes read per iteration when hashing the file. The file is streamed, never slurped.
_HASH_CHUNK_BYTES: Final[int] = 1_048_576


class EncodingProbe(BaseModel):
    """Which codec was chosen, which were rejected, and where the strictest one broke."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[str, ...]
    chosen: str
    rejected: tuple[str, ...]
    first_undecodable_byte_offset: int | None
    first_undecodable_reason: str | None

    @property
    def fell_back(self) -> bool:
        """Return whether a candidate stricter than the chosen one was rejected."""
        return bool(self.rejected)


class DialectProbe(BaseModel):
    """The delimiter and quoting shape sniffed from a bounded sample."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    delimiter: str
    quotechar: str
    doublequote: bool
    sniffed: bool
    """False when the sniff failed and the documented default was used instead."""


class SourceProbe(BaseModel):
    """Everything determined about a file before a single record is emitted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    byte_count: int
    content_sha256: str
    encoding: EncodingProbe
    dialect: DialectProbe
    header: tuple[str, ...]


def compose_dataset_version(dataset_id: str, content_sha256: str, mapping_hash: str) -> str:
    """Return the `dataset_version` for a pinned file read through a pinned mapping.

    Recipe: `<dataset_id>@<content_sha256[:16]>+map<mapping_digest[:16]>`.

    Both halves are left legible rather than folded into one opaque digest. The mapping
    participates in `run_id` through this value rather than through `RunKey`, which is
    frozen; the cost of that choice is that `dataset_version` no longer names the file
    alone, and a legible composite is the only real mitigation -- either half can be
    recovered by eye or by `str.split` and checked against `datasets/<id>.pin.json`.

    Args:
        dataset_id: the pack identifier, e.g. `dataco`.
        content_sha256: the full hex digest of the source bytes.
        mapping_hash: the `map:`-prefixed mapping content address.

    Raises:
        DataQualityError: if either hash is empty or the mapping hash is unprefixed.
    """
    if not content_sha256 or not mapping_hash:
        raise DataQualityError(
            "compose_dataset_version requires both a content hash and a mapping hash; a "
            "dataset_version missing either cannot identify what produced a run (ADR-0013)."
        )
    prefix = f"{IdentifierPrefix.MAPPING.value}:"
    if not mapping_hash.startswith(prefix):
        raise DataQualityError(
            f"compose_dataset_version received mapping_hash {mapping_hash!r}, which does "
            f"not carry the {prefix!r} prefix; a bare digest is not a content address "
            "(CONVENTIONS.md §9)."
        )
    mapping_digest = mapping_hash[len(prefix) :]
    return f"{dataset_id}@{content_sha256[:16]}+map{mapping_digest[:16]}"


def _hash_file(path: Path) -> tuple[str, int]:
    """Return the file's sha256 hex digest and its byte count, streaming it once."""
    hasher = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            hasher.update(chunk)
            total += len(chunk)
    return hasher.hexdigest(), total


def _window_bytes(path: Path, byte_count: int) -> bytes:
    """Return a prefix and a tail of the file, joined, for probing.

    Both ends are read. A prefix alone certifies nothing about a file whose encoding
    changes partway through, and "the check I ran is not the check I claimed" is the
    failure this repository has recorded twice (DEF-0001, OQ-014).
    """
    with path.open("rb") as handle:
        prefix = handle.read(_PROBE_WINDOW_BYTES)
        if byte_count > _PROBE_WINDOW_BYTES * 2:
            handle.seek(byte_count - _PROBE_WINDOW_BYTES)
            return prefix + handle.read(_PROBE_WINDOW_BYTES)
        return prefix + handle.read()


def _probe_encoding(sample: bytes, candidates: Sequence[str]) -> EncodingProbe:
    """Return the first candidate that strict-decodes the sample, and what it rejected."""
    rejected: list[str] = []
    offset: int | None = None
    reason: str | None = None
    for candidate in candidates:
        try:
            sample.decode(candidate, errors="strict")
        except UnicodeDecodeError as failure:
            rejected.append(candidate)
            if offset is None:
                offset = failure.start
                reason = failure.reason
            continue
        return EncodingProbe(
            candidates=tuple(candidates),
            chosen=candidate,
            rejected=tuple(rejected),
            first_undecodable_byte_offset=offset,
            first_undecodable_reason=reason,
        )
    raise DataQualityError(
        f"No candidate codec decoded the sample: tried {list(candidates)}. The candidate "
        "list must end with a codec that cannot fail (latin-1); a probe that can reject "
        "every candidate has no defined answer."
    )


def _probe_dialect(text: str) -> DialectProbe:
    """Return the sniffed delimiter and quoting, or the documented default if sniffing fails.

    A failed sniff is REPORTED (`sniffed=False`) rather than silently defaulted. A comma is
    the right guess for a `.csv`, and a wrong guess that nobody can see is how a
    single-column parse of a semicolon file becomes a data-quality report full of nulls.
    """
    try:
        dialect = csv.Sniffer().sniff(text, delimiters=",;\t|")
    except csv.Error:
        return DialectProbe(delimiter=",", quotechar='"', doublequote=True, sniffed=False)
    return DialectProbe(
        delimiter=dialect.delimiter,
        quotechar=dialect.quotechar or '"',
        doublequote=bool(dialect.doublequote),
        sniffed=True,
    )


def probe_source(
    path: Path,
    *,
    encoding_candidates: Sequence[str] = DEFAULT_ENCODING_CANDIDATES,
) -> SourceProbe:
    """Hash the file, detect its encoding and dialect, and read its header.

    Args:
        path: the file to probe.
        encoding_candidates: codecs to try, strictest first. The last must be one that
            cannot fail.

    Raises:
        DataQualityError: if the file is absent, empty, or has no header row.
    """
    if not path.is_file():
        raise DataQualityError(
            f"Source file {path} does not exist. A dataset is pinned by hash before it is "
            "read (datasets/README.md); nothing is inferred about a file that is absent."
        )
    content_sha256, byte_count = _hash_file(path)
    if byte_count == 0:
        raise DataQualityError(f"Source file {path} is empty; there is nothing to profile.")
    sample = _window_bytes(path, byte_count)
    encoding = _probe_encoding(sample, encoding_candidates)
    text = sample.decode(encoding.chosen, errors="strict")
    dialect = _probe_dialect(text[:_PROBE_WINDOW_BYTES])
    with path.open("r", encoding=encoding.chosen, newline="") as handle:
        reader = csv.reader(handle, delimiter=dialect.delimiter, quotechar=dialect.quotechar)
        header = next(reader, None)
    if not header:
        raise DataQualityError(
            f"Source file {path} has no header row. Column identity comes from the header; "
            "positional columns would make every mapping a guess about sequence."
        )
    return SourceProbe(
        path=str(path),
        byte_count=byte_count,
        content_sha256=content_sha256,
        encoding=encoding,
        dialect=dialect,
        header=tuple(header),
    )


class DelimitedTextSource:
    """Stream a delimited text file as `RawRecordBatch` values (`SourceReader`).

    The `dataset_version` is supplied rather than computed here, because it is a function of
    the mapping as well as the bytes (`compose_dataset_version`), and this class knows
    nothing about mappings. Whoever wires the run computes it and hands it over.

    A row whose field count disagrees with the header is emitted ANYWAY, padded with the
    empty string or carrying its surplus under positional names. Refusing it here would
    delete a data-quality finding before anything could count it; module 1 quarantines it
    with a reason, which is the difference between rejecting data and losing it.
    """

    def __init__(
        self,
        path: Path,
        dataset_version: str,
        *,
        probe: SourceProbe | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        encoding_candidates: Sequence[str] = DEFAULT_ENCODING_CANDIDATES,
    ) -> None:
        """Bind a file, its version, and the batch size used to stream it.

        Args:
            path: the delimited file to read.
            dataset_version: the pinned version, from `compose_dataset_version`.
            probe: a probe already computed for this file; recomputed if omitted.
            batch_size: rows per emitted batch. Must be positive.
            encoding_candidates: passed through to the probe when one is not supplied.

        Raises:
            DataQualityError: if `batch_size` is not positive.
        """
        if batch_size <= 0:
            raise DataQualityError(
                f"DelimitedTextSource batch_size must be positive, got {batch_size}. A "
                "non-positive batch size yields no batches, which reads as an empty dataset."
            )
        self._path = path
        self._dataset_version = dataset_version
        self._batch_size = batch_size
        self._probe = probe or probe_source(path, encoding_candidates=encoding_candidates)

    @property
    def probe(self) -> SourceProbe:
        """Return what was determined about the file before reading it."""
        return self._probe

    def dataset_version(self) -> str:
        """Return the pinned version identifier for this source."""
        return self._dataset_version

    def describe(self) -> SourceDescription:
        """Return the port-level description of what was determined about this file.

        The BASENAME, not the path: the description travels into a committed report, and an
        absolute path there both breaks cross-machine determinism and publishes somebody's
        home directory.
        """
        return SourceDescription(
            source_name=Path(self._probe.path).name,
            byte_count=self._probe.byte_count,
            content_sha256=self._probe.content_sha256,
            column_names=self._probe.header,
            encoding_chosen=self._probe.encoding.chosen,
            encoding_rejected=self._probe.encoding.rejected,
            first_undecodable_byte_offset=self._probe.encoding.first_undecodable_byte_offset,
            first_undecodable_reason=self._probe.encoding.first_undecodable_reason,
            field_separator=self._probe.dialect.delimiter,
            separator_was_detected=self._probe.dialect.sniffed,
        )

    def evidence_record_id(self, row_number: int) -> str:
        """Return the content-addressed citation for one source row.

        Addressed over `(dataset_version, row_number)`, so the same row of the same pinned
        file always cites identically -- across processes, machines, and reruns.
        """
        return digest(
            IdentifierPrefix.EVIDENCE_RECORD,
            canonical_payload(
                canonical_text(self._dataset_version),
                canonical_text(str(row_number)),
            ),
        )

    def _fields(self, row: Sequence[str]) -> tuple[tuple[str, str], ...]:
        """Pair a row with the header, reporting surplus fields positionally."""
        header = self._probe.header
        paired = [
            (name, row[index] if index < len(row) else "") for index, name in enumerate(header)
        ]
        paired.extend(
            (f"__surplus_{index}", value) for index, value in enumerate(row[len(header) :])
        )
        return tuple(paired)

    def read(self) -> Iterator[RawRecordBatch]:
        """Yield every batch in file sequence.

        `row_number` is 1-based over DATA rows: the header is row 0 and is not a record.
        """
        with self._path.open("r", encoding=self._probe.encoding.chosen, newline="") as handle:
            reader = csv.reader(
                handle,
                delimiter=self._probe.dialect.delimiter,
                quotechar=self._probe.dialect.quotechar,
            )
            next(reader, None)  # the header, already captured by the probe
            batch_index = 0
            pending: list[RawRecord] = []
            for row_number, row in enumerate(reader, start=1):
                pending.append(
                    RawRecord(
                        evidence_record_id=self.evidence_record_id(row_number),
                        fields=self._fields(row),
                    )
                )
                if len(pending) == self._batch_size:
                    yield RawRecordBatch(
                        dataset_version=self._dataset_version,
                        batch_index=batch_index,
                        records=tuple(pending),
                    )
                    batch_index += 1
                    pending = []
            if pending:
                yield RawRecordBatch(
                    dataset_version=self._dataset_version,
                    batch_index=batch_index,
                    records=tuple(pending),
                )
