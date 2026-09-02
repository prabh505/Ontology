"""Neo4j adapters: the derived, fully rebuildable graph projection (ADR-0001).

Nothing here is a source of truth. Every node and every relationship is a function of
PostgreSQL facts, and a write with no backing fact is a defect the rebuild's verification
step is built to catch.
"""

from causalog.persistence.neo4j.projection import (
    Neo4jProjection,
    ProjectionReport,
    projection_version_for,
)
from causalog.persistence.neo4j.schema import (
    INFERRED_RELATIONSHIP_TYPES,
    NODE_LABELS,
    OBSERVED_RELATIONSHIP_TYPES,
    RELATIONSHIP_TYPES,
    schema_statements,
)

__all__ = [
    "INFERRED_RELATIONSHIP_TYPES",
    "NODE_LABELS",
    "OBSERVED_RELATIONSHIP_TYPES",
    "RELATIONSHIP_TYPES",
    "Neo4jProjection",
    "ProjectionReport",
    "projection_version_for",
    "schema_statements",
]
