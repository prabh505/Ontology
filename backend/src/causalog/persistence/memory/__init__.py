"""In-memory adapters for fast tests (ADR-0014).

These are FAKES, not mocks. A mock asserts that a call happened; a fake behaves. The
difference matters here because the properties worth testing are behavioural -- canonical
sequencing, the scoping asymmetry, the append-only refusal, the bi-temporal supersession
-- and a mock cannot exhibit any of them. A test suite built on mocks would pass against a
repository that returned rows in insertion order, and that is the exact defect
`CONVENTIONS.md` §11 exists to prevent.

The obvious risk with a fake is drift: it passes, the real adapter does not, and nobody
notices until the integration job. That is handled by construction rather than by
discipline -- `tests/unit/persistence/test_repository_contract.py` is parameterized over
BOTH this and the PostgreSQL adapter, so a behaviour these two do not share is a failure
in one of them.
"""

from causalog.persistence.memory.fakes import (
    InMemoryAuditSink,
    InMemoryDerivedCache,
    InMemoryFactRepository,
    InMemoryGraphProjection,
)

__all__ = [
    "InMemoryAuditSink",
    "InMemoryDerivedCache",
    "InMemoryFactRepository",
    "InMemoryGraphProjection",
]
