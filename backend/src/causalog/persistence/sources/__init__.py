"""`SourceReader` implementations -- extension seam 1 (`docs/architecture.md` §5.1).

One module per dataset, each reading bytes and emitting `RawRecordBatch` values in a stable
sequence. This package is deliberately outside LAW-DOMAIN's scan scope: a reader must name
the real columns of a real dataset, and that is correct here and nowhere above it. See
`README.md` in this directory for why this is the only location that works.
"""

from __future__ import annotations

from causalog.persistence.sources.delimited import (
    DEFAULT_ENCODING_CANDIDATES,
    DelimitedTextSource,
    DialectProbe,
    EncodingProbe,
    SourceProbe,
    compose_dataset_version,
    probe_source,
)
from causalog.persistence.sources.pin import DatasetPin, read_pin, write_pin

__all__ = [
    "DEFAULT_ENCODING_CANDIDATES",
    "DatasetPin",
    "DelimitedTextSource",
    "DialectProbe",
    "EncodingProbe",
    "SourceProbe",
    "compose_dataset_version",
    "probe_source",
    "read_pin",
    "write_pin",
]
