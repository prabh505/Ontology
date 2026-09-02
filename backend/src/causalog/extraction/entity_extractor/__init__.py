"""Derive `Entity` values, their attribute history, and a reconciliation report (module 3).

Everything domain-specific reaches this package as DATA -- the resolved ontology pack and
the schema mapping -- and nothing in it names an entity type, an attribute, or a column
(LAW-DOMAIN). `entity_type` is an opaque string; there is no branch on its value anywhere.

See `README.md` for this package's forbidden dependencies.
"""

from __future__ import annotations

from causalog.extraction.entity_extractor.extract import (
    CONFLICT_EXAMPLE_LIMIT,
    EntityExtractor,
    ExtractionResult,
    undated,
)
from causalog.extraction.entity_extractor.identity import (
    AttributeConflict,
    ConflictPolicy,
    EntityAccumulator,
    ResolvedIdentity,
)
from causalog.extraction.entity_extractor.report import (
    RECONCILIATION_SCHEMA_VERSION,
    EntityTypeReconciliation,
    ReconciliationReport,
    render_markdown,
)
from causalog.extraction.entity_extractor.versioning import (
    EntityAttributeVersion,
    EntityHistory,
    HistoryAccumulator,
)

__all__ = [
    "CONFLICT_EXAMPLE_LIMIT",
    "RECONCILIATION_SCHEMA_VERSION",
    "AttributeConflict",
    "ConflictPolicy",
    "EntityAccumulator",
    "EntityAttributeVersion",
    "EntityExtractor",
    "EntityHistory",
    "EntityTypeReconciliation",
    "ExtractionResult",
    "HistoryAccumulator",
    "ReconciliationReport",
    "ResolvedIdentity",
    "render_markdown",
    "undated",
]
