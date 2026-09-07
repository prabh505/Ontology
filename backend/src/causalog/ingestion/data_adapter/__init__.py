"""Read, validate, and reject raw source records (module 1).

The public surface is `import_dataset`: two streaming passes over a pinned source producing
a `DataQualityReport`, a clean layer, and a quarantine. Everything domain-specific reaches
it as data -- the ontology pack and the schema mapping -- and nothing in this package names
a column, a value, or a concept of any domain (LAW-DOMAIN).

See `README.md` for this package's forbidden dependencies.
"""

from __future__ import annotations

from causalog.ingestion.data_adapter.adapter import (
    CLEAN_LAYER_FILES,
    ImportResult,
    import_dataset,
)
from causalog.ingestion.data_adapter.cleaning import (
    CleaningAction,
    CleaningLedger,
    apply_transforms,
    apply_transforms_stepwise,
    build_interval,
)
from causalog.ingestion.data_adapter.findings import RULES, Dimension, Finding, RuleSpec, rule
from causalog.ingestion.data_adapter.precedence import derived_precedence_index
from causalog.ingestion.data_adapter.profile import (
    ColumnProfile,
    DatasetProfile,
    InferredType,
    Profiler,
)
from causalog.ingestion.data_adapter.report import (
    REPORT_SCHEMA_VERSION,
    DataQualityReport,
    HeadlineConstraint,
    render_markdown,
    report_sha256,
)
from causalog.ingestion.data_adapter.validate import IdentityIndex, RowIssue, RowValidator

__all__ = [
    "CLEAN_LAYER_FILES",
    "REPORT_SCHEMA_VERSION",
    "RULES",
    "CleaningAction",
    "CleaningLedger",
    "ColumnProfile",
    "DataQualityReport",
    "DatasetProfile",
    "Dimension",
    "Finding",
    "HeadlineConstraint",
    "IdentityIndex",
    "ImportResult",
    "InferredType",
    "Profiler",
    "RowIssue",
    "RowValidator",
    "RuleSpec",
    "apply_transforms",
    "apply_transforms_stepwise",
    "build_interval",
    "derived_precedence_index",
    "import_dataset",
    "render_markdown",
    "report_sha256",
    "rule",
]
