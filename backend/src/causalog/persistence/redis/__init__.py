"""Redis adapter: the derived cache (ADR-0001).

Recomputable values only, every key scoped by `run_id`, every entry with a TTL. Flushing
this store changes latency and never an answer.
"""

from causalog.persistence.redis.cache import KEY_PREFIX, RedisDerivedCache

__all__ = ["KEY_PREFIX", "RedisDerivedCache"]
