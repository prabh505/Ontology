"""Bind dataset columns and values to ontology concepts (module 2).

The mapping itself is DATA at `ontology/packs/<domain>/mapping.yaml` (extension seam 3).
This package holds the schema that data is validated against, the loader that refuses an
unconfirmed proposal, the coverage assessment that says what is unmapped and what that
breaks, and the auto-suggester whose output is a proposal and never a commitment.

See `README.md` for this package's forbidden dependencies.
"""

from __future__ import annotations

from causalog.ingestion.schema_mapper.apply import (
    MappedRecord,
    MappedRecordBatch,
    MappingPlan,
    address_of,
    apply_mapping,
    clean_values,
    map_batch,
    mapped_addresses,
)
from causalog.ingestion.schema_mapper.coverage import (
    CoverageReport,
    MappingFinding,
    assess_coverage,
)
from causalog.ingestion.schema_mapper.dsl import (
    MAPPING_SCHEMA_VERSION,
    TEMPORAL_TRANSFORMS,
    AttributeRef,
    ColumnBindingSpec,
    ConditionExpression,
    ConditionOperator,
    EventEmissionSpec,
    IdentityBindingSpec,
    MappingStatus,
    OccurredAtPolicy,
    OccurredAtSpec,
    PrecedencePairSpec,
    ReferentialConstraintSpec,
    SchemaMappingSpec,
    TargetKind,
    TemporalBindingSpec,
    TimezonePolicy,
    Transform,
    UnmappedValuePolicy,
)
from causalog.ingestion.schema_mapper.hashing import mapping_hash
from causalog.ingestion.schema_mapper.loader import (
    MAPPING_DOCUMENT_NAME,
    LoadedMapping,
    inspect_mapping,
    load_mapping,
)
from causalog.ingestion.schema_mapper.suggest import (
    MappingProposal,
    SuggestedBinding,
    render_proposal_yaml,
    suggest_mapping,
)
from causalog.ingestion.schema_mapper.transforms import (
    PRECISION_SPANS,
    apply_transform,
    apply_transforms,
    apply_transforms_stepwise,
    build_interval,
    parse_source_instant,
)

__all__ = [
    "MAPPING_DOCUMENT_NAME",
    "MAPPING_SCHEMA_VERSION",
    "PRECISION_SPANS",
    "TEMPORAL_TRANSFORMS",
    "AttributeRef",
    "ColumnBindingSpec",
    "ConditionExpression",
    "ConditionOperator",
    "CoverageReport",
    "EventEmissionSpec",
    "IdentityBindingSpec",
    "LoadedMapping",
    "MappedRecord",
    "MappedRecordBatch",
    "MappingFinding",
    "MappingPlan",
    "MappingProposal",
    "MappingStatus",
    "OccurredAtPolicy",
    "OccurredAtSpec",
    "PrecedencePairSpec",
    "ReferentialConstraintSpec",
    "SchemaMappingSpec",
    "SuggestedBinding",
    "TargetKind",
    "TemporalBindingSpec",
    "TimezonePolicy",
    "Transform",
    "UnmappedValuePolicy",
    "address_of",
    "apply_mapping",
    "apply_transform",
    "apply_transforms",
    "apply_transforms_stepwise",
    "assess_coverage",
    "build_interval",
    "clean_values",
    "inspect_mapping",
    "load_mapping",
    "map_batch",
    "mapped_addresses",
    "mapping_hash",
    "parse_source_instant",
    "render_proposal_yaml",
    "suggest_mapping",
]
