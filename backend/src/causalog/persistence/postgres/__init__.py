"""PostgreSQL adapters: the system of record (ADR-0001).

Fact storage, the run registry, the bulk ingestion path, the migration runner, and the
append-only audit trail. Every one implements a Protocol declared in `core/ports`; nothing
here is imported by a reasoning package (forbidden edge F4).
"""

from causalog.persistence.postgres.audit_sink import PostgresAuditSink
from causalog.persistence.postgres.bulk_loader import BulkLoadReport, PostgresBulkFactWriter
from causalog.persistence.postgres.connection import PostgresConnectionFactory
from causalog.persistence.postgres.fact_repository import PostgresFactRepository
from causalog.persistence.postgres.migrator import Migration, PostgresMigrator, discover_migrations

__all__ = [
    "BulkLoadReport",
    "Migration",
    "PostgresAuditSink",
    "PostgresBulkFactWriter",
    "PostgresConnectionFactory",
    "PostgresFactRepository",
    "PostgresMigrator",
    "discover_migrations",
]
