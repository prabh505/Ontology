"""In-memory implementations of the `core/ports` capabilities.

Every ordering these classes return is produced by an explicit `sorted()` on the canonical
key, never by insertion order. A fake that returned insertion order would make an
unsequenced read pass in the unit suite and fail in the integration one -- which is worse
than not having a fake, because it moves the failure to the slowest place to find it.

Every law the real adapter enforces is enforced here too, with the same message. A fake
that accepted an unevidenced `OBSERVED` fact would make the law tests pass for the wrong
reason.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from causalog.core.errors import ContractViolationError, LawViolationError, ProjectionStaleError
from causalog.core.ports.jobs import JobRecord, JobStatus, StageStatus, StageTransition
from causalog.core.ports.limits import RateLimitVerdict
from causalog.core.ports.persistence import AUDITABLE_ACTIONS
from causalog.core.provenance import ProvenanceClass
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
    "FixedClock",
    "InMemoryAuditSink",
    "InMemoryDerivedCache",
    "InMemoryFactRepository",
    "InMemoryGraphProjection",
    "InMemoryJobStore",
    "InMemoryRateLimiter",
]

#: A closed system period. The real schema uses `'infinity'`; datetime.max is its Python
#: equivalent, and both mean "still believed".
_STILL_BELIEVED = datetime.max.replace(tzinfo=UTC)


@dataclass
class _Belief:
    """One stored artifact and the window over which this system believed it (ADR-0032)."""

    artifact: Any
    dataset_version: str
    system_from: datetime
    system_to: datetime = _STILL_BELIEVED


@dataclass
class InMemoryFactRepository:
    """Facts, the run registry, and run-scoped causal edges, held in dicts."""

    runs: dict[str, Run] = field(default_factory=dict)
    entities: dict[str, tuple[str, Entity]] = field(default_factory=dict)
    events: dict[str, tuple[str, Event]] = field(default_factory=dict)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    evidence_items: dict[str, EvidenceItem] = field(default_factory=dict)
    states: list[_Belief] = field(default_factory=list)
    transitions: list[_Belief] = field(default_factory=list)
    relationships: list[_Belief] = field(default_factory=list)
    causal_edges: dict[str, CausalEdge] = field(default_factory=dict)

    # -- the run registry ---------------------------------------------------

    def register_run(self, key: RunKey, ontology_version: str = "") -> str:
        """Persist the run key and return its content-addressed `run_id`."""
        run_id = key.address()
        self.runs.setdefault(
            run_id,
            Run(run_id=run_id, key=key, created_at=datetime(2026, 1, 1, tzinfo=UTC)),
        )
        return run_id

    def run(self, run_id: str) -> Run | None:
        """Return the registered run, or None."""
        return self.runs.get(run_id)

    # -- writes -------------------------------------------------------------

    def write_evidence_records(self, records: Iterable[EvidenceRecord]) -> int:
        """Persist citations."""
        written = 0
        for record in records:
            if record.evidence_record_id not in self.evidence:
                self.evidence[record.evidence_record_id] = record
                written += 1
        return written

    def write_entities(self, entities: Iterable[Entity], ontology_hash: str = "") -> int:
        """Persist entities, refusing an unevidenced or non-OBSERVED one."""
        written = 0
        for entity in entities:
            if entity.provenance_class is not ProvenanceClass.OBSERVED:
                raise LawViolationError(
                    f"Entity {entity.entity_id} carries provenance "
                    f"{entity.provenance_class.value}. An entity the engine inferred is "
                    "not an entity, it is a claim, and claims are run-scoped artifacts "
                    "(LAW-PROVENANCE, ADR-0013)."
                )
            if not entity.evidence_record_ids:
                raise LawViolationError(
                    f"Entity {entity.entity_id} cites no evidence record. An OBSERVED "
                    "artifact with no citation cannot be audited (LAW-EVIDENCE)."
                )
            if entity.entity_id in self.entities:
                continue
            self.entities[entity.entity_id] = (
                self._dataset_version_of(entity.evidence_record_ids),
                entity,
            )
            written += 1
        return written

    def write_events(self, events: Iterable[Event], ontology_hash: str = "") -> int:
        """Persist events, refusing an unevidenced observation."""
        written = 0
        for event in events:
            if event.provenance_class is ProvenanceClass.OBSERVED and not event.evidence_record_ids:
                raise LawViolationError(
                    f"Event {event.event_id} is OBSERVED and cites no evidence record. "
                    "LAW-EVIDENCE has no exceptions, including for the largest table in "
                    "the system."
                )
            if event.source_record_ref not in event.evidence_record_ids:
                raise ContractViolationError(
                    f"Event {event.event_id} names source_record_ref "
                    f"{event.source_record_ref!r}, which is absent from its evidence "
                    "records. The traceability pointer and the citation set must agree "
                    "(docs/contracts.md §5)."
                )
            if event.event_id in self.events:
                continue
            self.events[event.event_id] = (
                self._dataset_version_of(event.evidence_record_ids),
                event,
            )
            written += 1
        return written

    def write_states(
        self,
        states: Iterable[State],
        dataset_version: str,
        believed_from: datetime | None = None,
    ) -> int:
        """Persist states as a NEW belief. Never edits an existing one (ADR-0032)."""
        written = 0
        for state in states:
            if any(
                belief.artifact.state_id == state.state_id and belief.system_to == _STILL_BELIEVED
                for belief in self.states
            ):
                continue
            self.states.append(
                _Belief(
                    artifact=state,
                    dataset_version=dataset_version,
                    system_from=(
                        believed_from if believed_from is not None else self._next_system_instant()
                    ),
                )
            )
            written += 1
        return written

    def write_transitions(
        self,
        transitions: Iterable[Transition],
        dataset_version: str,
        believed_from: datetime | None = None,
    ) -> int:
        """Persist transitions as a new belief."""
        written = 0
        for transition in transitions:
            if any(
                belief.artifact.transition_id == transition.transition_id
                and belief.system_to == _STILL_BELIEVED
                for belief in self.transitions
            ):
                continue
            self.transitions.append(
                _Belief(
                    artifact=transition,
                    dataset_version=dataset_version,
                    system_from=(
                        believed_from if believed_from is not None else self._next_system_instant()
                    ),
                )
            )
            written += 1
        return written

    def write_relationships(
        self,
        relationships: Iterable[Relationship],
        dataset_version: str,
        believed_from: datetime | None = None,
    ) -> int:
        """Persist structural relationships, refusing `CAUSES`."""
        written = 0
        for relationship in relationships:
            if relationship.relationship_type == "CAUSES":
                raise LawViolationError(
                    f"Relationship {relationship.relationship_id} has type CAUSES. "
                    "Causal edges are a separate, run-scoped artifact produced only by "
                    "the causal engine; a structural store that accepted one would erase "
                    "the inference boundary (docs/contracts.md §5)."
                )
            self.relationships.append(
                _Belief(
                    artifact=relationship,
                    dataset_version=dataset_version,
                    system_from=(
                        believed_from if believed_from is not None else self._next_system_instant()
                    ),
                )
            )
            written += 1
        return written

    def retract_states(self, state_ids: Sequence[str], as_of: datetime) -> int:
        """Close the open system period of each named state (ADR-0032).

        Closes; never removes. What the engine used to believe stays readable, because
        every past conclusion computed against it would otherwise become unauditable.
        """
        targets = set(state_ids)
        closed = 0
        for belief in self.states:
            if belief.artifact.state_id in targets and belief.system_to == _STILL_BELIEVED:
                if as_of <= belief.system_from:
                    raise LawViolationError(
                        f"Closing the system period of {belief.artifact.state_id} at "
                        f"{as_of.isoformat()} would end it before it began "
                        f"({belief.system_from.isoformat()}). A belief cannot end before "
                        "it started (ADR-0032)."
                    )
                belief.system_to = as_of
                closed += 1
        return closed

    def write_causal_edges(self, edges: Iterable[CausalEdge]) -> int:
        """Persist causal edges, refusing an unscoped or unevidenced one."""
        written = 0
        for edge in edges:
            if not edge.run_id:
                raise LawViolationError(
                    f"Causal edge {edge.causal_edge_id} has no run_id. An inferred "
                    "artifact with no run cannot exist -- that is what makes 'inference "
                    "never overwrites observation' structural (ADR-0013)."
                )
            if not edge.evidence:
                raise LawViolationError(
                    f"Causal edge {edge.causal_edge_id} carries no evidence. A causal "
                    "claim nobody can inspect is exactly what LAW-EVIDENCE forbids."
                )
            if edge.causal_edge_id in self.causal_edges:
                continue
            self.causal_edges[edge.causal_edge_id] = edge
            for item in edge.evidence:
                self.evidence_items[item.evidence_item_id] = item
            written += 1
        return written

    def write_evidence_items(self, items: Iterable[EvidenceItem]) -> int:
        """Persist justifications, refusing an item with empty `verification`."""
        written = 0
        for item in items:
            if not item.verification.strip():
                raise LawViolationError(
                    f"Evidence item {item.evidence_item_id} has empty verification. An "
                    "item a reader cannot re-execute is a defect, not a weak item "
                    "(docs/contracts.md §5)."
                )
            if item.evidence_item_id not in self.evidence_items:
                self.evidence_items[item.evidence_item_id] = item
                written += 1
        return written

    # -- reads, every one explicitly sequenced ------------------------------

    def entities_for_dataset(self, dataset_version: str) -> Iterator[Entity]:
        """Yield entities sequenced by `entity_id`."""
        return iter(
            sorted(
                (
                    entity
                    for stored_version, entity in self.entities.values()
                    if stored_version == dataset_version
                ),
                key=lambda entity: entity.entity_id,
            )
        )

    def events_for_dataset(self, dataset_version: str) -> Iterator[Event]:
        """Yield events sequenced by `(t_earliest, t_latest, event_id)`."""
        return iter(
            sorted(
                (
                    event
                    for stored_version, event in self.events.values()
                    if stored_version == dataset_version
                ),
                key=lambda event: (*event.occurred_at.sort_key(), event.event_id),
            )
        )

    def events_for_entity(self, entity_id: str) -> Iterator[Event]:
        """Yield events this entity participated in, in canonical event sequence."""
        return iter(
            sorted(
                (
                    event
                    for _, event in self.events.values()
                    if entity_id in (*event.source_entity_ids, *event.target_entity_ids)
                ),
                key=lambda event: (*event.occurred_at.sort_key(), event.event_id),
            )
        )

    def states_for_dataset(self, dataset_version: str) -> Iterator[State]:
        """Yield currently believed states sequenced by `state_id`."""
        return iter(
            sorted(
                (
                    belief.artifact
                    for belief in self.states
                    if belief.dataset_version == dataset_version
                    and belief.system_to == _STILL_BELIEVED
                ),
                key=lambda state: state.state_id,
            )
        )

    def states_as_believed_at(
        self, dataset_version: str, system_instant: datetime
    ) -> Iterator[State]:
        """Yield the states this system believed at `system_instant` (ADR-0032).

        The predicate is half-open on the upper bound -- `system_from <= t < system_to` --
        so a belief closed at exactly `t` is not returned by a query as of `t`. Including
        it would return two beliefs for one state at the moment of retraction, which
        `core.derivation.current_state` treats as a contradiction in the source.
        """
        return iter(
            sorted(
                (
                    belief.artifact
                    for belief in self.states
                    if belief.dataset_version == dataset_version
                    and belief.system_from <= system_instant < belief.system_to
                ),
                key=lambda state: state.state_id,
            )
        )

    def transitions_for_dataset(self, dataset_version: str) -> Iterator[Transition]:
        """Yield currently believed transitions sequenced by `transition_id`."""
        return iter(
            sorted(
                (
                    belief.artifact
                    for belief in self.transitions
                    if belief.dataset_version == dataset_version
                    and belief.system_to == _STILL_BELIEVED
                ),
                key=lambda transition: transition.transition_id,
            )
        )

    def relationships_for_dataset(self, dataset_version: str) -> Iterator[Relationship]:
        """Yield currently believed relationships sequenced by `relationship_id`."""
        return iter(
            sorted(
                (
                    belief.artifact
                    for belief in self.relationships
                    if belief.dataset_version == dataset_version
                    and belief.system_to == _STILL_BELIEVED
                ),
                key=lambda relationship: relationship.relationship_id,
            )
        )

    def evidence_records(self, evidence_record_ids: Sequence[str]) -> Iterator[EvidenceRecord]:
        """Yield the named citations sequenced by `evidence_record_id`."""
        return iter(
            sorted(
                (
                    self.evidence[identifier]
                    for identifier in set(evidence_record_ids)
                    if identifier in self.evidence
                ),
                key=lambda record: record.evidence_record_id,
            )
        )

    def causal_edges_for_run(self, run_id: str) -> Iterator[CausalEdge]:
        """Yield edges sequenced by `(source_event_id, target_event_id, edge_kind)`."""
        return iter(
            sorted(
                (edge for edge in self.causal_edges.values() if edge.run_id == run_id),
                key=lambda edge: (
                    edge.source_event_id,
                    edge.target_event_id,
                    edge.edge_kind.value,
                ),
            )
        )

    def causal_edges_into(self, run_id: str, target_event_id: str) -> Iterator[CausalEdge]:
        """Yield edges pointing at an effect -- the backward traversal seed."""
        return iter(
            edge
            for edge in self.causal_edges_for_run(run_id)
            if edge.target_event_id == target_event_id
        )

    def causal_edges_out_of(self, run_id: str, source_event_id: str) -> Iterator[CausalEdge]:
        """Yield edges leading away from a cause -- the forward propagation sweep."""
        return iter(
            edge
            for edge in self.causal_edges_for_run(run_id)
            if edge.source_event_id == source_event_id
        )

    def fact_counts(self, dataset_version: str, run_id: str) -> dict[str, int]:
        """Return the per-family counts the projection verification compares against."""
        return {
            "entity": sum(1 for _ in self.entities_for_dataset(dataset_version)),
            "event": sum(1 for _ in self.events_for_dataset(dataset_version)),
            "state": sum(1 for _ in self.states_for_dataset(dataset_version)),
            "transition": sum(1 for _ in self.transitions_for_dataset(dataset_version)),
            "relationship": sum(1 for _ in self.relationships_for_dataset(dataset_version)),
            "causal_edge": sum(1 for _ in self.causal_edges_for_run(run_id)),
        }

    # -- internals ----------------------------------------------------------

    def _dataset_version_of(self, evidence_record_ids: Sequence[str]) -> str:
        versions = sorted(
            {
                self.evidence[identifier].dataset_version
                for identifier in evidence_record_ids
                if identifier in self.evidence
            }
        )
        if len(versions) != 1:
            raise ContractViolationError(
                f"A batch of observed facts cites {len(versions)} dataset versions "
                f"({versions}). One run reads one dataset (docs/architecture.md §2, "
                "module 1); facts spanning two would carry a run_id describing neither."
            )
        return versions[0]

    def _next_system_instant(self) -> datetime:
        """Return a monotonic, deterministic system instant.

        Not `datetime.now()`. A fake that read the wall clock would make every test that
        touches system time non-reproducible, and `CONVENTIONS.md` §11 forbids reading it
        inside the system at all -- time is injected. The counter is derived from how many
        beliefs already exist, so the sequence is a function of the test's own actions.
        """
        recorded = len(self.states) + len(self.transitions) + len(self.relationships)
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=recorded)


@dataclass
class InMemoryGraphProjection:
    """A projection that records what it was asked to hold, and can be compared.

    It stores the token stream rather than a graph, because every property this fake needs
    to exhibit -- idempotence, the content hash, run isolation -- is a property of that
    stream. Building a real graph structure here would be a second graph implementation to
    keep correct, and the one that matters is Neo4j's.
    """

    repository: InMemoryFactRepository
    live: dict[str, tuple[str, str]] = field(default_factory=dict)
    history: dict[str, list[str]] = field(default_factory=dict)

    def projection_version(self, run_id: str) -> str | None:
        """Return the version currently served for a run, or None."""
        entry = self.live.get(run_id)
        return None if entry is None else entry[0]

    def require_version(self, run_id: str, expected_version: str) -> None:
        """Raise `ProjectionStaleError` unless the live version is the one expected."""
        live = self.projection_version(run_id)
        if live != expected_version:
            raise ProjectionStaleError(
                f"Projection for run {run_id} is at {live!r}; {expected_version!r} was "
                "requested. A stale projection is never served as if fresh."
            )

    def rebuild_from_facts(self, run_id: str) -> str:
        """Rebuild and return the resulting version, refusing a determinism regression."""
        run = self.repository.run(run_id)
        if run is None:
            raise ContractViolationError(
                f"No run registered as {run_id!r}. A projection built for an "
                "unregistered run could not be reproduced from its inputs (ADR-0013)."
            )
        content_hash = self.content_hash(run_id)
        previous = self.history.get(run_id)
        if previous and previous[-1] != content_hash:
            raise ContractViolationError(
                f"Rebuilding run {run_id} produced content hash {content_hash!r}; the "
                f"previous build produced {previous[-1]!r}. Identical inputs must produce "
                "identical artifacts, so this is a determinism defect and not a retryable "
                "error (CONVENTIONS.md §11)."
            )
        version = f"gpv:{content_hash}"
        self.history.setdefault(run_id, []).append(content_hash)
        self.live[run_id] = (version, content_hash)
        return version

    def content_hash(self, run_id: str) -> str:
        """Return a canonical hash over the sorted token stream."""
        return hashlib.sha256("\n".join(sorted(self._tokens(run_id))).encode()).hexdigest()[:16]

    def drop_run(self, run_id: str) -> int:
        """Remove one run's inferred elements. Observed structure is untouched."""
        removed = sum(1 for _ in self.repository.causal_edges_for_run(run_id))
        self.live.pop(run_id, None)
        return removed

    def _tokens(self, run_id: str) -> list[str]:
        run = self.repository.run(run_id)
        assert run is not None  # noqa: S101 -- checked by the caller
        dataset_version = run.key.dataset_version
        tokens = [
            f"ent|{entity.entity_id}"
            for entity in self.repository.entities_for_dataset(dataset_version)
        ]
        tokens += [
            f"evt|{event.event_id}" for event in self.repository.events_for_dataset(dataset_version)
        ]
        tokens += [
            f"sta|{state.state_id}" for state in self.repository.states_for_dataset(dataset_version)
        ]
        tokens += [
            f"inf|{edge.edge_kind.value}|{edge.causal_edge_id}"
            for edge in self.repository.causal_edges_for_run(run_id)
        ]
        return tokens


