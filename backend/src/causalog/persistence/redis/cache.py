"""The derived cache (`DerivedCache`). Recomputable values only (ADR-0001).

The rule this adapter exists to make unbreakable: **flushing Redis at any moment must
change latency and never an answer.** `docs/architecture.md` §3.2 states it and a test
asserts it by running a query twice with the cache cleared in between.

Three design choices follow from that rule rather than from convenience:

* **Every key is run-scoped.** `causalog:{run_id}:{cache_key}`. A cached value that
  outlived its run would be served against a different set of inputs, which is the one way
  a cache CAN change an answer.
* **Every entry has a TTL, and it is required rather than defaulted.** An entry with no
  expiry is a value nobody has decided the lifetime of, and it accumulates until somebody
  discovers the cache is the largest thing in the deployment.
* **A miss is never an error and never logged above DEBUG.** A cache that raises on a miss
  has become a source of truth; a cache that warns on one trains people to ignore warnings.

Payloads are bytes. Serialization is the caller's, and it is `core.serialization`'s
canonical form -- a cache that re-serialized would be a second wire format, free to
disagree with the first (`docs/contracts.md` §9 already names two coexisting paths as a
thing to watch).
"""

from __future__ import annotations

import os
from typing import Final, cast

import redis

from causalog.core.errors import ContractViolationError

__all__ = ["KEY_PREFIX", "RedisDerivedCache"]

#: Every key this adapter writes begins here, so a shared Redis is inspectable and a
#: targeted flush is possible without touching another application's keys.
KEY_PREFIX: Final[str] = "causalog"

_URL_ENVIRONMENT_VARIABLE: Final[str] = "CAUSALOG_REDIS_URL"

#: Keys deleted per `drop_run` scan batch. `SCAN` rather than `KEYS`, because `KEYS` blocks
#: the server for the length of the keyspace and a cache must never be able to stall the
#: thing it is speeding up.
_SCAN_BATCH: Final[int] = 500


class RedisDerivedCache:
    """A run-scoped, TTL'd cache of recomputable values."""

    def __init__(self, client: redis.Redis) -> None:
        """Bind the cache to a client."""
        self._client = client

    @classmethod
    def from_environment(cls) -> RedisDerivedCache:
        """Build a cache from `CAUSALOG_REDIS_URL`."""
        url = os.environ.get(_URL_ENVIRONMENT_VARIABLE)
        if not url:
            raise ContractViolationError(
                f"No Redis URL: set {_URL_ENVIRONMENT_VARIABLE}. The cache is optional to "
                "correctness and not optional to configure -- silently running without one "
                "would make a latency regression look like a code change."
            )
        return cls(redis.Redis.from_url(url))

    def get(self, run_id: str, cache_key: str) -> bytes | None:
        """Return a cached payload, or None. A miss is never an error."""
        # `cast` rather than a runtime check: redis-py types its methods as possibly
        # awaitable because one client class covers the sync and async APIs. This client
        # is the synchronous one, constructed here, so the awaitable arm is unreachable --
        # and a runtime isinstance guard would be dead code pretending to be a safeguard.
        value = cast("bytes | None", self._client.get(_key(run_id, cache_key)))
        return value

    def put(self, run_id: str, cache_key: str, payload: bytes, ttl_seconds: int) -> None:
        """Store a recomputable payload under a run-scoped key.

        `ttl_seconds` is required and must be positive. There is deliberately no default
        and no "no expiry" path: an entry nobody has chosen a lifetime for is an entry
        nobody will remove.
        """
        if ttl_seconds <= 0:
            raise ContractViolationError(
                f"TTL {ttl_seconds} is not positive. Every cache entry expires; an entry "
                "with no expiry is a value nobody has decided the lifetime of, and the "
                "cache stops being recomputable state and starts being storage."
            )
        self._client.set(_key(run_id, cache_key), payload, ex=ttl_seconds)

    def drop_run(self, run_id: str) -> int:
        """Evict every entry for a run and return the count. Changes latency only."""
        removed = 0
        pattern = f"{KEY_PREFIX}:{run_id}:*"
        for key in self._client.scan_iter(match=pattern, count=_SCAN_BATCH):
            removed += cast("int", self._client.delete(key))
        return removed


def _key(run_id: str, cache_key: str) -> str:
    """Return the run-scoped key.

    The run is in the key rather than in the value, so a cached entry CANNOT be read back
    under a different run. Putting it in the value would leave the check to a caller, and
    a caller that forgot would serve one run's answer for another.
    """
    if not run_id:
        raise ContractViolationError(
            "A cache key with no run_id would be readable from any run. Every derived "
            "value is scoped to the inputs that produced it (ADR-0013)."
        )
    return f"{KEY_PREFIX}:{run_id}:{cache_key}"
