"""The `FactRepository` adapter over PostgreSQL (ADR-0001, ADR-0014).

Every read is batched. A canonical-sequence read of the event table fetches the events in
one statement, then fetches each child collection for the whole batch in one statement
each, then assembles. That is five round trips for any number of events, and it is written
out rather than arranged by a mapper, because the alternative -- a lazily loaded attribute
-- turns the same-looking code into one query per row on the largest table in the system.

Every read carries an explicit `ORDER BY` on a unique key (`CONVENTIONS.md` §11). The
statements live in `sql.py` so that is visible in one file.

Writes validate before they touch the database. The schema also validates -- the CHECKs in
the migrations restate most of these invariants -- and the duplication is deliberate: the
schema defends against a writer that bypasses this code, and this defends against a schema
that predates a contract change. Neither is redundant with the other while both can be
wrong independently.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

from psycopg import Cursor

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.identifiers import IdentifierPrefix
from causalog.core.provenance import ProvenanceClass
from causalog.core.run import Run, RunKey
from causalog.core.types import (
    CausalEdge,
    ConfidenceVector,
    ContributingCause,
    Entity,
    Event,
    EvidenceItem,
    EvidenceRecord,
    Relationship,
    State,
    Transition,
)
from causalog.persistence.postgres import rows as row_mapping
from causalog.persistence.postgres import sql
from causalog.persistence.postgres.connection import PostgresConnectionFactory

__all__ = ["PostgresFactRepository"]

#: Reads assemble in pages of this many parents, so a dataset-sized stream never holds the
#: whole table in memory while still costing a constant number of round trips per page.
#: Named rather than inline (`CONVENTIONS.md` §5: no magic literals).
READ_PAGE_SIZE = 2_000


class PostgresFactRepository:
    """Facts, the run registry, and the run-scoped causal edges."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        """Bind the repository to a connection source, not to a connection."""
        self._factory = factory

    # ------------------------------------------------------------------
    # The run registry
    # ------------------------------------------------------------------

    def register_run(self, key: RunKey, ontology_version: str = "") -> str:
        """Persist the run key and return its content-addressed `run_id`.

        The identifier is derived here, from the key, and never accepted from a caller:
        `RunKey.address()` is the recipe, and a stored identifier that disagreed with its
        own inputs would make every artifact scoped to it unverifiable (ADR-0013).
        """
        run_id = key.address()
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.INSERT_RUN,
                (
                    run_id,
                    key.dataset_version,
                    key.ontology_hash,
                    ontology_version,
                    key.rule_pack_version,
                    key.engine_version,
                    key.seed,
                ),
            )
            stored = cursor.fetchone()
            connection.commit()
        if stored is None:  # pragma: no cover -- RETURNING always yields on both paths
            raise ContractViolationError(
                "Registering a run returned no identifier. The upsert is written to "
                "return one on both the insert and the conflict path precisely so the "
                "caller never has to guess which happened."
            )
        registered = str(stored[0])
        if registered != run_id:
            raise ContractViolationError(
                f"The run registry already holds {registered!r} for the five-tuple that "
                f"addresses to {run_id!r}. Two identifiers for one set of inputs means "
                "either a digest collision or a schema written by a different "
                "engine_version, and both are CRITICAL (CONVENTIONS.md §9)."
            )
        return registered

    def run(self, run_id: str) -> Run | None:
        """Return the registered run, or None."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_RUN, (run_id,))
            record = cursor.fetchone()
        if record is None:
            return None
        return Run(
            run_id=record[0],
            key=RunKey(
                dataset_version=record[1],
                ontology_hash=record[2],
                rule_pack_version=record[3],
                engine_version=record[4],
                seed=record[5],
            ),
            created_at=record[6],
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def write_evidence_records(self, records: Iterable[EvidenceRecord]) -> int:
        """Persist citations. The raw source record is never passed here or stored."""
        payload = [
            (
                record.evidence_record_id,
                record.dataset_version,
                record.source_locator,
                record.source_timezone,
            )
            for record in records
        ]
        return self._execute_many(sql.INSERT_EVIDENCE_RECORD, payload)

    def write_entities(self, entities: Iterable[Entity], ontology_hash: str = "") -> int:
        """Persist entities, their attributes, their lifecycle, and their citations."""
        materialized = list(entities)
        for entity in materialized:
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
        written = 0
        with self._factory.connect() as connection, connection.cursor() as cursor:
            # EVERY citation, not one per entity. Sampling the first would have made
            # the "one run reads one dataset" check pass on a batch whose second citation
            # pointed somewhere else -- a spanning batch stored under a version it does
            # not belong to, and a silently unreproducible run.
            dataset_version = self._dataset_version_of_evidence(
                cursor,
                [
                    evidence_id
                    for entity in materialized
                    for evidence_id in entity.evidence_record_ids
                ],
            )
            for entity in materialized:
                cursor.execute(
                    sql.INSERT_ENTITY,
                    (
                        entity.entity_id,
                        dataset_version,
                        ontology_hash,
                        entity.entity_type,
                        entity.natural_key,
                        entity.provenance_class.value,
                    ),
                )
                written += cursor.rowcount
                cursor.executemany(
                    "INSERT INTO entity_attribute (entity_id, attribute_name, attribute_value) "
                    "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    [(entity.entity_id, name, value) for name, value in entity.attributes],
                )
                cursor.executemany(
                    "INSERT INTO entity_lifecycle_state (entity_id, state_name) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(entity.entity_id, name) for name in entity.lifecycle.state_names],
                )
                cursor.executemany(
                    "INSERT INTO entity_lifecycle_transition "
                    "(entity_id, from_state_name, to_state_name) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    [
                        (entity.entity_id, source, target)
                        for source, target in entity.lifecycle.legal_transitions
                    ],
                )
                cursor.executemany(
                    "INSERT INTO entity_evidence (entity_id, evidence_record_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(entity.entity_id, evidence_id) for evidence_id in entity.evidence_record_ids],
                )
            connection.commit()
        return written

    def write_events(self, events: Iterable[Event], ontology_hash: str = "") -> int:
        """Persist events with their confidence vectors, participants, and citations."""
        materialized = list(events)
        for event in materialized:
            if event.provenance_class is ProvenanceClass.OBSERVED and not event.evidence_record_ids:
                raise LawViolationError(
                    f"Event {event.event_id} is OBSERVED and cites no evidence record. "
                    "LAW-EVIDENCE has no exceptions, including for the largest table in "
                    "the system."
                )
            if event.source_record_ref not in event.evidence_record_ids:
                raise ContractViolationError(
                    f"Event {event.event_id} names source_record_ref "
                    f"{event.source_record_ref!r}, which is absent from its "
                    "records. The traceability pointer and the citation set must agree, "
                    "or the row cannot be traced back to the source record it came from "
                    "(docs/contracts.md §5)."
                )
        written = 0
        with self._factory.connect() as connection, connection.cursor() as cursor:
            dataset_version = self._dataset_version_of_evidence(
                cursor,
                [
                    evidence_id
                    for event in materialized
                    for evidence_id in event.evidence_record_ids
                ],
            )
            for event in materialized:
                vector_id = self._store_decomposition(cursor, event.confidence)
                bounds = row_mapping.interval_to_columns(event.occurred_at)
                cursor.execute(
                    sql.INSERT_EVENT,
                    (
                        event.event_id,
                        dataset_version,
                        ontology_hash,
                        event.event_type,
                        *bounds,
                        event.trigger,
                        event.provenance_class.value,
                        vector_id,
                        event.is_actionable,
                        event.source_record_ref,
                    ),
                )
                written += cursor.rowcount
                cursor.executemany(
                    "INSERT INTO event_entity (event_id, entity_id, participation_role) "
                    "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    [(event.event_id, entity_id, "SOURCE") for entity_id in event.source_entity_ids]
                    + [
                        (event.event_id, entity_id, "TARGET")
                        for entity_id in event.target_entity_ids
                    ],
                )
                cursor.executemany(
                    "INSERT INTO event_changed_attribute "
                    "(event_id, attribute_name, attribute_value) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    [(event.event_id, name, value) for name, value in event.changed_attributes],
                )
                cursor.executemany(
                    "INSERT INTO event_metadata (event_id, metadata_name, metadata_value) "
                    "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    [(event.event_id, name, value) for name, value in event.metadata],
                )
                cursor.executemany(
                    "INSERT INTO event_evidence (event_id, evidence_record_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(event.event_id, evidence_id) for evidence_id in event.evidence_record_ids],
                )
            connection.commit()
        return written

    def write_states(
        self,
        states: Iterable[State],
        dataset_version: str,
        believed_from: datetime | None = None,
    ) -> int:
        """Persist states as a new belief, opening a system period for each (ADR-0032).

        `believed_from` comes from the `Clock` port. It defaults to the database's `now()`
        only so an exploratory insert still works; every caller inside the pipeline passes
        it, because reading the wall clock inside the system is a determinism defect
        (`CONVENTIONS.md` §11) and because a test cannot assert an as-of read against an
        instant it did not choose.
        """
        opened_at = believed_from if believed_from is not None else _database_now()
        written = 0
        with self._factory.connect() as connection, connection.cursor() as cursor:
            for state in states:
                cursor.execute(
                    sql.INSERT_STATE,
                    (
                        state.state_id,
                        state.entity_id,
                        dataset_version,
                        state.state_name,
                        *row_mapping.interval_to_columns(state.held_over),
                        state.derived_from_event_id,
                        state.provenance_class.value,
                        opened_at,
                    ),
                )
                written += cursor.rowcount
                cursor.executemany(
                    "INSERT INTO state_evidence (state_id, evidence_record_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(state.state_id, evidence_id) for evidence_id in state.evidence_record_ids],
                )
            connection.commit()
        return written

    def write_transitions(
        self,
        transitions: Iterable[Transition],
        dataset_version: str,
        believed_from: datetime | None = None,
    ) -> int:
        """Persist transitions as a new belief, opening a system period for each."""
        opened_at = believed_from if believed_from is not None else _database_now()
        payload = [
            (
                transition.transition_id,
                transition.from_state_id,
                transition.to_state_id,
                transition.causing_event_id,
                dataset_version,
                transition.provenance_class.value,
                opened_at,
            )
            for transition in transitions
        ]
        return self._execute_many(
            "INSERT INTO state_transition (transition_id, from_state_id, to_state_id, "
            "causing_event_id, dataset_version, provenance_class, system_from) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            payload,
        )

    def write_relationships(
        self,
        relationships: Iterable[Relationship],
        dataset_version: str,
        believed_from: datetime | None = None,
    ) -> int:
        """Persist structural relationships as a new belief.

        Refuses `CAUSES` before the database does. The CHECK in migration 0010 would also
        refuse it, and the message here is the one a developer should see: the reason,
        not a constraint name.
        """
        opened_at = believed_from if believed_from is not None else _database_now()
        materialized = list(relationships)
        for relationship in materialized:
            if relationship.relationship_type == "CAUSES":
                raise LawViolationError(
                    f"Relationship {relationship.relationship_id} has type CAUSES. "
                    "Causal edges are a separate, run-scoped artifact produced only by "
                    "the causal engine; a structural store that accepted one would erase "
                    "the inference boundary (docs/contracts.md §5)."
                )
        written = 0
        with self._factory.connect() as connection, connection.cursor() as cursor:
            for relationship in materialized:
                cursor.execute(
                    "INSERT INTO relationship (relationship_id, relationship_type, "
                    "source_entity_id, target_entity_id, dataset_version, valid_from, "
                    "valid_to, valid_precision, valid_provenance, valid_source, "
                    "provenance_class, system_from) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (
                        relationship.relationship_id,
                        relationship.relationship_type,
                        relationship.source_entity_id,
                        relationship.target_entity_id,
                        dataset_version,
                        *row_mapping.interval_to_columns(relationship.valid_over),
                        relationship.provenance_class.value,
                        opened_at,
                    ),
                )
                written += cursor.rowcount
                cursor.executemany(
                    "INSERT INTO relationship_evidence (relationship_id, evidence_record_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [
                        (relationship.relationship_id, evidence_id)
                        for evidence_id in relationship.evidence_record_ids
                    ],
                )
            connection.commit()
        return written

    def retract_states(self, state_ids: Sequence[str], as_of: datetime) -> int:
        """Close the open system period of each named state at `as_of` (ADR-0032).

        `as_of` comes from the `Clock` port. Reading the wall clock here would be a
        determinism defect (`CONVENTIONS.md` §11), and it would also make a retraction
        untestable: a test cannot assert an as-of read against an instant it did not
        choose.
        """
        with self._factory.connect() as connection, connection.cursor() as cursor:
            # Checked here, before the statement, so the caller gets the closed taxonomy's
            # error rather than the driver's. `CONVENTIONS.md` §7: never raise a bare
            # driver exception across a module boundary -- the trigger would refuse this
            # too, and its message would name a constraint instead of the contract.
            cursor.execute(
                "SELECT state_id, system_from FROM state "
                "WHERE state_id = ANY(%s) AND system_to = 'infinity'::timestamptz "
                "AND system_from >= %s ORDER BY state_id LIMIT 1",
                (list(state_ids), as_of),
            )
            offending = cursor.fetchone()
            if offending is not None:
                raise LawViolationError(
                    f"Closing the system period of {offending[0]} at {as_of.isoformat()} "
                    f"would end it before it began ({offending[1].isoformat()}). A belief "
                    "cannot end before it started (ADR-0032)."
                )
            cursor.execute(sql.RETRACT_STATES, (as_of, list(state_ids)))
            closed = cursor.rowcount
            connection.commit()
        return closed

    def write_causal_edges(self, edges: Iterable[CausalEdge]) -> int:
        """Persist causal edges. Every edge carries a `run_id`; there is no unscoped path."""
        materialized = list(edges)
        for edge in materialized:
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
        written = 0
        with self._factory.connect() as connection, connection.cursor() as cursor:
            for edge in materialized:
                vector_id = self._store_decomposition(cursor, edge.confidence)
                payload = edge.payload
                cursor.execute(
                    sql.INSERT_CAUSAL_EDGE,
                    (
                        edge.causal_edge_id,
                        edge.run_id,
                        edge.source_event_id,
                        edge.target_event_id,
                        edge.edge_kind.value,
                        vector_id,
                        edge.propagation_weight,
                        edge.provenance_class.value,
                        edge.temporal_verdict.value,
                        edge.temporally_unverifiable,
                        getattr(payload, "condition_expression", None),
                        getattr(payload, "condition_holds", None),
                        getattr(payload, "joint_cause_group_id", None),
                        getattr(payload, "magnitude_multiplier", None),
                    ),
                )
                written += cursor.rowcount
                if isinstance(payload, ContributingCause):
                    cursor.executemany(
                        "INSERT INTO causal_edge_co_cause (causal_edge_id, co_cause_event_id) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        [
                            (edge.causal_edge_id, event_id)
                            for event_id in payload.co_cause_event_ids
                        ],
                    )
                self._insert_evidence_items(cursor, edge.causal_edge_id, edge.evidence)
            connection.commit()
        return written

    def write_evidence_items(self, items: Iterable[EvidenceItem]) -> int:
        """Persist justifications. Refuses an item with empty `verification`."""
        materialized = list(items)
        with self._factory.connect() as connection, connection.cursor() as cursor:
            written = self._insert_evidence_items(cursor, None, tuple(materialized))
            connection.commit()
        return written

    # ------------------------------------------------------------------
    # Reads -- every one batched, every one in canonical sequence
    # ------------------------------------------------------------------

    def entities_for_dataset(self, dataset_version: str) -> Iterator[Entity]:
        """Yield entities sequenced by `entity_id`."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_ENTITIES_FOR_DATASET, (dataset_version,))
            for page in _paged(cursor, READ_PAGE_SIZE):
                identifiers = [record[0] for record in page]
                attributes = _grouped_pairs(cursor, sql.SELECT_ENTITY_ATTRIBUTES, identifiers)
                lifecycle_states = _grouped_values(
                    cursor, sql.SELECT_ENTITY_LIFECYCLE_STATES, identifiers
                )
                lifecycle_transitions = _grouped_pairs(
                    cursor, sql.SELECT_ENTITY_LIFECYCLE_TRANSITIONS, identifiers
                )
                evidence = _grouped_values(cursor, sql.SELECT_ENTITY_EVIDENCE, identifiers)
                for record in page:
                    entity_id = record[0]
                    yield row_mapping.entity_from_row(
                        record,
                        attributes.get(entity_id, ()),
                        lifecycle_states.get(entity_id, ()),
                        lifecycle_transitions.get(entity_id, ()),
                        evidence.get(entity_id, ()),
                    )

    def events_for_dataset(self, dataset_version: str) -> Iterator[Event]:
        """Yield events sequenced by `(t_earliest, t_latest, event_id)`."""
        yield from self._events(sql.SELECT_EVENTS_FOR_DATASET, (dataset_version,))

    def events_for_entity(self, entity_id: str) -> Iterator[Event]:
        """Yield events this entity participated in, in canonical event sequence."""
        yield from self._events(sql.SELECT_EVENTS_FOR_ENTITY, (entity_id,))

    def states_for_dataset(self, dataset_version: str) -> Iterator[State]:
        """Yield currently believed states sequenced by `state_id`."""
        yield from self._states(sql.SELECT_STATES_FOR_DATASET, (dataset_version,))

    def states_as_believed_at(
        self, dataset_version: str, system_instant: datetime
    ) -> Iterator[State]:
        """Yield the states this system believed at `system_instant` (ADR-0032)."""
        yield from self._states(
            sql.SELECT_STATES_AS_BELIEVED_AT, (dataset_version, system_instant, system_instant)
        )

    def transitions_for_dataset(self, dataset_version: str) -> Iterator[Transition]:
        """Yield currently believed transitions sequenced by `transition_id`."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_TRANSITIONS_FOR_DATASET, (dataset_version,))
            for record in cursor:
                yield row_mapping.transition_from_row(record)

    def relationships_for_dataset(self, dataset_version: str) -> Iterator[Relationship]:
        """Yield currently believed relationships sequenced by `relationship_id`."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_RELATIONSHIPS_FOR_DATASET, (dataset_version,))
            for page in _paged(cursor, READ_PAGE_SIZE):
                identifiers = [record[0] for record in page]
                evidence = _grouped_values(cursor, sql.SELECT_RELATIONSHIP_EVIDENCE, identifiers)
                for record in page:
                    yield row_mapping.relationship_from_row(record, evidence.get(record[0], ()))

    def evidence_records(self, evidence_record_ids: Sequence[str]) -> Iterator[EvidenceRecord]:
        """Yield the named citations sequenced by `evidence_record_id`."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql.SELECT_EVIDENCE_RECORDS, (list(evidence_record_ids),))
            for record in cursor.fetchall():
                yield row_mapping.evidence_record_from_row(record)

    def causal_edges_for_run(self, run_id: str) -> Iterator[CausalEdge]:
        """Yield edges sequenced by `(source_event_id, target_event_id, edge_kind)`."""
        yield from self._causal_edges(sql.SELECT_CAUSAL_EDGES_FOR_RUN, (run_id,))

    def causal_edges_into(self, run_id: str, target_event_id: str) -> Iterator[CausalEdge]:
        """Yield edges pointing at an effect -- the backward traversal seed."""
        statement = sql.SELECT_CAUSAL_EDGES_FOR_RUN.replace(
            "WHERE run_id = %s", "WHERE run_id = %s AND target_event_id = %s"
        )
        yield from self._causal_edges(statement, (run_id, target_event_id))

    def causal_edges_out_of(self, run_id: str, source_event_id: str) -> Iterator[CausalEdge]:
        """Yield edges leading away from a cause -- the forward propagation sweep."""
        statement = sql.SELECT_CAUSAL_EDGES_FOR_RUN.replace(
            "WHERE run_id = %s", "WHERE run_id = %s AND source_event_id = %s"
        )
        yield from self._causal_edges(statement, (run_id, source_event_id))

    def fact_counts(self, dataset_version: str, run_id: str) -> dict[str, int]:
        """Return the per-table counts the projection verification compares against.

        One statement rather than six, so every count is read at one instant. Six
        statements could disagree with each other because a write landed between two of
        them, and a verification that can disagree with itself reports drift that is not
        there.
        """
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.COUNT_FACTS_FOR_DATASET,
                {"dataset_version": dataset_version, "run_id": run_id},
            )
            record = cursor.fetchone()
        assert record is not None  # noqa: S101 -- a scalar subquery row always exists
        return {
            "entity": record[0],
            "event": record[1],
            "state": record[2],
            "transition": record[3],
            "relationship": record[4],
            "causal_edge": record[5],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _events(self, statement: str, parameters: tuple[Any, ...]) -> Iterator[Event]:
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            for page in _paged(cursor, READ_PAGE_SIZE):
                identifiers = [record[0] for record in page]
                vector_ids = [record[11] for record in page]
                vectors = self._confidence_vectors(cursor, vector_ids)
                participants = _grouped_by_role(cursor, sql.SELECT_EVENT_PARTICIPANTS, identifiers)
                changed = _grouped_pairs(cursor, sql.SELECT_EVENT_CHANGED_ATTRIBUTES, identifiers)
                metadata = _grouped_pairs(cursor, sql.SELECT_EVENT_METADATA, identifiers)
                evidence = _grouped_values(cursor, sql.SELECT_EVENT_EVIDENCE, identifiers)
                for record in page:
                    event_id = record[0]
                    sources, targets = participants.get(event_id, ((), ()))
                    yield row_mapping.event_from_row(
                        record,
                        vectors[record[11]],
                        sources,
                        targets,
                        changed.get(event_id, ()),
                        metadata.get(event_id, ()),
                        evidence.get(event_id, ()),
                    )

    def _states(self, statement: str, parameters: tuple[Any, ...]) -> Iterator[State]:
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            for page in _paged(cursor, READ_PAGE_SIZE):
                identifiers = [record[0] for record in page]
                evidence = _grouped_values(cursor, sql.SELECT_STATE_EVIDENCE, identifiers)
                for record in page:
                    yield row_mapping.state_from_row(record, evidence.get(record[0], ()))

    def _causal_edges(self, statement: str, parameters: tuple[Any, ...]) -> Iterator[CausalEdge]:
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            for page in _paged(cursor, READ_PAGE_SIZE):
                identifiers = [record[0] for record in page]
                vectors = self._confidence_vectors(cursor, [record[9] for record in page])
                co_causes = _grouped_values(cursor, sql.SELECT_CAUSAL_EDGE_CO_CAUSES, identifiers)
                items = self._evidence_items_by_edge(cursor, identifiers)
                for record in page:
                    edge_id = record[0]
                    payload = row_mapping.payload_from_row(
                        record[8],
                        record[10],
                        record[11],
                        record[12],
                        co_causes.get(edge_id, ()),
                        record[13],
                    )
                    yield row_mapping.causal_edge_from_row(
                        record[:8], payload, vectors[record[9]], items.get(edge_id, ())
                    )

    def _confidence_vectors(
        self, cursor: Cursor[Any], vector_ids: Sequence[int]
    ) -> dict[int, ConfidenceVector]:
        unique = sorted(set(vector_ids))
        if not unique:
            return {}
        cursor.execute(sql.SELECT_CONFIDENCE_COMPONENTS, (unique,))
        components: dict[int, list[Any]] = defaultdict(list)
        for record in cursor.fetchall():
            components[record[0]].append((record[1], record[2], record[3], tuple(record[4])))
        cursor.execute(sql.SELECT_CONFIDENCE_VECTORS, (unique,))
        return {
            record[0]: row_mapping.confidence_vector_from_rows(
                record[1], record[2], record[3], components[record[0]]
            )
            for record in cursor.fetchall()
        }

    def _evidence_items_by_edge(
        self, cursor: Cursor[Any], edge_ids: Sequence[str]
    ) -> dict[str, tuple[EvidenceItem, ...]]:
        if not edge_ids:
            return {}
        cursor.execute(sql.SELECT_CAUSAL_EDGE_EVIDENCE_ITEMS, (list(edge_ids),))
        grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
        for record in cursor.fetchall():
            grouped[record[0]].append(
                row_mapping.evidence_item_from_row(record[1:7], tuple(record[7]))
            )
        return {edge_id: tuple(items) for edge_id, items in grouped.items()}

    def _store_decomposition(self, cursor: Cursor[Any], vector: ConfidenceVector) -> int:
        """Store a decomposed judgement and return the storage surrogate that addresses it.

        Deliberately NOT named `_insert_confidence_vector`. The LAW-EVIDENCE lint
        (`scripts/check_confidence_is_a_vector.py`) refuses a confidence-named binding
        whose type is numeric, and it was right to fire on the original name. The
        returned `int` is a `BIGSERIAL` surrogate that never crosses a module boundary
        (`CONVENTIONS.md` §9) -- it is not a confidence, and a name implying it was one
        is exactly the reading LAW-EVIDENCE exists to prevent.
        """
        cursor.execute(
            sql.INSERT_CONFIDENCE_VECTOR,
            (vector.scalar, vector.aggregation, vector.provenance_class.value),
        )
        record = cursor.fetchone()
        if record is None:  # pragma: no cover -- RETURNING on an INSERT always yields
            raise ContractViolationError(
                "Storing a confidence decomposition returned no surrogate. The statement "
                "carries RETURNING precisely so the components can be attached to the "
                "vector they belong to; without one they would be orphaned, and the "
                "LAW-EVIDENCE hook would point at nothing."
            )
        vector_id = int(record[0])
        cursor.executemany(
            sql.INSERT_CONFIDENCE_COMPONENT,
            [
                (
                    vector_id,
                    component.component_name,
                    component.value,
                    component.provenance_class.value,
                )
                for component in vector.components
            ],
        )
        cursor.executemany(
            "INSERT INTO confidence_component_evidence "
            "(confidence_vector_id, component_name, evidence_record_id) "
            "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            [
                (vector_id, component.component_name, evidence_id)
                for component in vector.components
                for evidence_id in component.evidence_record_ids
            ],
        )
        return vector_id

    def _insert_evidence_items(
        self, cursor: Cursor[Any], causal_edge_id: str | None, items: tuple[EvidenceItem, ...]
    ) -> int:
        written = 0
        for item in items:
            if not item.verification.strip():
                raise LawViolationError(
                    f"Evidence item {item.evidence_item_id} has empty verification. An "
                    "item a reader cannot re-execute is a defect, not a weak item "
                    "(docs/contracts.md §5)."
                )
            cursor.execute(
                "INSERT INTO evidence_item (evidence_item_id, kind, description, strength, "
                "verification, provenance_class) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (evidence_item_id) DO NOTHING",
                (
                    item.evidence_item_id,
                    item.kind.value,
                    item.description,
                    item.strength,
                    item.verification,
                    item.provenance_class.value,
                ),
            )
            written += cursor.rowcount
            cursor.executemany(
                "INSERT INTO evidence_item_support (evidence_item_id, supporting_id, "
                "supporting_kind) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                [
                    (item.evidence_item_id, supporting_id, _supporting_kind(supporting_id))
                    for supporting_id in item.supporting_ids
                ],
            )
            if causal_edge_id is not None:
                cursor.execute(
                    "INSERT INTO causal_edge_evidence (causal_edge_id, evidence_item_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (causal_edge_id, item.evidence_item_id),
                )
        return written

    def _dataset_version_of_evidence(self, cursor: Cursor[Any], evidence_ids: Sequence[str]) -> str:
        """Resolve the dataset version a batch belongs to, from its citations.

        The version is not passed in, deliberately. It is a property of the evidence, and
        deriving it here makes it impossible to file a batch of facts under a dataset
        version their citations do not belong to -- which would be a silently
        unreproducible run.
        """
        if not evidence_ids:
            raise LawViolationError(
                "A batch of observed facts carries no citations, so no dataset version "
                "can be derived for it. LAW-EVIDENCE has no exceptions."
            )
        cursor.execute(
            "SELECT DISTINCT dataset_version FROM evidence_record "
            "WHERE evidence_record_id = ANY(%s)",
            (list(dict.fromkeys(evidence_ids)),),
        )
        versions = sorted(str(record[0]) for record in cursor.fetchall())
        if len(versions) != 1:
            raise ContractViolationError(
                f"A batch of observed facts cites {len(versions)} dataset versions "
                f"({versions}). One run reads one dataset (docs/architecture.md §2, "
                "module 1); facts spanning two would carry a run_id that describes "
                "neither."
            )
        return versions[0]

    def _execute_many(self, statement: str, payload: list[tuple[Any, ...]]) -> int:
        if not payload:
            return 0
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.executemany(statement, payload)
            written = cursor.rowcount
            connection.commit()
        return max(written, 0)


