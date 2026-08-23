"""Repository ports (ADR-0014).

Reasoning packages depend on these Protocols. They never import a driver, a connection,
or anything under `causalog.persistence` -- only `causalog.orchestration` wires a concrete
adapter to a port. Passing a database handle across a module boundary is a defect
(`CONVENTIONS.md` §6).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from causalog.core.run import RunKey
from causalog.core.types import Entity, Event, Relationship, State, Transition

__all__ = ["AuditSink", "DerivedCache", "FactRepository", "GraphProjection"]


@runtime_checkable
class FactRepository(Protocol):
    """The system of record: facts, dataset versions, run registry (ADR-0001).

    Reads return results in canonical sequence; an unsequenced read breaks determinism
    (`CONVENTIONS.md` §11).
    """

    def register_run(self, key: RunKey) -> str:
        """Persist the run key and return its content-addressed `run_id`."""
        ...

    def events_for_dataset(self, dataset_version: str) -> Iterator[Event]:
        """Yield events sequenced by `(t_earliest, t_latest, event_id)`."""
        ...

    def entities_for_dataset(self, dataset_version: str) -> Iterator[Entity]:
        """Yield entities sequenced by `entity_id`."""
        ...

    def states_for_dataset(self, dataset_version: str) -> Iterator[State]:
        """Yield states sequenced by `state_id`."""
        ...

    def transitions_for_dataset(self, dataset_version: str) -> Iterator[Transition]:
        """Yield transitions sequenced by `transition_id`."""
        ...

    def relationships_for_dataset(self, dataset_version: str) -> Iterator[Relationship]:
        """Yield relationships sequenced by `relationship_id`."""
        ...


@runtime_checkable
class GraphProjection(Protocol):
    """The derived, fully rebuildable graph store (ADR-0001).

    Dropping and rebuilding the whole projection from the fact repository is always safe.
    A write here with no corresponding fact is a defect.
    """

    def projection_version(self) -> str:
        """Return the version currently served; stamped on every query response."""
        ...

    def rebuild_from_facts(self, run_id: str) -> str:
        """Rebuild the projection for a run and return the resulting version."""
        ...

    def content_hash(self, run_id: str) -> str:
        """Return a canonical hash of the projection, for rebuild verification."""
        ...


@runtime_checkable
class DerivedCache(Protocol):
    """Recomputable values only. Losing every entry changes latency, never an answer."""

    def get(self, run_id: str, cache_key: str) -> bytes | None:
        """Return a cached payload, or None. A miss is never an error."""
        ...

    def put(self, run_id: str, cache_key: str, payload: bytes, ttl_seconds: int) -> None:
        """Store a recomputable payload under a run-scoped key."""
        ...


@runtime_checkable
class AuditSink(Protocol):
    """The append-only audit trail (`CONVENTIONS.md` §8), retained apart from logs.

    It must be possible, from an audit record alone, to reconstruct why a confidence
    number has the value it has (the LAW-EVIDENCE hook).
    """

    def record(
        self, run_id: str, auditable_event: str, payload: tuple[tuple[str, str], ...]
    ) -> None:
        """Append one immutable audit entry. Never updates, never deletes."""
        ...
