"""The migration runner (ADR-0033).

ADR-0015 excludes every ORM and every migration framework: migrations are numbered raw
SQL. Its own negative-consequences section names the cost -- "writing an apply-and-record
runner by hand" -- and this is that runner.

What it guarantees, and what each guarantee is defending against:

* **Every application is recorded.** `schema_migration` holds the version, the file name,
  the sha256 of the bytes applied, when, and how long. A schema whose ledger is empty is
  indistinguishable from an unmigrated one, which is why the PostgreSQL init directory is
  no longer used: it applies files without writing a ledger.
* **An applied migration whose bytes changed is a hard error**, naming the version. Not a
  skip, not a re-application. An applied migration is history; editing one means the
  database in front of you and the file in the repository describe different schemas, and
  a runner that shrugs lets that difference grow silently.
* **Every forward migration has a reverse with the same basename** under `sql/down/`. A
  migration nobody can undo is one nobody will risk applying, and "forward-only" in
  practice means "irreversible in an incident".
* **One migration, one transaction.** PostgreSQL has transactional DDL, so a failed
  migration leaves nothing behind. A half-applied migration is the state this runner is
  built to make unreachable.
* **The ledger is advisory-locked** during a run, so two concurrent `make migrate`
  invocations serialize instead of racing to create the same object.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from psycopg import Connection

from causalog.core.errors import ContractViolationError
from causalog.persistence.postgres.connection import PostgresConnectionFactory

__all__ = ["MIGRATION_FILENAME", "Migration", "PostgresMigrator", "discover_migrations"]

#: `NNNN_<verb>_<subject>.sql` (`CONVENTIONS.md` §5). Dated filenames are excluded by the
#: pattern rather than by review: two developers dating a file the same day produce an
#: ambiguous sequence, and the sequence is the only thing ordering the series.
MIGRATION_FILENAME: Final[re.Pattern[str]] = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

#: A fixed 64-bit key for `pg_advisory_lock`. Arbitrary, and constant: two runners must
#: choose the same number or the lock protects nothing.
_ADVISORY_LOCK_KEY: Final[int] = 0x0CA05A106D191A71

_LEDGER_DDL: Final[str] = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version        TEXT PRIMARY KEY,
    name           TEXT        NOT NULL,
    content_sha256 TEXT        NOT NULL,
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms    INTEGER     NOT NULL
);
COMMENT ON TABLE schema_migration IS
    'The migration ledger: the authority on what schema this database holds. A schema '
    'whose ledger is empty is indistinguishable from an unmigrated one (ADR-0033).';
COMMENT ON COLUMN schema_migration.content_sha256 IS
    'The bytes actually applied. A later run whose file hashes differently is a hard '
    'error naming the version -- an applied migration is history, and editing one means '
    'the database and the repository describe different schemas.';
"""


@dataclass(frozen=True)
class Migration:
    """One numbered migration and its reverse."""

    version: str
    name: str
    forward_path: Path
    reverse_path: Path

    @property
    def content_sha256(self) -> str:
        """Return the sha256 of the forward file's bytes."""
        return hashlib.sha256(self.forward_path.read_bytes()).hexdigest()


def discover_migrations(sql_root: Path) -> tuple[Migration, ...]:
    """Return the migration series in ascending version order.

    Discovery is derived from the directory, never from a checked-in list. A list would be
    one more place to forget: a migration added without editing it would be collected by
    nothing, and zero applied migrations report exactly like a clean run. This is the same
    reasoning ADR-0030 applied to ontology pack discovery.

    Raises when a forward migration has no reverse, when a reverse has no forward, when a
    filename does not match `NNNN_<verb>_<subject>.sql`, or when the series has a
    duplicate or a gap.
    """
    forward_dir = sql_root / "migrations"
    reverse_dir = sql_root / "down"
    if not forward_dir.is_dir():
        raise ContractViolationError(
            f"No migration directory at {forward_dir}. The runner discovers the series "
            "from the directory rather than from a checked-in list, so an absent "
            "directory is an error and never an empty series."
        )

    migrations: list[Migration] = []
    for path in sorted(forward_dir.glob("*.sql")):
        match = MIGRATION_FILENAME.match(path.name)
        if match is None:
            raise ContractViolationError(
                f"Migration {path.name!r} does not match NNNN_<verb>_<subject>.sql "
                "(CONVENTIONS.md §5). The numeric prefix is the only thing ordering the "
                "series; a file outside the pattern has no defined position in it."
            )
        reverse = reverse_dir / path.name
        if not reverse.is_file():
            raise ContractViolationError(
                f"Migration {path.name!r} has no reverse at "
                f"{reverse.as_posix()}. Every forward migration ships with its exact "
                "reverse (ADR-0033): a migration nobody can undo is one nobody will risk "
                "applying, and 'forward-only' means 'irreversible in an incident'."
            )
        migrations.append(
            Migration(
                version=match.group(1),
                name=match.group(2),
                forward_path=path,
                reverse_path=reverse,
            )
        )

    if reverse_dir.is_dir():
        forward_names = {migration.forward_path.name for migration in migrations}
        for orphan in sorted(reverse_dir.glob("*.sql")):
            if orphan.name not in forward_names:
                raise ContractViolationError(
                    f"Reverse migration {orphan.name!r} has no forward migration. A "
                    "reversal for a migration that was never written would undo "
                    "something nothing created."
                )

    versions = [migration.version for migration in migrations]
    if len(set(versions)) != len(versions):
        raise ContractViolationError(
            f"Duplicate migration version in {versions}. Two files claiming one position "
            "make the series order depend on the filesystem."
        )
    expected = [f"{index:04d}" for index in range(1, len(versions) + 1)]
    if versions != expected:
        raise ContractViolationError(
            f"Migration series has a gap or starts late: found {versions}, expected "
            f"{expected}. A gap usually means a migration was deleted rather than "
            "reversed, which leaves the ledger describing a schema nobody can rebuild."
        )
    return tuple(migrations)


