"""The DataCo SMART Supply Chain source binding -- extension seam 1, DataCo's instance.

This is the ONE code file DataCo contributes. It names a path, a publisher, and a codec
preference; it holds no reasoning, no cleaning, no mapping, and no column semantics. Every
one of those is data (`ontology/packs/dataco/`) or generic code (`delimited.py`).

Naming `DataCoSupplyChainDataset.csv` here is correct and is correct nowhere above this
package: `causalog.persistence` is deliberately outside LAW-DOMAIN's scan scope, forbidden
edge F4 stops any reasoning package importing it, and F7 permits its `csv` import because
`persistence` carries no layer rank. See `README.md` in this directory.

The Latin-1 quirk
-----------------
The published distribution is not valid UTF-8 -- product and place names carry single-byte
accented characters. That is stated here as a codec PREFERENCE ORDER, not as an assertion:
`delimited.py` probes the candidates against the actual bytes and records which one won and
which were rejected. If the publisher re-encodes the file tomorrow, the probe notices and
the data-quality report says so; a hard-coded `encoding="latin-1"` would decode the new
file into mojibake without a single error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

__all__ = [
    "DATASET_ID",
    "ENCODING_CANDIDATES",
    "SOURCE_FILE_NAME",
    "SOURCE_URL",
    "default_pin_path",
    "default_source_path",
]

DATASET_ID: Final[str] = "dataco"

SOURCE_FILE_NAME: Final[str] = "DataCoSupplyChainDataset.csv"

SOURCE_URL: Final[str] = (
    "https://data.mendeley.com/datasets/8gx2fvg2k6/5"
    "  (DataCo SMART SUPPLY CHAIN FOR BIG DATA ANALYSIS, Constante, Silva & Herrera, 2019)"
)

#: Strictest first; the probe takes the first that decodes the real bytes cleanly. The
#: expectation is that `utf-8` is rejected and `cp1252` accepted, and the report says so
#: either way rather than this list deciding it.
ENCODING_CANDIDATES: Final[tuple[str, ...]] = ("utf-8", "utf-8-sig", "cp1252", "latin-1")


def default_source_path(repository_root: Path) -> Path:
    """Return the conventional working-copy location of the raw file (git-ignored)."""
    return repository_root / "datasets" / "raw" / SOURCE_FILE_NAME


def default_pin_path(repository_root: Path) -> Path:
    """Return the committed pin location for this dataset."""
    return repository_root / "datasets" / f"{DATASET_ID}.pin.json"