@dataclass
class InMemoryDerivedCache:
    """A run-scoped cache. Losing every entry changes latency, never an answer."""

    entries: dict[tuple[str, str], bytes] = field(default_factory=dict)

    def get(self, run_id: str, cache_key: str) -> bytes | None:
        """Return a cached payload, or None. A miss is never an error."""
        return self.entries.get((run_id, cache_key))

    def put(self, run_id: str, cache_key: str, payload: bytes, ttl_seconds: int) -> None:
        """Store a payload. A non-positive TTL is refused, as in the real adapter."""
        if ttl_seconds <= 0:
            raise ContractViolationError(
                f"TTL {ttl_seconds} is not positive. Every cache entry expires; an entry "
                "with no expiry is a value nobody has decided the lifetime of."
            )
        self.entries[(run_id, cache_key)] = payload

    def drop_run(self, run_id: str) -> int:
        """Evict every entry for a run and return the count."""
        keys = [key for key in self.entries if key[0] == run_id]
        for key in keys:
            del self.entries[key]
        return len(keys)


@dataclass
class InMemoryAuditSink:
    """An append-only audit trail. Entries are readable and never removable."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        *,
        run_id: str | None,
        actor: str,
        action: str,
        target: str,
        target_kind: str,
        correlation_id: str | None = None,
        execution_id: str | None = None,
        before_state: tuple[tuple[str, str], ...] | None = None,
        after_state: tuple[tuple[str, str], ...] | None = None,
        payload: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """Append one entry. There is deliberately no method that removes one."""
        # The PostgreSQL sink refuses an action outside the closed list; until module 16
        # this fake did not, so every audit unit test written against it proved less than
        # it read as. This file's own docstring ("every law the real adapter enforces is
        # enforced here too, with the same message") was false about exactly this law.
        if action not in AUDITABLE_ACTIONS:
            raise ContractViolationError(
                f"{action!r} is not in the closed auditable-action list "
                f"({sorted(AUDITABLE_ACTIONS)}). An audit trail whose vocabulary anyone "
                "may extend at a call site cannot be filtered or reconciled "
                "(CONVENTIONS.md §8)."
            )
        if not actor.strip():
            raise ContractViolationError(
                "An audit entry with no actor cannot discharge prd.md §54: it records "
                "that something happened and not who did it."
            )
        if not target.strip():
            raise ContractViolationError(
                f"Audit action {action!r} names no target. An entry that cannot be "
                "resolved back to the artifact it describes cannot satisfy the "
                "LAW-EVIDENCE hook (CONVENTIONS.md §8)."
            )
        self.entries.append(
            {
                "run_id": run_id,
                "actor": actor,
                "action": action,
                "target": target,
                "target_kind": target_kind,
                "correlation_id": correlation_id,
                "execution_id": execution_id,
                "before_state": before_state,
                "after_state": after_state,
                "payload": payload,
            }
        )


@dataclass
class InMemoryJobStore:
    """The execution ledger in dicts. Transitions are appended and never revised.

    Deliberately mirrors the database's asymmetry rather than smoothing it: the roll-up in
    `_jobs` is mutable, the transitions in `_transitions` are not, and there is no method
    here that removes or rewrites a transition. A fake that allowed one would let a test
    pass that the 0004 trigger would reject in integration -- the slowest place to find it.
    """

    _jobs: dict[str, JobRecord] = field(default_factory=dict)
    _transitions: list[StageTransition] = field(default_factory=list)
    _responses: dict[tuple[str, str, str], tuple[str, int, str]] = field(default_factory=dict)

    def create_job(self, record: JobRecord) -> None:
        """Append a new execution, refusing a duplicate `execution_id`."""
        if record.execution_id in self._jobs:
            raise ContractViolationError(
                f"An execution already exists with execution_id "
                f"{record.execution_id!r}. An execution identifier is minted once per "
                "attempt and never reused; reusing one would merge two attempts' stage "
                "histories into a ledger that describes neither (ADR-0083)."
            )
        self._jobs[record.execution_id] = record

    def job(self, execution_id: str) -> JobRecord | None:
        """Return one execution, or None when no execution has that identifier."""
        return self._jobs.get(execution_id)

    def jobs(self, *, limit: int, dataset_id: str | None = None) -> Iterator[JobRecord]:
        """Yield executions newest first, at most `limit`, optionally one dataset's.

        Sequenced by an explicit `sorted()` on `(created_at, execution_id)`, never by
        insertion: `execution_id` is the tie-break that makes the sequence total, matching
        `SELECT_PIPELINE_JOBS`. Without it two executions created in one clock tick would
        page non-deterministically here and deterministically in PostgreSQL.
        """
        candidates = [
            record
            for record in self._jobs.values()
            if dataset_id is None or record.dataset_id == dataset_id
        ]
        ranked = sorted(
            candidates, key=lambda record: (record.created_at, record.execution_id), reverse=True
        )
        yield from ranked[:limit]

    def job_for_idempotency_key(self, key: str) -> JobRecord | None:
        """Return the execution a previous request with this key created, if any."""
        for record in sorted(self._jobs.values(), key=lambda item: item.execution_id):
            if record.idempotency_key == key:
                return record
        return None

    def set_status(
        self, execution_id: str, status: JobStatus, *, run_id: str | None, at: datetime
    ) -> None:
        """Record an execution's current status, and its `run_id` once one is known."""
        existing = self._jobs.get(execution_id)
        if existing is None:
            raise ContractViolationError(
                f"No execution {execution_id!r} to set status on. A status recorded "
                "against an execution that was never created would leave the ledger "
                "describing an attempt with no beginning."
            )
        # `run_id or existing.run_id`, matching the adapter's COALESCE: a run is learned
        # once and never unlearned by a later status update.
        self._jobs[execution_id] = existing.model_copy(
            update={
                "status": status,
                "run_id": run_id or existing.run_id,
                "updated_at": at,
            }
        )

    def append_transition(self, transition: StageTransition) -> None:
        """Append one stage transition. Never updates and never deletes."""
        if transition.execution_id not in self._jobs:
            raise ContractViolationError(
                f"Stage {transition.stage_id!r} names execution "
                f"{transition.execution_id!r}, which does not exist. The foreign key in "
                "migration 0017 refuses the same thing."
            )
        if transition.status in _EXPLAINED_STAGE_STATUSES and not (transition.detail or "").strip():
            raise ContractViolationError(
                f"Stage {transition.stage_id!r} reached {transition.status.value} with no "
                "detail. A non-successful terminal status that does not say why is an "
                "incident nobody can diagnose from the ledger, which is the only thing "
                "that survives the container (migration 0017)."
            )
        self._transitions.append(transition)

    def transitions(self, execution_id: str) -> Iterator[StageTransition]:
        """Yield every transition for an execution, oldest first."""
        yield from (
            transition
            for transition in self._transitions
            if transition.execution_id == execution_id
        )

    def remember_response(
        self,
        *,
        idempotency_key: str,
        endpoint: str,
        actor: str,
        request_digest: str,
        response_status: int,
        response_body: str,
        correlation_id: str | None = None,
    ) -> None:
        """Store what a mutating request already returned, so a retry replays it."""
        del correlation_id  # recorded by the adapter; not read back by any caller
        self._responses.setdefault(
            (idempotency_key, endpoint, actor),
            (request_digest, response_status, response_body),
        )

    def remembered_response(
        self, *, idempotency_key: str, endpoint: str, actor: str
    ) -> tuple[str, int, str] | None:
        """Return `(request_digest, status, body)` a key already produced, or None."""
        return self._responses.get((idempotency_key, endpoint, actor))


