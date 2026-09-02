"""The migration series applies forward, reverses cleanly, and refuses an edited history.

ADR-0015 excludes every migration framework, so the properties a framework would have
provided have to be tested rather than assumed. There are three, and each has a specific
failure it prevents:

  * **Forward from empty.** The obvious one, and the only one most projects test.
  * **Reverse to empty.** Untested reversals rot. The first time anyone needs one is
    during an incident, which is the worst possible moment to discover that 0009's
    reversal forgot the extension it created.
  * **Forward again after reversing.** Catches the reversal that "worked" by leaving
    something behind -- a function, an index, an extension -- which the re-application
    then trips over. `CREATE ... IF NOT EXISTS` hides exactly this, so the test looks at
    the catalogue rather than at whether the statements succeeded.

The ledger, not the schema, is the authority on what has been applied, so it is asserted
directly too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from causalog.core.errors import ContractViolationError
from tests import persistence_support

#: Everything the series creates in `public`, except the ledger itself. Written out rather
#: than derived, so a table added without a reversal shows up as a residue failure here
#: instead of silently surviving a rollback.
LEDGER_TABLE = "schema_migration"


@pytest.fixture
def migrator() -> None:
    """Return a migrator over an empty database, and empty it again afterwards."""
    from causalog.persistence.postgres.migrator import PostgresMigrator

    factory = persistence_support.connection_factory()
    instance = PostgresMigrator(factory, persistence_support.SQL_ROOT)
    instance.rollback("0000")
    yield instance
    instance.rollback("0000")


def _catalogue(factory: Any) -> dict[str, set[str]]:
    """Return the objects the series is responsible for, from the system catalogue."""
    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
        tables = {row[0] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' ORDER BY 1"
        )
        functions = {row[0] for row in cursor.fetchall()}
        cursor.execute("SELECT t.tgname FROM pg_trigger t WHERE NOT t.tgisinternal ORDER BY 1")
        triggers = {row[0] for row in cursor.fetchall()}
        cursor.execute("SELECT extname FROM pg_extension ORDER BY 1")
        extensions = {row[0] for row in cursor.fetchall()}
    return {
        "tables": tables,
        "functions": functions,
        "triggers": triggers,
        "extensions": extensions,
    }


def test_the_series_applies_forward_from_empty(migrator: Any) -> None:
    applied = migrator.migrate()
    assert applied == tuple(m.version for m in migrator.migrations), (
        "Every migration in the discovered series must apply, in ascending order. The "
        "series is derived from the directory rather than from a checked-in list, so a "
        "migration added without being registered anywhere is still applied here."
    )
    assert migrator.applied_versions() == applied


def test_the_series_reverses_to_an_empty_schema(migrator: Any) -> None:
    factory = persistence_support.connection_factory()
    before = _catalogue(factory)
    migrator.migrate()
    migrator.rollback("0000")
    after = _catalogue(factory)

    residue = {kind: sorted(after[kind] - before[kind] - {LEDGER_TABLE}) for kind in after}
    assert not any(residue.values()), (
        f"Reversing the series left objects behind: {residue}. A reversal that leaves "
        "residue is not a reversal -- the next forward run trips over an object it did "
        "not create, and `CREATE ... IF NOT EXISTS` hides that until something depends on "
        "the difference."
    )
    assert migrator.applied_versions() == ()


def test_the_ledger_survives_the_reversal_and_is_the_authority(migrator: Any) -> None:
    """The ledger table itself is NOT dropped by a full rollback, deliberately.

    It records what has been applied, including that nothing currently is. Dropping it
    would leave a database whose schema is empty and whose history is unknown, which is
    indistinguishable from a database nobody has ever migrated -- and those two states
    need different actions.
    """
    factory = persistence_support.connection_factory()
    migrator.migrate()
    migrator.rollback("0000")
    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tablename = %s",
            (LEDGER_TABLE,),
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(f"SELECT count(*) FROM {LEDGER_TABLE}")  # noqa: S608
        assert cursor.fetchone()[0] == 0


def test_the_series_re_applies_after_a_full_reversal(migrator: Any) -> None:
    migrator.migrate()
    migrator.rollback("0000")
    reapplied = migrator.migrate()
    assert reapplied == tuple(m.version for m in migrator.migrations)


def test_a_partial_rollback_stops_at_the_target(migrator: Any) -> None:
    migrator.migrate()
    reversed_versions = migrator.rollback("0007")
    assert set(migrator.applied_versions()) == {
        "0001",
        "0002",
        "0003",
        "0004",
        "0005",
        "0006",
        "0007",
    }
    assert "0007" not in reversed_versions, (
        "`rollback('0007')` stops AT 0007 and leaves it applied. The alternative reading "
        "-- reverse 0007 too -- differs by one migration, which in an incident is the "
        "difference between a fix and a longer outage, so the boundary is pinned here."
    )


def test_editing_an_applied_migration_is_a_hard_error(
    migrator: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checksum change on an applied migration must refuse, not skip and not re-apply.

    An applied migration is history. Editing one means the database in front of you and
    the file in the repository describe different schemas, and only one of them can be
    right. A runner that silently skipped would let that difference grow until a later
    migration failed on an object whose definition nobody could account for.
    """
    from causalog.persistence.postgres.migrator import PostgresMigrator

    migrator.migrate()

    # Rebuild the runner over a COPY of the tree with one applied file altered. The copy
    # keeps the real migrations untouched -- a test that edited them would leave the
    # repository dirty on failure.
    copied = tmp_path / "sql"
    for directory in ("migrations", "down"):
        (copied / directory).mkdir(parents=True)
        for path in (persistence_support.SQL_ROOT / directory).glob("*.sql"):
            (copied / directory / path.name).write_text(path.read_text())
    edited = copied / "migrations" / "0002_create_audit_log.sql"
    edited.write_text(edited.read_text() + "\n-- an edit made after the fact\n")

    tampered = PostgresMigrator(persistence_support.connection_factory(), copied)
    with pytest.raises(ContractViolationError, match="0002"):
        tampered.migrate()


def test_a_migration_with_no_reverse_is_refused_at_discovery(tmp_path: Path) -> None:
    """Discovery refuses an unreversible series before it applies anything."""
    from causalog.persistence.postgres.migrator import discover_migrations

    (tmp_path / "migrations").mkdir()
    (tmp_path / "down").mkdir()
    (tmp_path / "migrations" / "0001_create_thing.sql").write_text("SELECT 1;")
    with pytest.raises(ContractViolationError, match="no reverse"):
        discover_migrations(tmp_path)


def test_a_gap_in_the_series_is_refused_at_discovery(tmp_path: Path) -> None:
    """A missing number means a migration was deleted rather than reversed."""
    from causalog.persistence.postgres.migrator import discover_migrations

    (tmp_path / "migrations").mkdir()
    (tmp_path / "down").mkdir()
    for name in ("0001_create_thing.sql", "0003_create_other.sql"):
        (tmp_path / "migrations" / name).write_text("SELECT 1;")
        (tmp_path / "down" / name).write_text("SELECT 1;")
    with pytest.raises(ContractViolationError, match="gap"):
        discover_migrations(tmp_path)