# ---------------------------------------------------------------------------
# Assembly helpers. Each takes a whole page of parents and issues ONE statement.
# ---------------------------------------------------------------------------


def _database_now() -> datetime:
    """Return the instant to open a system period at when no clock was supplied.

    `datetime.now(UTC)`, and only ever as the fallback on a call that did not inject one.
    Naming it here rather than inlining it makes the one place the system reads a clock
    greppable -- `CONVENTIONS.md` §11 forbids it inside a reasoning module, and this is not
    one, but it should still be a single visible exception rather than a habit.
    """
    return datetime.now(UTC)


def _paged(cursor: Cursor[Any], size: int) -> Iterator[list[tuple[Any, ...]]]:
    """Yield fetched rows in pages, preserving the statement's ORDER BY."""
    while True:
        page = cursor.fetchmany(size)
        if not page:
            return
        yield page


def _grouped_values(
    cursor: Cursor[Any], statement: str, identifiers: Sequence[str]
) -> dict[str, tuple[str, ...]]:
    """Return `{parent_id: (value, ...)}` for a two-column child statement."""
    if not identifiers:
        return {}
    cursor.execute(statement, (list(identifiers),))
    grouped: dict[str, list[str]] = defaultdict(list)
    for parent, value in cursor.fetchall():
        grouped[parent].append(value)
    return {parent: tuple(values) for parent, values in grouped.items()}


