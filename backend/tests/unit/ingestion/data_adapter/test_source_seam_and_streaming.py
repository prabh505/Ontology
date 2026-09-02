"""The `SourceReader` seam holds, and reading is bounded by the batch, never by the file.

Two properties module 1 rests on and neither of which is visible in its own code.

**The seam is real.** Forbidden edge F4 keeps `ingestion` from importing a concrete reader,
so the reader is supplied. That only works if the concrete reader actually satisfies the
protocol -- and a protocol nothing is checked against is a comment.

**Reading is bounded.** `prd.md` §55 puts a time budget on loading a large dataset, and a
profiler that had to hold the file could not be measured against it honestly. Memory here is
a function of the header width, the distinct-value cap and the identity cardinality, never
of the row count.
"""

from __future__ import annotations

import csv
import tracemalloc
from pathlib import Path
from typing import Any

from causalog.core.ports.source import SourceDescription, SourceReader
from causalog.persistence.sources.delimited import DelimitedTextSource, probe_source
from tests.fixtures.dataco import SAMPLE_CSV, SAMPLE_ROW_COUNT


def test_the_concrete_reader_satisfies_the_port(sample_probe: Any) -> None:
    """The injection contract. A protocol nothing is checked against is a comment."""
    source = DelimitedTextSource(SAMPLE_CSV, "sample@x+mapx", probe=sample_probe)
    assert isinstance(source, SourceReader)
    assert isinstance(source.describe(), SourceDescription)


def test_the_description_carries_a_basename_and_never_a_path(sample_probe: Any) -> None:
    """The description reaches a committed report; an absolute path must not."""
    description = DelimitedTextSource(SAMPLE_CSV, "sample@x+mapx", probe=sample_probe).describe()
    assert description.source_name == SAMPLE_CSV.name
    assert "/" not in description.source_name


def test_every_row_is_read_exactly_once_whatever_the_batch_size(sample_probe: Any) -> None:
    for batch_size in (1, 7, 64, 1_000_000):
        source = DelimitedTextSource(
            SAMPLE_CSV, "sample@x+mapx", probe=sample_probe, batch_size=batch_size
        )
        seen = [record.evidence_record_id for batch in source.read() for record in batch.records]
        assert len(seen) == SAMPLE_ROW_COUNT
        assert len(set(seen)) == SAMPLE_ROW_COUNT, "two rows share one citation"


def test_batch_indices_are_monotonic_from_zero(sample_probe: Any) -> None:
    """An unstable batch sequence breaks the determinism guarantee (CONVENTIONS.md §11)."""
    source = DelimitedTextSource(SAMPLE_CSV, "sample@x+mapx", probe=sample_probe, batch_size=32)
    indices = [batch.batch_index for batch in source.read()]
    assert indices == list(range(len(indices)))


def test_a_short_row_is_padded_and_a_long_row_is_kept_rather_than_dropped(
    tmp_path: Path,
) -> None:
    """Refusing a malformed row HERE would delete a finding before anything counted it."""
    path = tmp_path / "ragged.csv"
    path.write_text("a,b,c\n1,2,3\n4,5\n6,7,8,9\n", encoding="utf-8")
    source = DelimitedTextSource(path, "ragged@x+mapx")
    records = [record for batch in source.read() for record in batch.records]
    assert len(records) == 3
    short = dict(records[1].fields)
    assert short["c"] == "", "a missing field becomes empty, not absent"
    surplus = [name for name, _ in records[2].fields if name.startswith("__surplus_")]
    assert surplus, "a surplus field is carried so the row can be quarantined with a reason"


def test_peak_memory_does_not_grow_with_the_row_count(tmp_path: Path) -> None:
    """The property `prd.md` §55 depends on, measured rather than asserted."""
    header = "k,v\n"
    small = tmp_path / "small.csv"
    large = tmp_path / "large.csv"
    small.write_text(header + "".join(f"{i},{i}\n" for i in range(1_000)), encoding="utf-8")
    large.write_text(header + "".join(f"{i},{i}\n" for i in range(50_000)), encoding="utf-8")

    def peak(path: Path) -> int:
        source = DelimitedTextSource(path, "bench@x+mapx", probe=probe_source(path), batch_size=256)
        tracemalloc.start()
        rows = 0
        for batch in source.read():
            rows += len(batch.records)
        _current, high = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert rows > 0
        return high

    small_peak = peak(small)
    large_peak = peak(large)
    assert large_peak < small_peak * 4, (
        f"peak memory grew from {small_peak} to {large_peak} across a 50x larger file; "
        "reading is supposed to be bounded by the batch, not by the file"
    )


def test_the_raw_file_is_not_modified_by_reading_it(tmp_path: Path) -> None:
    """Cleaning produces a new layer. The evidence a conclusion cites must not move."""
    path = tmp_path / "immutable.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    before = path.read_bytes()
    source = DelimitedTextSource(path, "imm@x+mapx")
    for batch in source.read():
        assert batch.records
    assert path.read_bytes() == before


def test_the_probe_reads_both_ends_of_the_file(tmp_path: Path) -> None:
    """A prefix-only probe certifies nothing about a file whose encoding changes late."""
    path = tmp_path / "late.csv"
    with path.open("wb") as handle:
        handle.write(b"a,b\n")
        handle.write(b"clean,ascii\n" * 200_000)
        handle.write("caf\xe9,tail\n".encode("cp1252"))
    probe = probe_source(path)
    assert probe.encoding.chosen != "utf-8", (
        "the tail is not valid UTF-8 and a probe that read only the prefix would have "
        "chosen utf-8 and produced mojibake without a single error"
    )
    with path.open("r", encoding=probe.encoding.chosen, newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[-1][0] == "caf\xe9"
