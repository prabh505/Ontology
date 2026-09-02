"""DataCo-derived test fixtures.

`CONVENTIONS.md` §14: this is the ONLY directory in the test suite where LAW-DOMAIN
vocabulary may appear. `sample.csv` is a deterministic slice of the head of the published
distribution plus seven hand-planted defect rows, one per validation rule that needs a
negative case against a realistically shaped row. It is kept in `cp1252`, like the real
file, so the encoding probe is exercised rather than assumed.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PLANTED_DEFECT_ROWS", "SAMPLED_ROW_COUNT", "SAMPLE_CSV", "SAMPLE_ROW_COUNT"]

SAMPLE_CSV: Path = Path(__file__).resolve().parent / "sample.csv"

#: Rows taken unmodified from the head of the real file.
SAMPLED_ROW_COUNT: int = 200

#: Rows appended with a deliberate defect, keyed by the rule each one must trigger.
PLANTED_DEFECT_ROWS: dict[str, int] = {
    "DQ-TMP-PRECEDENCE-VIOLATION": 201,
    "DQ-CON-UNMAPPED-VALUE": 202,
    "DQ-REF-ORPHAN-KEY": 203,
    "DQ-TMP-UNPARSEABLE": 204,
    "DQ-STR-BLANK-REQUIRED": 205,
    "DQ-STR-UNPARSEABLE": 206,
    "DQ-REF-DUPLICATE-IDENTITY": 207,
}

#: Every data row in the fixture.
SAMPLE_ROW_COUNT: int = SAMPLED_ROW_COUNT + len(PLANTED_DEFECT_ROWS)
