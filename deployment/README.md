# `deployment/`

**Single responsibility:** define how the system runs — locally and in CI — without any
reasoning logic living here.

- `docker-compose.yml` — postgres, neo4j, redis, backend, frontend, each with a
  healthcheck so `make up` waits for readiness rather than racing it.
- `docker/` — one Dockerfile per runnable service.
- `sql/migrations/` — numbered, forward-only SQL, named `NNNN_<verb>_<subject>.sql`
  (`CONVENTIONS.md` §5). Raw SQL, no ORM and no migration framework (ADR-0015).
- `sql/seeds/` — minimal local fixtures.

## Host requirements

Allocate the container runtime **at least 4 GB of memory**. Neo4j is the constraint: with a
smaller budget — or with unrelated containers already holding most of it — it is OOM-killed
during startup and exits 137, which reads like a configuration error and is not one. Its
heap and page cache are sized in `docker-compose.yml` for a laptop running all five
services at once; production sizing is a deployment concern, not a compose-file default.

Every published host port is overridable (see `.env.example`), because a developer machine
frequently already runs a PostgreSQL or a Redis on the conventional port.

**Forbidden:** no schema for the Neo4j projection lives here. The projection is derived and
is built only by module 8 from PostgreSQL facts (ADR-0001); writing it from a migration
would create a graph with no fact behind it.