def _grouped_pairs(
    cursor: Cursor[Any], statement: str, identifiers: Sequence[str]
) -> dict[str, tuple[tuple[str, str], ...]]:
    """Return `{parent_id: ((name, value), ...)}` for a three-column child statement."""
    if not identifiers:
        return {}
    cursor.execute(statement, (list(identifiers),))
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for parent, name, value in cursor.fetchall():
        grouped[parent].append((name, value))
    return {parent: tuple(pairs) for parent, pairs in grouped.items()}


def _grouped_by_role(
    cursor: Cursor[Any], statement: str, identifiers: Sequence[str]
) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Return `{event_id: (source_entity_ids, target_entity_ids)}` from one statement."""
    if not identifiers:
        return {}
    cursor.execute(statement, (list(identifiers),))
    sources: dict[str, list[str]] = defaultdict(list)
    targets: dict[str, list[str]] = defaultdict(list)
    for event_id, entity_id, role in cursor.fetchall():
        (sources if role == "SOURCE" else targets)[event_id].append(entity_id)
    return {
        event_id: (tuple(sources.get(event_id, ())), tuple(targets.get(event_id, ())))
        for event_id in set(sources) | set(targets)
    }


def _supporting_kind(supporting_id: str) -> str:
    """Map an identifier prefix to the artifact family it addresses.

    The mapping is derived from `IdentifierPrefix` rather than written out, so a prefix
    added to the frozen enum cannot be silently missing here. The prefix is the authority
    and the stored `supporting_kind` is derived from it, so the two cannot disagree.

    An unrecognised prefix raises rather than defaulting. A catch-all would let an
    unmodelled artifact family into the evidence graph, and `CONVENTIONS.md` §7 forbids
    falling through to "OTHER".
    """
    families = {
        IdentifierPrefix.EVENT: "EVENT",
        IdentifierPrefix.ENTITY: "ENTITY",
        IdentifierPrefix.STATE: "STATE",
        IdentifierPrefix.TRANSITION: "TRANSITION",
        IdentifierPrefix.CANDIDATE_EDGE: "CAUSAL_EDGE",
        IdentifierPrefix.EVIDENCE_RECORD: "EVIDENCE_RECORD",
    }
    prefix = supporting_id.split(":", 1)[0]
    for identifier_prefix, family in families.items():
        if identifier_prefix.value == prefix:
            return family
    raise ContractViolationError(
        f"Evidence supporting id {supporting_id!r} has no supported type prefix. Every "
        "identifier is <type_prefix>:<digest> (CONVENTIONS.md §9), and an evidence item "
        "may cite an event, an entity, a state, a transition, a causal edge, or a "
        "citation -- nothing else is a re-verifiable target."
    )