#: The stage statuses migration 0017 requires a `detail` for. Held beside the fake so the
#: constraint is one list rather than two that can drift.
_EXPLAINED_STAGE_STATUSES = frozenset(
    {StageStatus.FAILED, StageStatus.BLOCKED, StageStatus.NOT_RUNNABLE}
)


@dataclass
class InMemoryRateLimiter:
    """A fixed-window counter in a dict, with the same window arithmetic as Redis.

    It does NOT fail open, because it cannot fail: there is no transport to lose. The
    Redis adapter's open failure is a property of its dependency, not of the port, so
    reproducing it here would make a test pass for a reason the real limiter would not
    supply.
    """

    _counts: dict[tuple[str, int], int] = field(default_factory=dict)

    def consume(self, *, bucket: str, limit: int, window_seconds: int) -> RateLimitVerdict:
        """Spend one unit of `bucket`'s budget and report what remains."""
        if limit <= 0 or window_seconds <= 0:
            raise ContractViolationError(
                f"A rate limit needs a positive budget and window; got limit={limit}, "
                f"window_seconds={window_seconds}. A non-positive budget refuses every "
                "request, which is a misconfiguration that would read as an outage."
            )
        key = (bucket, window_seconds)
        used = self._counts.get(key, 0) + 1
        self._counts[key] = used
        return RateLimitVerdict(
            allowed=used <= limit,
            limit=limit,
            remaining=max(0, limit - used),
            retry_after_seconds=0 if used <= limit else window_seconds,
        )


@dataclass
class FixedClock:
    """A `Clock` a test controls (ADR-0014).

    Time is a port precisely so that this can exist: an expiry check, a stage timestamp and
    a run's `created_at` are all testable only when the instant is chosen rather than
    observed. `advance` moves it; nothing here ever reads the ambient clock, which is the
    whole reason the port is not `datetime.now`.

    The default instant is a real, fixed, timezone-aware UTC value rather than `now()`.
    A fake seeded from the wall clock would make a test that formats an instant pass today
    and fail on the day the formatting changes length.
    """

    instant: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    def now_utc(self) -> datetime:
        """Return the currently configured instant."""
        return self.instant

    def advance(self, seconds: float) -> datetime:
        """Move the clock forward and return the new instant."""
        self.instant = self.instant + timedelta(seconds=seconds)
        return self.instant
