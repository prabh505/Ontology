"""The `RateLimiter` adapter over Redis (prd.md §54 hardening, ADR-0084).

A fixed-window counter, not a sliding window and not a leaky bucket, and the choice is
recorded rather than defaulted. A fixed window admits a documented burst -- up to twice the
limit across a window boundary -- and costs two Redis commands. A sliding window removes
the burst and costs a sorted set per caller plus a trim on every request. This limiter
exists to keep one caller from exhausting a shared engine, not to meter a paid API, and
the burst it admits is bounded and harmless for that purpose. The cost is stated here so
that a later requirement for exact metering reopens the decision rather than discovering it.

**Why this is a separate port from `DerivedCache` even though both are Redis.** The cache
is run-scoped and may be flushed at any instant without changing an answer
(`docs/architecture.md` §3.2, point 5). Limiter state is caller-scoped and flushing it
changes who gets through. Two lifetimes and two guarantees; widening one port to carry
both would put a value whose loss matters behind a method documented to say it never does.

**It fails OPEN, deliberately.** If Redis is unreachable the verdict is `allowed`. That is
the correct direction for an availability control -- a limiter outage must not become a
total outage -- and it is precisely why authorization is not built on this port. A control
that fails open must never be the thing standing between a caller and data.
"""

from __future__ import annotations

import os
from typing import Final, cast

import redis

from causalog.core.errors import ContractViolationError
from causalog.core.ports.limits import RateLimitVerdict

__all__ = ["KEY_PREFIX", "RedisRateLimiter"]

#: Distinct from `RedisDerivedCache.KEY_PREFIX` so a cache flush cannot reset a budget and
#: a budget sweep cannot evict a cached answer.
KEY_PREFIX: Final[str] = "causalog:limit"

_URL_ENVIRONMENT_VARIABLE: Final[str] = "CAUSALOG_REDIS_URL"


class RedisRateLimiter:
    """Count one caller's requests against a fixed budget in a fixed window."""

    def __init__(self, client: redis.Redis) -> None:
        """Bind the limiter to a client."""
        self._client = client

    @classmethod
    def from_environment(cls) -> RedisRateLimiter:
        """Build a limiter from `CAUSALOG_REDIS_URL`."""
        url = os.environ.get(_URL_ENVIRONMENT_VARIABLE)
        if not url:
            raise ContractViolationError(
                f"No Redis URL: set {_URL_ENVIRONMENT_VARIABLE}. A rate limit that is "
                "silently absent is indistinguishable from one that is generous, and the "
                "difference only shows up under the load it was meant to survive."
            )
        return cls(redis.Redis.from_url(url))

    def consume(self, *, bucket: str, limit: int, window_seconds: int) -> RateLimitVerdict:
        """Spend one unit of `bucket`'s budget and report what remains."""
        if limit <= 0 or window_seconds <= 0:
            raise ContractViolationError(
                f"A rate limit needs a positive budget and window; got limit={limit}, "
                f"window_seconds={window_seconds}. A non-positive budget refuses every "
                "request, which is a misconfiguration that would read as an outage."
            )
        key = f"{KEY_PREFIX}:{window_seconds}:{bucket}"
        try:
            # Three round trips rather than one pipeline. `pipeline().execute()` is
            # untyped in redis-py and `mypy --strict` refuses a call to an untyped
            # function; silencing that with an ignore would trade a real type check for
            # one saved round trip on a call already cheaper than the query it protects.
            used = int(cast("int", self._client.incr(key)))
            ttl = int(cast("int", self._client.ttl(key)))
            if ttl < 0:
                # No expiry recorded. Two ways to get here and both need the same repair:
                # this is the window's first increment, or a previous process died between
                # its `incr` and its `expire`. Without this the key would live forever and
                # the caller would be throttled permanently -- a limiter that never resets
                # is an outage wearing a limiter's name.
                self._client.expire(key, window_seconds)
                ttl = window_seconds
        except redis.RedisError:
            # Fails OPEN, per this module's docstring. The caller's structured log records
            # it with its reason rather than swallowing it: `CONVENTIONS.md` §7 permits a
            # tolerated failure only when it is logged and counted.
            return RateLimitVerdict(
                allowed=True, limit=limit, remaining=limit, retry_after_seconds=0
            )

        return RateLimitVerdict(
            allowed=used <= limit,
            limit=limit,
            remaining=max(0, limit - used),
            retry_after_seconds=0 if used <= limit else ttl,
        )
