"""The query cache: recomputable values only, keyed by run and query, invalidated by run.

ADR-0001 is the constraint and `docs/architecture.md` §3.2 point 5 is the test: **flushing
Redis at any moment must change latency and never an answer.** Everything here follows
from that one sentence.

* A key is `run_id` plus a digest of the query name and its arguments. The run is what
  makes a cached value meaningful -- the same question against different inputs is a
  different question -- and it is also what makes invalidation possible, because
  `DerivedCache.drop_run` exists.
* Only *derived* answers are cached. A fact read is not, because a fact read is already
  the cheap path and caching it would put a copy of the system of record behind a store
  documented to be losable.
* Every entry carries a TTL, required rather than defaulted, for the reason the Redis
  adapter gives: an entry nobody has decided the lifetime of accumulates until somebody
  discovers the cache is the largest thing in the deployment.

**Invalidation is explicit and has exactly three triggers**, named here so a fourth is a
deliberate addition rather than a discovery: a pipeline execution starts against a run, a
run's inferred artifacts are deleted, and the graph projection is rebuilt. Each of those
can change what a derived answer would be, and each calls `invalidate_run`. Nothing else
in this distribution may.
"""

from __future__ import annotations

from typing import Final

from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_pairs,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.ports.persistence import DerivedCache

__all__ = [
    "DEFAULT_TTL_SECONDS",
    "cache_key",
    "invalidate_run",
    "read_cached",
    "write_cached",
]

#: One hour. Long enough that a session of related queries shares its work, short enough
#: that an entry nobody invalidated cannot outlive the deployment that produced it. A run
#: is immutable by construction (ADR-0013), so this TTL is a storage bound and never a
#: correctness one -- correctness is `invalidate_run`'s job.
DEFAULT_TTL_SECONDS: Final[int] = 3600


def cache_key(query_name: str, parameters: tuple[tuple[str, str], ...]) -> str:
    """Return the content address of one query against one run.

    The `run_id` is deliberately NOT part of this digest: the `DerivedCache` port scopes by
    run already, and folding it in twice would make a key that says the same thing in two
    places -- which is how a partial invalidation happens, where one scoping is cleared and
    the other is not.

    Parameters are canonicalized through `core.identifiers` rather than formatted here, so
    a key cannot depend on dict sequence, float formatting, or interpreter hash seed. Two
    callers asking the same question in different argument sequence get one key, which is
    the whole point of a content address.
    """
    return digest(
        IdentifierPrefix.RUN,
        canonical_payload(canonical_text(query_name), canonical_pairs(parameters)),
    )


def read_cached(cache: DerivedCache | None, run_id: str, key: str) -> bytes | None:
    """Return a cached payload, or None. A miss is never an error, and nor is no cache.

    `cache is None` is a supported configuration, not a degraded one: the in-process test
    wiring and the determinism harness both run without one, and a cache whose absence
    raised would make the thing that must not affect answers able to stop them.
    """
    if cache is None:
        return None
    return cache.get(run_id, key)


def write_cached(
    cache: DerivedCache | None,
    run_id: str,
    key: str,
    payload: bytes,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> None:
    """Store a recomputable payload against a run. A no-op when no cache is wired."""
    if cache is None:
        return
    cache.put(run_id, key, payload, ttl_seconds)


def invalidate_run(cache: DerivedCache | None, run_id: str) -> int:
    """Drop every cached answer for a run. Returns how many entries were removed.

    The count is returned rather than discarded because it is the only evidence that an
    invalidation happened: a cache that was already empty and a cache that was never asked
    are indistinguishable from the caller's side otherwise, and the second is a defect.
    """
    if cache is None:
        return 0
    return cache.drop_run(run_id)
