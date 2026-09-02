"""Connection management for the system of record.

Three settings are applied to every session and each exists for a stated reason:

* `TIME ZONE 'UTC'` -- every instant in this schema is `TIMESTAMPTZ` in UTC
  (`CONVENTIONS.md` §10). A session whose zone came from the server locale would render
  the same instant differently on two machines, and a determinism comparison would see two
  values where there is one.
* `search_path` pinned to the application schema -- an unpinned search path resolves a
  table name against whatever the role's default happens to be, which is a silent way to
  read the wrong database.
* `application_name` -- so a long-running rebuild is attributable in `pg_stat_activity`
  rather than showing up as an anonymous connection somebody has to guess about.

The DSN is read from the environment, never assembled from parts here, and never logged:
it carries a password (`CONVENTIONS.md` §8 forbids logging credentials).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Final

import psycopg
from psycopg import Connection

from causalog.core.errors import ContractViolationError

__all__ = ["DSN_ENVIRONMENT_VARIABLE", "PostgresConnectionFactory"]

#: The single environment variable naming the system of record. Matches the compose file
#: and the CI service definition; a second spelling would let two of them disagree.
DSN_ENVIRONMENT_VARIABLE: Final[str] = "CAUSALOG_POSTGRES_DSN"

_APPLICATION_NAME: Final[str] = "causalog"


class PostgresConnectionFactory:
    """Hands out configured connections. Holds no state a caller can corrupt.

    Deliberately not a pool. A pool is the right answer for the API's request-per-second
    profile and the wrong answer for the two workloads this package has today -- a single
    long bulk load and a single long rebuild -- where a pool adds a lifecycle to get wrong
    and saves nothing. `orchestration` may wrap this in one when module 16 gives it a
    reason; the port does not change if it does.
    """

    def __init__(self, dsn: str | None = None) -> None:
        """Store the DSN, resolving it from the environment when not supplied."""
        resolved = dsn if dsn is not None else os.environ.get(DSN_ENVIRONMENT_VARIABLE)
        if not resolved:
            raise ContractViolationError(
                f"No PostgreSQL DSN: pass one explicitly or set "
                f"{DSN_ENVIRONMENT_VARIABLE}. The system of record is not optional "
                "(ADR-0001), and defaulting to a local socket would silently write facts "
                "into whatever database happened to be running."
            )
        self._dsn = resolved

    @contextmanager
    def connect(self, *, autocommit: bool = False) -> Iterator[Connection[Any]]:
        """Yield a configured connection, closing it on exit.

        `autocommit` is off by default: a caller that forgets to commit should lose its
        work loudly at the end of the block rather than have each statement land
        independently, which is how a partially applied migration happens.
        """
        with psycopg.connect(
            self._dsn, autocommit=autocommit, application_name=_APPLICATION_NAME
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")
                cursor.execute("SET search_path TO public")
            yield connection

    @contextmanager
    def bulk_connect(self) -> Iterator[Connection[Any]]:
        """Yield a connection tuned for one large, single-transaction load.

        `synchronous_commit = off` is `SET LOCAL`, so it applies to this transaction and
        cannot leak into another session. It trades durability of the *commit
        acknowledgement* for throughput: a crash in the seconds after commit may lose the
        load. That is acceptable here and nowhere else, because a lost bulk load is
        re-runnable from a pinned, hashed source file -- the load is a function of its
        inputs, which is the same property the whole engine rests on.
        """
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL synchronous_commit = off")
                # The promotion sorts ~1.5 million rows across ten tables on the reference
                # dataset. At the 4 MB default those sorts spill to disk; raised, they stay
                # in memory. Measured on the reference shape: ~7% off the total load, which
                # is real and is not the difference between meeting the prd.md §55 budget
                # and missing it -- see PROGRESS.md for the measurement and the finding.
                #
                # SET LOCAL, so both settings die with this transaction. Setting them
                # globally would give every concurrent query the same allowance, and
                # `work_mem` is per sort node per connection: the number that helps one
                # bulk load is the number that exhausts the host under twenty of them.
                cursor.execute("SET LOCAL work_mem = '256MB'")
                cursor.execute("SET LOCAL maintenance_work_mem = '512MB'")
            yield connection
