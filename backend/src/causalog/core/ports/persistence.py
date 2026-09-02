"""Repository ports (ADR-0014).

Reasoning packages depend on these Protocols. They never import a driver, a connection,
or anything under `causalog.persistence` -- only `causalog.orchestration` wires a concrete
adapter to a port. Passing a database handle across a module boundary is a defect
(`CONVENTIONS.md` §6).

Two properties every implementation owes its callers, stated once here rather than on
every method:

* **Canonical sequence.** Every read yields results in the canonical sequence its
  docstring names. An unsequenced read breaks determinism (`CONVENTIONS.md` §11), and it
  breaks it silently -- two runs differ only in the sequence of a list nobody was
  looking at.
* **The scoping asymmetry.** Observed facts are scoped to `dataset_version`; inferred
  artifacts are scoped to `run_id`. An implementation that let an inference write into a
  dataset-scoped table would defeat LAW-PROVENANCE structurally rather than merely
  permitting a violation (ADR-0013).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Protocol, runtime_checkable

from causalog.core.run import Run, RunKey
from causalog.core.types import (
    CausalEdge,
    Entity,
    Event,
    EvidenceItem,
    EvidenceRecord,
    Relationship,
    State,
    Transition,
)

__all__ = [
    "AuditSink",
    "BulkFactWriter",
    "DerivedCache",
    "FactRepository",
    "GraphProjection",
    "SchemaMigrator",
]


@runtime_checkable
class FactRepository(Protocol):
    """The system of record: facts, dataset versions, run registry (ADR-0001).

    Reads return results in canonical sequence; an unsequenced read breaks determinism
    (`CONVENTIONS.md` §11).
    """

    # -- the run registry ---------------------------------------------------

    def register_run(self, key: RunKey) -> str:
        """Persist the run key and return its content-addressed `run_id`.

        Idempotent: registering an identical key twice returns the same identifier and
        creates no second row. Two executions of one Run are one Run (ADR-0013).
        """
        ...

    def run(self, run_id: str) -> Run | None:
        """Return the registered run, or None. An absent run is not an error here.

        The caller decides what an absent run means: a 404 at the API boundary, a hard
        error in the rebuild, which resolves a `run_id` it was given.
        """
        ...

    # -- observed facts, written once, scoped to a dataset version ----------

    def write_entities(self, entities: Iterable[Entity]) -> int:
        """Persist entities and return the number newly stored.

        Re-writing an identical entity is a no-op, not an error: content addressing means
        the same participant seen twice is one row. A digest collision on *differing*
        payloads is `CRITICAL` and raises (`CONVENTIONS.md` §9).
        """
        ...

    def write_events(self, events: Iterable[Event]) -> int:
        """Persist events and return the number newly stored.

        Refuses an `OBSERVED` event with no evidence record -- LAW-EVIDENCE has no
        exceptions, and an unevidenced observation cannot be audited.
        """
        ...

    def write_states(self, states: Iterable[State]) -> int:
        """Persist states as a new belief, opening a system period for each.

        Never updates an existing state in place. A re-derivation that changes a state
        supersedes it via `retract_states`; overwriting would destroy the interval a past
        conclusion was computed against (ADR-0032).
        """
        ...

    def write_transitions(self, transitions: Iterable[Transition]) -> int:
        """Persist transitions as a new belief, opening a system period for each."""
        ...

    def write_relationships(self, relationships: Iterable[Relationship]) -> int:
        """Persist structural relationships as a new belief.

        Refuses a `CAUSES` relationship type. Causal edges are a separate artifact and are
        run-scoped; a structural store that accepted one would erase the inference
        boundary (`docs/contracts.md` §5).
        """
        ...

    def write_evidence_records(self, records: Iterable[EvidenceRecord]) -> int:
        """Persist citations. The raw source record is never passed here or stored."""
        ...

    def retract_states(self, state_ids: Sequence[str], as_of: str) -> int:
        """Close the open system period of each named state at `as_of`.

        The single sanctioned mutation in the fact store. It records that the engine has
        stopped believing something; it does not remove what the engine believed, because
        every past conclusion computed against it would become unauditable (ADR-0032).

        `as_of` comes from the `Clock` port. Reading the wall clock inside a module is a
        determinism defect (`CONVENTIONS.md` §11).
        """
        ...

    # -- observed facts, read in canonical sequence -------------------------

    def events_for_dataset(self, dataset_version: str) -> Iterator[Event]:
        """Yield events sequenced by `(t_earliest, t_latest, event_id)`."""
        ...

    def entities_for_dataset(self, dataset_version: str) -> Iterator[Entity]:
        """Yield entities sequenced by `entity_id`."""
        ...

    def states_for_dataset(self, dataset_version: str) -> Iterator[State]:
        """Yield currently believed states sequenced by `state_id`.

        Superseded beliefs are excluded. `states_as_believed_at` is how a caller asks for
        a past belief, and asking for one is deliberately a different call: the ordinary
        read must not be able to return stale history by accident.
        """
        ...

    def transitions_for_dataset(self, dataset_version: str) -> Iterator[Transition]:
        """Yield currently believed transitions sequenced by `transition_id`."""
        ...

    def relationships_for_dataset(self, dataset_version: str) -> Iterator[Relationship]:
        """Yield currently believed relationships sequenced by `relationship_id`."""
        ...

    def states_as_believed_at(self, dataset_version: str, system_instant: str) -> Iterator[State]:
        """Yield the states this system believed at `system_instant` (ADR-0032).

        The bi-temporal read. `states_for_dataset` answers "what does the engine believe
        now"; this answers "what did it believe then", which is the question an audit of a
        past conclusion asks.
        """
        ...

    def events_for_entity(self, entity_id: str) -> Iterator[Event]:
        """Yield events this entity participated in, in canonical event sequence."""
        ...

    def evidence_records(self, evidence_record_ids: Sequence[str]) -> Iterator[EvidenceRecord]:
        """Yield the named citations sequenced by `evidence_record_id`."""
        ...

    # -- inferred artifacts, always run-scoped ------------------------------

    def write_causal_edges(self, edges: Iterable[CausalEdge]) -> int:
        """Persist causal edges. Every edge carries a `run_id`; there is no unscoped path.

        Refuses an edge whose evidence is empty (LAW-EVIDENCE) and an edge whose
        provenance is `OBSERVED` (causation is never read from a source record).
        """
        ...

    def write_evidence_items(self, items: Iterable[EvidenceItem]) -> int:
        """Persist justifications. Refuses an item with empty `verification`.

        An item a reader cannot re-execute is a defect, not a weak item
        (`docs/contracts.md` §5).
        """
        ...

    def causal_edges_for_run(self, run_id: str) -> Iterator[CausalEdge]:
        """Yield edges sequenced by `(source_event_id, target_event_id, edge_kind)`."""
        ...

    def causal_edges_into(self, run_id: str, target_event_id: str) -> Iterator[CausalEdge]:
        """Yield edges pointing at an effect -- the backward traversal seed."""
        ...

    def causal_edges_out_of(self, run_id: str, source_event_id: str) -> Iterator[CausalEdge]:
        """Yield edges leading away from a cause -- the forward propagation sweep."""
        ...


@runtime_checkable
class BulkFactWriter(Protocol):
    """The ingestion path, separate from `FactRepository` because its trade is different.

    `FactRepository.write_*` is transactional per call and validates per artifact.
    A bulk load of a whole dataset within the prd.md §55 thirty-second budget cannot pay
    that per-row cost, so it is a distinct port with distinct guarantees:

    * one transaction for the whole load, so a failure leaves no partial dataset;
    * validation happens once, at the boundary, on the typed artifacts -- never skipped,
      only moved;
    * the write is idempotent, so a re-run after a failure is safe.

    Keeping it a separate Protocol means a reasoning module cannot reach for the fast path
    by accident: only ingestion is given one.
    """

    def load_dataset(
        self,
        *,
        dataset_version: str,
        entities: Iterable[Entity],
        events: Iterable[Event],
        evidence_records: Iterable[EvidenceRecord],
    ) -> BulkLoadSummary:
        """Load a whole dataset in one transaction and return what was written."""
        ...


class BulkLoadSummary(Protocol):
    """What a bulk load wrote. Reported in the run summary, never silently discarded."""

    @property
    def entity_count(self) -> int:
        """Entities newly stored."""
        ...

    @property
    def event_count(self) -> int:
        """Events newly stored."""
        ...

    @property
    def evidence_record_count(self) -> int:
        """Citations newly stored."""
        ...

    @property
    def elapsed_seconds(self) -> float:
        """Wall-clock duration, for the prd.md §55 budget. Never an input to reasoning."""
        ...


@runtime_checkable
class GraphProjection(Protocol):
    """The derived, fully rebuildable graph store (ADR-0001).

    Dropping and rebuilding the whole projection from the fact repository is always safe.
    A write here with no corresponding fact is a defect.
    """

    def projection_version(self, run_id: str) -> str | None:
        """Return the version currently served for a run, or None if none is.

        Stamped on every query response so staleness is detectable. A reader asking for a
        version the store is not serving gets `ProjectionStaleError`; it never silently
        receives an older graph (`docs/architecture.md` §3.2).
        """
        ...

    def rebuild_from_facts(self, run_id: str) -> str:
        """Rebuild the projection for a run and return the resulting version.

        Idempotent by construction: the projection is a function of the facts, so two
        rebuilds of one run produce identical content and therefore an identical version.
        A difference is a determinism defect, not a retryable error
        (`docs/architecture.md` §3.3 step 6).
        """
        ...

    def content_hash(self, run_id: str) -> str:
        """Return a canonical hash of the projection, for rebuild verification."""
        ...

    def drop_run(self, run_id: str) -> int:
        """Remove one run's inferred elements and return how many were removed.

        Observed structure is untouched: inferred elements carry a `run_id` and observed
        ones never do, so this cannot reach them. Dropping a run's inferences from the
        *projection* is routine; the corresponding PostgreSQL rows are the record and are
        never deleted.
        """
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

    def drop_run(self, run_id: str) -> int:
        """Evict every entry for a run and return the count. Changes latency only."""
        ...


@runtime_checkable
class AuditSink(Protocol):
    """The append-only audit trail (`CONVENTIONS.md` §8), retained apart from logs.

    It must be possible, from an audit record alone, to reconstruct why a confidence
    number has the value it has (the LAW-EVIDENCE hook).
    """

    def record(
        self,
        *,
        run_id: str | None,
        actor: str,
        action: str,
        target: str,
        target_kind: str,
        correlation_id: str | None,
        execution_id: str | None,
        before_state: tuple[tuple[str, str], ...] | None,
        after_state: tuple[tuple[str, str], ...] | None,
        payload: tuple[tuple[str, str], ...],
    ) -> None:
        """Append one immutable audit entry. Never updates, never deletes.

        `correlation_id` is what prd.md §54 calls a request id; one concept gets one name
        (`CONVENTIONS.md` §8). `before_state` is None for a creation -- a meaningful
        absence, not a missing value.
        """
        ...


@runtime_checkable
class SchemaMigrator(Protocol):
    """Applies and reverses the numbered SQL migration series (ADR-0033).

    A port rather than a script entry point so the migration state is inspectable from a
    test without shelling out, and so `orchestration` can assert the schema is current
    before a run rather than discovering it mid-pipeline.
    """

    def applied_versions(self) -> tuple[str, ...]:
        """Return the applied migration versions, ascending."""
        ...

    def migrate(self, target_version: str | None = None) -> tuple[str, ...]:
        """Apply pending migrations up to `target_version` and return what was applied.

        An applied migration whose file bytes have changed is a hard error naming the
        version -- never a silent skip and never a re-application. An applied migration is
        history; editing one means the database and the repository describe different
        schemas.
        """
        ...

    def rollback(self, target_version: str) -> tuple[str, ...]:
        """Reverse applied migrations down to `target_version` and return what was reversed."""
        ...