class PostgresMigrator:
    """Applies and reverses the migration series. Implements the `SchemaMigrator` port."""

    def __init__(self, factory: PostgresConnectionFactory, sql_root: Path) -> None:
        """Bind the runner to a connection source and a migration directory."""
        self._factory = factory
        self._migrations = discover_migrations(sql_root)

    @property
    def migrations(self) -> tuple[Migration, ...]:
        """Return the discovered series, ascending."""
        return self._migrations

    # -- ledger -------------------------------------------------------------

    def _ensure_ledger(self, connection: Connection[Any]) -> None:
        with connection.cursor() as cursor:
            cursor.execute(_LEDGER_DDL)

    def _applied(self, connection: Connection[Any]) -> dict[str, str]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version, content_sha256 FROM schema_migration ORDER BY version")
            return {row[0]: row[1] for row in cursor.fetchall()}

    def applied_versions(self) -> tuple[str, ...]:
        """Return the applied migration versions, ascending."""
        with self._factory.connect() as connection:
            self._ensure_ledger(connection)
            connection.commit()
            return tuple(sorted(self._applied(connection)))

    def _verify_checksums(self, applied: dict[str, str]) -> None:
        """Refuse to proceed when an applied migration's bytes have changed."""
        for migration in self._migrations:
            recorded = applied.get(migration.version)
            if recorded is None:
                continue
            if recorded != migration.content_sha256:
                raise ContractViolationError(
                    f"Migration {migration.version}_{migration.name} was applied with "
                    f"content {recorded[:12]}… and now hashes to "
                    f"{migration.content_sha256[:12]}…. An applied migration is history: "
                    "the database in front of you and the file in this repository "
                    "describe different schemas. Write a new migration; do not edit an "
                    "applied one (ADR-0033)."
                )

    # -- forward ------------------------------------------------------------

    def migrate(self, target_version: str | None = None) -> tuple[str, ...]:
        """Apply pending migrations up to `target_version` and return what was applied."""
        applied_now: list[str] = []
        with self._factory.connect() as connection:
            self._ensure_ledger(connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_ADVISORY_LOCK_KEY,))
            applied = self._applied(connection)
            self._verify_checksums(applied)

            for migration in self._migrations:
                if migration.version in applied:
                    continue
                if target_version is not None and migration.version > target_version:
                    break
                started = time.monotonic()
                with connection.cursor() as cursor:
                    cursor.execute(migration.forward_path.read_text())
                    cursor.execute(
                        "INSERT INTO schema_migration "
                        "(version, name, content_sha256, duration_ms) VALUES (%s, %s, %s, %s)",
                        (
                            migration.version,
                            migration.name,
                            migration.content_sha256,
                            int((time.monotonic() - started) * 1000),
                        ),
                    )
                applied_now.append(migration.version)
            connection.commit()
        return tuple(applied_now)

    # -- reverse ------------------------------------------------------------

    def rollback(self, target_version: str) -> tuple[str, ...]:
        """Reverse applied migrations down to `target_version`, newest first.

        `target_version` is the version to stop *at*: `rollback("0003")` leaves 0001
        through 0003 applied. `rollback("0000")` empties the schema, which is exactly what
        the up/down test asserts -- a reversal that leaves residue is not a reversal.
        """
        reversed_now: list[str] = []
        with self._factory.connect() as connection:
            self._ensure_ledger(connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_ADVISORY_LOCK_KEY,))
            applied = self._applied(connection)
            self._verify_checksums(applied)

            for migration in reversed(self._migrations):
                if migration.version not in applied:
                    continue
                if migration.version <= target_version:
                    break
                with connection.cursor() as cursor:
                    cursor.execute(migration.reverse_path.read_text())
                    cursor.execute(
                        "DELETE FROM schema_migration WHERE version = %s", (migration.version,)
                    )
                reversed_now.append(migration.version)
            connection.commit()
        return tuple(reversed_now)
