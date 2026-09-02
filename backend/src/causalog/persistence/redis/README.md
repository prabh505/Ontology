# `causalog.persistence.redis`

**Layer rank:** none — this package is a driven adapter, not a layer.

## Single responsibility

Cache recomputable derived values keyed by `run_id`.

## The rule this package exists to make unbreakable

**Flushing Redis at any moment must change latency and never an answer.** Three consequences,
each enforced rather than intended:

- Every key is `causalog:{run_id}:{cache_key}`. The run is in the *key*, not the value, so a
  cached entry cannot be read back under a different run.
- Every entry carries a TTL, and it is a required argument. There is no default and no
  "no expiry" path: an entry nobody has chosen a lifetime for is one nobody will remove.
- A miss is never an error and never logged above `DEBUG`. A cache that raises on a miss has
  become a source of truth; one that warns on a miss trains people to ignore warnings.

`drop_run` uses `SCAN`, never `KEYS`: `KEYS` blocks the server for the length of the
keyspace, and a cache must never be able to stall the thing it is speeding up.

## Forbidden dependencies

Every reasoning package. May never be a source of truth.

See `docs/architecture.md` §3 for the storage boundary.
