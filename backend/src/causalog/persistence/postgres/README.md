# `causalog.persistence.postgres`

**Layer rank:** none — this package is a driven adapter, not a layer.

## Single responsibility

Implement fact storage and the append-only audit against the system of record.

## Contents

| Module | Role |
|---|---|
| `connection.py` | Configured connections; UTC, pinned `search_path`, and the bulk-tuned variant |
| `sql.py` | Every statement as a named constant, so a missing `ORDER BY` is a visible diff |
| `rows.py` | Explicit row↔model mapping — no ORM, no inferred columns |
| `fact_repository.py` | `FactRepository`: batched reads, validated writes |
| `bulk_loader.py` | `BulkFactWriter`: the prd.md §55 ingestion path |
| `audit_sink.py` | `AuditSink`: the append-only trail, with the LAW-EVIDENCE hook |
| `migrator.py` | `SchemaMigrator`: the apply-and-record runner ADR-0015 obliged |

## Why there is no ORM

The brief's constraint and the right one: **no ORM lazy-loading magic in hot paths.** A
lazily loaded relationship on `Event.confidence` turns one canonical-sequence read of the
largest table in the system into one query per row, and the calling code reads identically
either way. Every fetch here is a statement somebody wrote, and every child collection is
fetched for a whole page of parents at once.

## Forbidden dependencies

Every reasoning package.

**Forbidden behaviours:** deciding anything; repairing a malformed artifact; storing a raw
source record; reading the wall clock outside the one named fallback in
`fact_repository._database_now`.

See `docs/data-model.md` for the schema and `docs/architecture.md` §3 for the boundary.
