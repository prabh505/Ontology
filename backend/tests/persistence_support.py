"""Shared plumbing for the tests that need a real PostgreSQL or Neo4j.

The rule these helpers exist to enforce: **a database test that cannot reach its database
is SKIPPED WITH A STATED REASON, never quietly passed.** A test that silently succeeds
when the service is absent is the DEF-0001 shape -- a check that cannot run reads exactly
like a check that passed -- and it is worse here than elsewhere, because the properties
these tests assert (append-only refusal, bi-temporal supersession, migration reversibility)
are enforced by the *database* and by nothing else. Losing them silently loses them
entirely.

The CI `integration` job provides both services, so a skip in CI means the job is
misconfigured and the skip reason says so.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_ROOT = REPO_ROOT / "deployment" / "sql"

POSTGRES_DSN_VARIABLE = "CAUSALOG_POSTGRES_DSN"
NEO4J_URI_VARIABLE = "CAUSALOG_NEO4J_URI"

_SKIP_POSTGRES = (
    f"No PostgreSQL: set {POSTGRES_DSN_VARIABLE} (`make up` provides one). This test is "
    "SKIPPED and not passed -- the properties it asserts are enforced by the database and "
    "by nothing else, so a silent pass would lose them entirely."
)

_SKIP_NEO4J = (
    f"No Neo4j: set {NEO4J_URI_VARIABLE} (`make up` provides one). This test is SKIPPED "
    "and not passed -- a projection test with no projection asserts nothing."
)


def postgres_dsn() -> str:
    """Return the DSN, or skip the test with a reason naming the variable."""
    dsn = os.environ.get(POSTGRES_DSN_VARIABLE)
    if not dsn:
        pytest.skip(_SKIP_POSTGRES)
    return dsn


def neo4j_settings() -> tuple[str, str, str]:
    """Return `(uri, user, password)`, or skip with a reason."""
    uri = os.environ.get(NEO4J_URI_VARIABLE)
    if not uri:
        pytest.skip(_SKIP_NEO4J)
    user, _, password = os.environ.get("CAUSALOG_NEO4J_AUTH", "neo4j/causalog-local").partition("/")
    return uri, user, password


def connection_factory() -> object:
    """Return a factory bound to the test DSN, skipping when there is none."""
    from causalog.persistence.postgres.connection import PostgresConnectionFactory

    return PostgresConnectionFactory(postgres_dsn())


def migrated_database() -> Iterator[object]:
    """Yield a factory over a freshly migrated, empty schema.

    The schema is torn all the way down first, then applied. Starting from whatever the
    last run left behind would make a failure depend on test order, and a bi-temporal
    assertion in particular is meaningless against rows some other test believed.
    """
    from causalog.persistence.postgres.migrator import PostgresMigrator

    factory = connection_factory()
    migrator = PostgresMigrator(factory, SQL_ROOT)
    migrator.rollback("0000")
    migrator.migrate()
    try:
        yield factory
    finally:
        migrator.rollback("0000")


def register_dataset(factory: object, dataset_version: str, ontology_hash: str) -> None:
    """Insert the version pins a fact batch's foreign keys require.

    Written out rather than hidden in a fixture, because the constraint it satisfies is a
    real one: a Run may not name an unregistered input, and facts may not be filed under a
    dataset version nobody pinned (migration 0003).
    """
    with factory.connect() as connection, connection.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            "INSERT INTO dataset_version (dataset_version, source_locator, source_sha256, "
            "record_count, accepted_count, rejected_count) VALUES (%s, %s, %s, 0, 0, 0) "
            "ON CONFLICT DO NOTHING",
            (dataset_version, "fixture://synthetic", "0" * 64),
        )
        cursor.execute(
            "INSERT INTO ontology_version (ontology_hash, pack_id, ontology_version, "
            "pack_schema_version, resolved_pack) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (ontology_hash, "fixture", "1.0.0", "1.0.0", "{}"),
        )
        cursor.execute(
            "INSERT INTO rule_pack_version (rule_pack_version, pack_id, rule_ids, "
            "content_sha256) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            ("1.0.0", "fixture", ["R-FIXTURE-0001"], "0" * 64),
        )
        connection.commit()
