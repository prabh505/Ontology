# `deployment/sql`

Two directories, one numbered series.

```
migrations/NNNN_<verb>_<subject>.sql   forward
down/NNNN_<verb>_<subject>.sql         its exact reverse, same basename
```

Every forward migration has a reverse with the **same file name** in `down/`. The pairing
is by name, not by convention, and `scripts/check_migration_pairs.py` fails the build when
one exists without the other — a migration nobody can undo is a migration nobody will risk
applying.

## Why two directories rather than a `.down.sql` suffix

The suffix form sorts wrong. `0003_x.down.sql` precedes `0003_x.sql` lexically, so any tool
that reads a directory in name order — PostgreSQL's own init directory included — would run
the reversal first. Separating the directories removes the ordering question instead of
documenting a trap.

## The ledger, and why the init directory is no longer used

Migrations are applied by `causalog.persistence.postgres.migrator`, exposed as
`make migrate` / `make migrate-down RUN_TO=NNNN`. The runner records every application in
`schema_migration`: version, name, sha256 of the file it applied, when, and how long it
took. That table is the authority on what the schema is.

`migrations/` used to be mounted at `/docker-entrypoint-initdb.d`, where PostgreSQL applies
`*.sql` in lexical order on first initialization. That path is no longer used, because it
applies migrations **without writing the ledger** — leaving a database whose schema exists
and whose ledger says nothing has been applied. The two would then disagree, and the
disagreement is invisible until a later migration fails on an object it did not create.
The directory is still mounted, read-only at `/migrations`, so the files are available
inside the container for inspection and for a manual `psql -f`.

`make up` therefore does not leave a migrated database. Run `make migrate` after it.

## Checksums

Re-running the runner over an already-applied migration whose bytes have changed is a hard
error naming the version, not a silent skip and not a re-application. An applied migration
is history; editing one means the database in front of you and the file in the repository
describe different schemas, and only one of them can be right.

## `seeds/`

Minimal local fixtures, mounted read-only at `/seeds` and **never** applied automatically.
A fixture row that appears as a side effect of starting a container is indistinguishable
from a fact, and a fact with no evidence record cannot satisfy LAW-EVIDENCE.

**Forbidden:** no schema for the Neo4j projection lives here. The projection is derived and
is built only from PostgreSQL facts (ADR-0001); writing it from a migration would create a
graph with no fact behind it.
