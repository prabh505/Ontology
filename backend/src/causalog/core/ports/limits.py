"""`RateLimiter` -- the request budget one caller may spend in a window (prd.md §54).

Separate from `DerivedCache` deliberately, though both are served by Redis today. The
cache is run-scoped and may be flushed at any moment without changing an answer
(`docs/architecture.md` §3.2, point 5); a rate limiter is caller-scoped and flushing it
changes who is allowed through. Two lifetimes, two guarantees, two ports -- the same
reasoning that gave `BulkFactWriter` its own port rather than widening `FactRepository`.

Losing limiter state fails OPEN (a caller gets a fresh budget), which is the correct
failure direction for a availability control and the wrong one for an authorization
control. That is exactly why authorization is not implemented with this port.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

__all__ = ["RateLimitVerdict", "RateLimiter"]


class RateLimitVerdict(BaseModel):
    """What a limiter decided, with the numbers a caller needs to act on it.

    `retry_after_seconds` is present whenever `allowed` is false. A 429 that does not say
    when to come back leaves a client to guess, and every client guesses the same wrong
    thing at the same moment.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


@runtime_checkable
class RateLimiter(Protocol):
    """Count one caller's requests against a fixed budget in a fixed window."""

    def consume(self, *, bucket: str, limit: int, window_seconds: int) -> RateLimitVerdict:
        """Spend one unit of `bucket`'s budget and report what remains.

        `bucket` identifies the caller and the class of endpoint together, so that an
        expensive simulation endpoint and a cheap metadata read do not share a budget.
        """
        ...
