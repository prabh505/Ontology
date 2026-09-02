"""Load and validate a domain pack into an in-memory specification.

**Layer rank L1.** May import `causalog.core` and nothing else in the distribution
(forbidden edge F1/F2). Nothing at L4 or above may import this package (forbidden edge F3):
the reasoning engine never reads the ontology.

The domain description itself is data under `/ontology/packs/<domain>/`. This package holds
the code that reads it, and that code is **in LAW-DOMAIN scope** (ADR-0026) -- a loader that
named a domain concept would be the domain leaking in through the one door built to keep it
out.
"""

from __future__ import annotations

from causalog.ontology_runtime.diagnostics import Diagnostic, Severity
from causalog.ontology_runtime.dsl import PACK_SCHEMA_VERSION, DomainPack, ResolvedPack
from causalog.ontology_runtime.hashing import ontology_hash
from causalog.ontology_runtime.loader import (
    LoadedPack,
    inspect_pack,
    load_pack,
    read_pack_chain,
)
from causalog.ontology_runtime.resolution import PACK_DOCUMENT_NAME

__all__ = [
    "PACK_DOCUMENT_NAME",
    "PACK_SCHEMA_VERSION",
    "Diagnostic",
    "DomainPack",
    "LoadedPack",
    "ResolvedPack",
    "Severity",
    "inspect_pack",
    "load_pack",
    "ontology_hash",
    "read_pack_chain",
]
