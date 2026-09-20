"""The one place a port meets an adapter (ADR-0014).

Forbidden edge F4 says only `causalog.orchestration` may import `causalog.persistence`, and
within orchestration this is the only module that does. That is deliberate and it is
checkable: "where does this deployment get its database from" is answered by reading one
file, and a reasoning package that acquired a driver would have to route the import through
here to do it.

`Adapters` is a frozen bundle rather than a service locator with lookups. A caller receives
the ports it was given; nothing here can be reconfigured at runtime, and there is no
registry to mutate. The two constructors are the two honest configurations:

* `from_environment()` -- every real adapter, every connection string from the environment.
  It raises if anything is missing, because a partially-configured deployment that starts
  anyway fails later, further from the cause.
* `in_memory()` -- every fake. Not a degraded mode and not a mock: `persistence.memory`'s
  fakes enforce the same laws with the same messages as the real adapters, which is what
  makes a test that passes against them mean something.

**`SystemClock` lives here and nowhere else.** `CONVENTIONS.md` §11 makes `datetime.now()`
inside a reasoning package a determinism defect, and ADR-0014 makes wall-clock access a
port for that reason. Wiring is the layer whose job is to supply the outside world, so this
is the one legal place to read the real clock -- and having exactly one makes the rule
enforceable by inspection rather than by hope.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from causalog.core.ports.clock import Clock
from causalog.core.ports.identity import Authenticator
from causalog.core.ports.jobs import JobStore
from causalog.core.ports.limits import RateLimiter
from causalog.core.ports.persistence import (
    AuditSink,
    DerivedCache,
    FactRepository,
    GraphProjection,
)
from causalog.orchestration.identity import SignedTokenAuthenticator
from causalog.persistence.memory.fakes import (
    InMemoryAuditSink,
    InMemoryDerivedCache,
    InMemoryFactRepository,
    InMemoryGraphProjection,
    InMemoryJobStore,
    InMemoryRateLimiter,
)
from causalog.persistence.neo4j.projection import Neo4jProjection
from causalog.persistence.postgres.audit_sink import PostgresAuditSink
from causalog.persistence.postgres.connection import PostgresConnectionFactory
from causalog.persistence.postgres.fact_repository import PostgresFactRepository
from causalog.persistence.postgres.job_store import PostgresJobStore
from causalog.persistence.redis.cache import RedisDerivedCache
from causalog.persistence.redis.rate_limiter import RedisRateLimiter

__all__ = ["ENVIRONMENT_VARIABLE", "Adapters", "SystemClock", "is_production"]

#: Names the deployment posture. Read by the error layer to decide how much of a failure a
#: response may describe: outside production an operator debugging locally gets the detail,
#: in production a caller gets the taxonomy member and nothing else.
ENVIRONMENT_VARIABLE: Final[str] = "CAUSALOG_ENV"

_PRODUCTION: Final[str] = "production"

#: Where the ontology packs, rule packs and dataset pins live. Configuration, because a
#: deployment may mount them anywhere; derived from this file's location only as a
#: development convenience, which is why the derivation is here and not at a call site.
REPOSITORY_ROOT_VARIABLE: Final[str] = "CAUSALOG_REPOSITORY_ROOT"


def is_production() -> bool:
    """Return whether this process is running as production.

    Defaults to **True** when the variable is unset, and the direction of that default is
    the point. An unset variable most likely means somebody deployed without setting it, and
    the failure modes are asymmetric: a production deployment that accidentally reveals
    internals is a security incident, while a development box that accidentally hides them
    costs one environment variable. The safe default is the quiet one.
    """
    return os.environ.get(ENVIRONMENT_VARIABLE, _PRODUCTION).strip().lower() == _PRODUCTION


class SystemClock:
    """The real clock. The only implementation in the distribution that reads it."""

    def now_utc(self) -> datetime:
        """Return the current instant, timezone-aware, in UTC."""
        return datetime.now(UTC)


@dataclass(frozen=True)
class Adapters:
    """Every capability the pipeline and the API need from the outside world.

    `projection`, `cache` and `limiter` are optional and the rest are not, and that split is
    a statement about what this system can do without.

    * No `GraphProjection` means modules 7 and 8 have not run, which is the state of this
      repository today -- so an absent projection is the normal case, not a degraded one,
      and the graph endpoints report `NOT_RUNNABLE` rather than failing.
    * No `DerivedCache` means queries recompute. `docs/architecture.md` §3.2 point 5
      guarantees that changes latency and never an answer, so a cache that must be present
      for correctness would contradict the guarantee it exists under.
    * No `RateLimiter` means requests are not throttled. An availability control that fails
      open (its own module says so) cannot coherently be required for the process to start.

    `facts`, `audit`, `jobs`, `clock` and `authenticator` have no such story. A run with no
    fact repository has nowhere to put facts; one with no audit sink cannot discharge
    prd.md §54; one with no authenticator serves inferences to unidentified callers.
    """

    facts: FactRepository
    audit: AuditSink
    jobs: JobStore
    clock: Clock
    authenticator: Authenticator
    repository_root: Path
    projection: GraphProjection | None = None
    cache: DerivedCache | None = None
    limiter: RateLimiter | None = None

    @classmethod
    def from_environment(cls) -> Adapters:
        """Build every real adapter from environment configuration.

        The projection, the cache and the limiter are built only when their configuration is
        present. Everything else raises on absence, from the adapter's own constructor,
        naming the variable -- which is why there is no validation block here duplicating
        those messages in a second place that could disagree with them.
        """
        factory = PostgresConnectionFactory()
        clock = SystemClock()
        facts = PostgresFactRepository(factory)
        projection: GraphProjection | None = None
        if os.environ.get("CAUSALOG_NEO4J_URI"):
            # The projection is handed the repository and the connection factory because it
            # is DERIVED: a rebuild streams facts out of PostgreSQL (ADR-0001), so it cannot
            # be constructed without a way back to the system of record.
            projection = Neo4jProjection.from_environment(facts, factory)
        cache: DerivedCache | None = None
        limiter: RateLimiter | None = None
        if os.environ.get("CAUSALOG_REDIS_URL"):
            cache = RedisDerivedCache.from_environment()
            limiter = RedisRateLimiter.from_environment()
        return cls(
            facts=facts,
            repository_root=_repository_root(),
            audit=PostgresAuditSink(factory),
            jobs=PostgresJobStore(factory),
            clock=clock,
            authenticator=SignedTokenAuthenticator.from_environment(clock),
            projection=projection,
            cache=cache,
            limiter=limiter,
        )

    @classmethod
    def in_memory(
        cls,
        *,
        clock: Clock,
        authenticator: Authenticator,
        repository_root: Path | None = None,
    ) -> Adapters:
        """Build every fake. The clock and the authenticator are injected.

        Those two are injected rather than defaulted because both are exactly what a test
        needs to control: a test that cannot move the clock cannot assert that an expired
        credential is refused, and one that cannot choose a principal cannot exercise a
        permission matrix.
        """
        facts = InMemoryFactRepository()
        return cls(
            facts=facts,
            repository_root=repository_root or _repository_root(),
            audit=InMemoryAuditSink(),
            jobs=InMemoryJobStore(),
            clock=clock,
            authenticator=authenticator,
            # Handed the same repository, for the reason the real projection is handed the
            # real one: a projection is DERIVED (ADR-0001), and a fake that could be built
            # without a source of facts would model something the real one cannot be.
            projection=InMemoryGraphProjection(facts),
            cache=InMemoryDerivedCache(),
            limiter=InMemoryRateLimiter(),
        )


def _repository_root() -> Path:
    """Return the directory holding `ontology/`, `rule_engine/` and `datasets/`.

    From the environment when set, otherwise derived from this file's location. The
    derivation is a development convenience and is deliberately the fallback: a container
    that mounts the packs elsewhere sets the variable, and a deployment that silently
    resolved to a path inside the installed distribution would read packs nobody edited.
    """
    configured = os.environ.get(REPOSITORY_ROOT_VARIABLE)
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4]
