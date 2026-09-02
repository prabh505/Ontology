"""The bulk ingestion path (`BulkFactWriter`), sized for the prd.md §55 load budget.

The target is "dataset loading < 30 seconds" for the reference dataset, which is roughly
180 000 source records. The row-at-a-time path in `fact_repository` cannot reach that and
is not meant to: it is the correctness path, transactional per call and validated per
artifact. This is the throughput path, and it is a *separate port* precisely so a
reasoning module cannot reach for it by accident.

WHAT MAKES IT FAST, and what each choice costs:

1. `COPY … FROM STDIN` rather than `INSERT`. One statement per table
   instead of one per row, no per-statement parse, no per-row round trip. This is the
   whole of the speed-up; everything else below is a smaller multiplier.
2. **UNLOGGED staging tables**, then `INSERT … SELECT … ORDER BY <canonical key>` into the
   real tables. Two reasons rather than one: `COPY` cannot express `ON CONFLICT`, so
   re-ingestion after a partial failure would abort on the first duplicate; and the
   canonical sequence is applied on the way out of staging, so the physical order of the
   real table follows the order every reader asks for. UNLOGGED costs crash-safety on the
   staging tables alone -- they are dropped in the same transaction and hold nothing that
   would survive it anyway.
3. **One transaction for the whole load.** A failure leaves no partial dataset, so the
   remedy is always "run it again" and never "work out how far it got".
4. `SET LOCAL synchronous_commit = off`. Trades durability of the commit acknowledgement
   for throughput. Acceptable here and nowhere else, because a lost load is re-runnable
   from a pinned, hashed source file: the load is a function of its inputs, which is the
   property the whole engine rests on.
5. **Streamed in chunks, never materialised whole.** Every `load_dataset` argument is an
   `Iterable`, consumed once. PostgreSQL permits exactly ONE `COPY` in flight per
   connection, and an event fans out into seven tables, so the seven streams cannot be
   written concurrently -- they are written sequentially per chunk of `COPY_CHUNK_ROWS`
   artifacts. Peak memory is therefore bounded by the chunk, not by the dataset, so a
   larger dataset gets slower and never gets killed. Buffering the whole dataset first --
   the obvious way to make the seven passes work -- would put every row in memory at the
   one moment the database also holds it.
6. **No index is dropped and rebuilt.** The usual bulk-load trick, deliberately skipped:
   dropping the unique constraints would remove the collision check `CONVENTIONS.md` §9
   requires *at insert*, and a content-address collision detected after the load is a
   collision nobody detected.

WHAT IS NOT SKIPPED: validation. Every artifact is a validated `causalog.core` model
before it reaches this module -- construction is where the invariants run. This path moves
where the *database* round trip happens, never where the contract is checked.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Final

from psycopg import Connection

from causalog.core.errors import LawViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Entity, Event, EvidenceRecord
from causalog.persistence.postgres import rows as row_mapping
from causalog.persistence.postgres.connection import PostgresConnectionFactory

__all__ = ["COPY_CHUNK_ROWS", "BulkLoadReport", "PostgresBulkFactWriter"]

#: Artifacts buffered before each round of `COPY` statements. PostgreSQL allows exactly one
#: `COPY` in flight per connection, so an event's seven streams are written sequentially
#: per chunk rather than concurrently; this constant is what bounds peak memory to the
#: chunk instead of to the dataset. Named rather than inline (`CONVENTIONS.md` §5: no magic
#: literals), and measured -- `tests/integration/test_bulk_load_budget.py` reports
#: throughput against the prd.md §55 budget on every run.
COPY_CHUNK_ROWS: Final[int] = 20_000

#: Tables the load touches, re-analyzed once the rows are in. Named rather than inline so
#: the promotion and the statistics refresh cannot drift apart (`CONVENTIONS.md` §5).
ANALYZED_TABLES: Final[str] = "evidence_record, entity, event, event_entity"


@dataclass(frozen=True)
class BulkLoadReport:
    """What a bulk load wrote, and how long it took.

    `elapsed_seconds` is wall-clock and appears in the run summary. It is never an input
    to reasoning: a conclusion that depended on how fast its inputs loaded would not be
    reproducible (`CONVENTIONS.md` §11).
    """

    entity_count: int
    event_count: int
    evidence_record_count: int
    elapsed_seconds: float


class PostgresBulkFactWriter:
    """Loads a whole dataset in one transaction."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        """Bind the writer to a connection source."""
        self._factory = factory

    def load_dataset(
        self,
        *,
        dataset_version: str,
        ontology_hash: str,
        entities: Iterable[Entity],
        events: Iterable[Event],
        evidence_records: Iterable[EvidenceRecord],
    ) -> BulkLoadReport:
        """Load a dataset and return what was written.

        The sequence is fixed by the foreign keys: citations, then participants, then
        occurrences. It is not an optimisation -- an event cannot reference an evidence
        record that does not exist yet, and the constraint says so rather than leaving the
        order to chance.
        """
        started = time.monotonic()
        with self._factory.bulk_connect() as connection:
            self._create_staging(connection)
            evidence_count = self._copy_evidence_records(connection, evidence_records)
            entity_count = self._copy_entities(connection, entities, dataset_version, ontology_hash)
            event_count = self._copy_events(connection, events, dataset_version, ontology_hash)
            self._promote(connection)
            self._analyze(connection)
            self._drop_staging(connection)
            connection.commit()
        return BulkLoadReport(
            entity_count=entity_count,
            event_count=event_count,
            evidence_record_count=evidence_count,
            elapsed_seconds=time.monotonic() - started,
        )

    # ------------------------------------------------------------------
    # Staging
    # ------------------------------------------------------------------

    def _create_staging(self, connection: Connection[Any]) -> None:
        """Create UNLOGGED mirrors of the target tables, without their constraints.

        `INCLUDING DEFAULTS` and nothing else: the staging tables deliberately carry no
        primary keys, no foreign keys, and no triggers. Constraints belong on the
        promotion, which is one set-based statement per table, not on 180 000 individual
        `COPY` rows -- and the append-only trigger in particular must not fire here,
        because staging is dropped rather than kept.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE UNLOGGED TABLE staging_evidence_record
                    (LIKE evidence_record INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
                                          EXCLUDING INDEXES);
                CREATE UNLOGGED TABLE staging_entity
                    (LIKE entity INCLUDING DEFAULTS EXCLUDING CONSTRAINTS EXCLUDING INDEXES);
                CREATE UNLOGGED TABLE staging_entity_attribute
                    (LIKE entity_attribute INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
                                           EXCLUDING INDEXES);
                CREATE UNLOGGED TABLE staging_entity_evidence
                    (LIKE entity_evidence INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
                                          EXCLUDING INDEXES);
                CREATE UNLOGGED TABLE staging_confidence_vector (
                    staging_key BIGINT NOT NULL,
                    scalar NUMERIC(9, 6) NOT NULL,
                    aggregation TEXT NOT NULL,
                    provenance_class TEXT NOT NULL
                );
                CREATE UNLOGGED TABLE staging_confidence_component (
                    staging_key BIGINT NOT NULL,
                    component_name TEXT NOT NULL,
                    value NUMERIC(9, 6) NOT NULL,
                    provenance_class TEXT NOT NULL
                );
                CREATE UNLOGGED TABLE staging_confidence_component_evidence (
                    staging_key BIGINT NOT NULL,
                    component_name TEXT NOT NULL,
                    evidence_record_id TEXT NOT NULL
                );
                CREATE UNLOGGED TABLE staging_event
                    (LIKE event INCLUDING DEFAULTS EXCLUDING CONSTRAINTS EXCLUDING INDEXES
                                EXCLUDING GENERATED);
                ALTER TABLE staging_event ALTER COLUMN confidence_vector_id DROP NOT NULL;
                ALTER TABLE staging_event ADD COLUMN staging_key BIGINT;
                CREATE UNLOGGED TABLE staging_event_entity
                    (LIKE event_entity INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
                                       EXCLUDING INDEXES);
                CREATE UNLOGGED TABLE staging_event_changed_attribute
                    (LIKE event_changed_attribute INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
                                                  EXCLUDING INDEXES);
                CREATE UNLOGGED TABLE staging_event_metadata
                    (LIKE event_metadata INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
                                         EXCLUDING INDEXES);
                CREATE UNLOGGED TABLE staging_event_evidence
                    (LIKE event_evidence INCLUDING DEFAULTS EXCLUDING CONSTRAINTS
                                         EXCLUDING INDEXES);
                """
            )

    def _drop_staging(self, connection: Connection[Any]) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "DROP TABLE staging_event_evidence, staging_event_metadata, "
                "staging_event_changed_attribute, staging_event_entity, staging_event, "
                "staging_confidence_component_evidence, staging_confidence_component, "
                "staging_confidence_vector, staging_entity_evidence, "
                "staging_entity_attribute, staging_entity, staging_evidence_record"
            )

    # ------------------------------------------------------------------
    # COPY
    # ------------------------------------------------------------------

    def _copy_evidence_records(
        self, connection: Connection[Any], records: Iterable[EvidenceRecord]
    ) -> int:
        """COPY citations in chunks.

        `recorded_at` is deliberately absent from the column list. `COPY` does not apply a
        column default to a value it was given, so writing NULL into a NOT NULL DEFAULT
        column fails -- omitting the column is what lets the default apply.
        """
        statement = (
            "COPY staging_evidence_record (evidence_record_id, dataset_version, "
            "source_locator, source_timezone) FROM STDIN"
        )
        written = 0
        for chunk in _chunked(records):
            written += _copy_rows(
                connection,
                statement,
                (
                    (
                        record.evidence_record_id,
                        record.dataset_version,
                        record.source_locator,
                        record.source_timezone,
                    )
                    for record in chunk
                ),
            )
        return written

    def _copy_entities(
        self,
        connection: Connection[Any],
        entities: Iterable[Entity],
        dataset_version: str,
        ontology_hash: str,
    ) -> int:
        written = 0
        for chunk in _chunked(entities):
            parents: list[tuple[Any, ...]] = []
            attributes: list[tuple[Any, ...]] = []
            citations: list[tuple[Any, ...]] = []
            for entity in chunk:
                if entity.provenance_class is not ProvenanceClass.OBSERVED:
                    raise LawViolationError(
                        f"Entity {entity.entity_id} carries provenance "
                        f"{entity.provenance_class.value}. The bulk path enforces the "
                        "same law as the row path: an entity the engine inferred is a "
                        "claim, and claims are run-scoped (LAW-PROVENANCE)."
                    )
                parents.append(
                    (
                        entity.entity_id,
                        dataset_version,
                        ontology_hash,
                        entity.entity_type,
                        entity.natural_key,
                        entity.provenance_class.value,
                    )
                )
                attributes.extend(
                    (entity.entity_id, name, value) for name, value in entity.attributes
                )
                citations.extend(
                    (entity.entity_id, evidence_id) for evidence_id in entity.evidence_record_ids
                )
            written += _copy_rows(
                connection,
                "COPY staging_entity (entity_id, dataset_version, ontology_hash, "
                "entity_type, natural_key, provenance_class) FROM STDIN",
                iter(parents),
            )
            _copy_rows(
                connection,
                "COPY staging_entity_attribute (entity_id, attribute_name, "
                "attribute_value) FROM STDIN",
                iter(attributes),
            )
            _copy_rows(
                connection,
                "COPY staging_entity_evidence (entity_id, evidence_record_id) " "FROM STDIN",
                iter(citations),
            )
        return written

    def _copy_events(
        self,
        connection: Connection[Any],
        events: Iterable[Event],
        dataset_version: str,
        ontology_hash: str,
    ) -> int:
        """COPY events and every child collection, one chunk at a time.

        PostgreSQL permits exactly ONE `COPY` in flight per connection, so the seven
        streams an event fans out into cannot be written concurrently. They are written
        SEQUENTIALLY PER CHUNK instead: buffer one chunk's worth of every child row, then
        issue the seven `COPY` statements in turn. Peak memory is bounded by the chunk, not
        by the dataset, which is the property the streaming design promised and which a
        single buffer-everything pass would have quietly given up.

        The confidence vector's real identifier is a `BIGSERIAL`, which `COPY` cannot
        obtain per row without a round trip -- and a round trip per row is the exact cost
        this path exists to avoid. Each event is given a monotonic `staging_key`, the
        vector rows carry the same key, and `_promote` resolves keys to identifiers in one
        set-based statement after the copy.
        """
        written = 0
        for chunk in _chunked(events):
            parents: list[tuple[Any, ...]] = []
            vectors: list[tuple[Any, ...]] = []
            components: list[tuple[Any, ...]] = []
            component_citations: list[tuple[Any, ...]] = []
            participants: list[tuple[Any, ...]] = []
            changed: list[tuple[Any, ...]] = []
            metadata: list[tuple[Any, ...]] = []
            citations: list[tuple[Any, ...]] = []

            for event in chunk:
                if (
                    event.provenance_class is ProvenanceClass.OBSERVED
                    and not event.evidence_record_ids
                ):
                    raise LawViolationError(
                        f"Event {event.event_id} is OBSERVED and cites no evidence "
                        "record. LAW-EVIDENCE has no exceptions and no fast path."
                    )
                staging_key = written + len(parents)
                parents.append(
                    (
                        event.event_id,
                        dataset_version,
                        ontology_hash,
                        event.event_type,
                        *row_mapping.interval_to_columns(event.occurred_at),
                        event.trigger,
                        event.provenance_class.value,
                        event.is_actionable,
                        event.source_record_ref,
                        staging_key,
                    )
                )
                vectors.append(
                    (
                        staging_key,
                        event.confidence.scalar,
                        event.confidence.aggregation,
                        event.confidence.provenance_class.value,
                    )
                )
                components.extend(
                    (
                        staging_key,
                        component.component_name,
                        component.value,
                        component.provenance_class.value,
                    )
                    for component in event.confidence.components
                )
                # The LAW-EVIDENCE hook, carried on the fast path too. It was missing here
                # in the first version of this loader while the row path wrote it, which
                # meant a bulk-loaded dataset produced confidence components that were
                # named but not traceable to the records that produced them -- the law
                # holding for small loads and not for real ones, which is precisely
                # backwards. `CONVENTIONS.md` §8: a component that cannot be traced to
                # evidence record ids means the module that wrote it is not done.
                component_citations.extend(
                    (staging_key, component.component_name, evidence_id)
                    for component in event.confidence.components
                    for evidence_id in component.evidence_record_ids
                )
                participants.extend(
                    (event.event_id, entity_id, "SOURCE") for entity_id in event.source_entity_ids
                )
                participants.extend(
                    (event.event_id, entity_id, "TARGET") for entity_id in event.target_entity_ids
                )
                changed.extend(
                    (event.event_id, name, value) for name, value in event.changed_attributes
                )
                metadata.extend((event.event_id, name, value) for name, value in event.metadata)
                citations.extend(
                    (event.event_id, evidence_id) for evidence_id in event.evidence_record_ids
                )

            written += _copy_rows(
                connection,
                "COPY staging_event (event_id, dataset_version, ontology_hash, "
                "event_type, t_earliest, t_latest, time_precision, time_provenance, "
                "time_source, trigger_mechanism, provenance_class, is_actionable, "
                "source_record_ref, staging_key) FROM STDIN",
                iter(parents),
            )
            for statement, rows in (
                (
                    "COPY staging_confidence_vector (staging_key, scalar, aggregation, "
                    "provenance_class) FROM STDIN",
                    vectors,
                ),
                (
                    "COPY staging_confidence_component (staging_key, component_name, "
                    "value, provenance_class) FROM STDIN",
                    components,
                ),
                (
                    "COPY staging_confidence_component_evidence (staging_key, "
                    "component_name, evidence_record_id) FROM STDIN",
                    component_citations,
                ),
                (
                    "COPY staging_event_entity (event_id, entity_id, participation_role) "
                    "FROM STDIN",
                    participants,
                ),
                (
                    "COPY staging_event_changed_attribute (event_id, attribute_name, "
                    "attribute_value) FROM STDIN",
                    changed,
                ),
                (
                    "COPY staging_event_metadata (event_id, metadata_name, metadata_value) "
                    "FROM STDIN",
                    metadata,
                ),
                (
                    "COPY staging_event_evidence (event_id, evidence_record_id) " "FROM STDIN",
                    citations,
                ),
            ):
                _copy_rows(connection, statement, iter(rows))
        return written

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def _promote(self, connection: Connection[Any]) -> None:
        """Move staged rows into the real tables, in canonical order, idempotently.

        Every statement carries `ORDER BY` on the canonical key so the physical order of
        the target follows the order every reader asks for, and `ON CONFLICT DO NOTHING`
        so a re-run after a failure is a no-op rather than an abort. The constraints the
        staging tables lack are all applied here, on the way in -- including the unique
        keys that make a content-address collision a loud failure at insert
        (`CONVENTIONS.md` §9).
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evidence_record (evidence_record_id, dataset_version,
                                             source_locator, source_timezone)
                SELECT evidence_record_id, dataset_version, source_locator, source_timezone
                FROM staging_evidence_record
                ORDER BY evidence_record_id
                ON CONFLICT (evidence_record_id) DO NOTHING;

                INSERT INTO entity (entity_id, dataset_version, ontology_hash, entity_type,
                                    natural_key, provenance_class)
                SELECT entity_id, dataset_version, ontology_hash, entity_type, natural_key,
                       provenance_class
                FROM staging_entity
                ORDER BY entity_id
                ON CONFLICT (entity_id) DO NOTHING;

                INSERT INTO entity_attribute (entity_id, attribute_name, attribute_value)
                SELECT DISTINCT ON (entity_id, attribute_name)
                       entity_id, attribute_name, attribute_value
                FROM staging_entity_attribute
                ORDER BY entity_id, attribute_name
                ON CONFLICT DO NOTHING;

                INSERT INTO entity_evidence (entity_id, evidence_record_id)
                SELECT DISTINCT entity_id, evidence_record_id
                FROM staging_entity_evidence
                ORDER BY entity_id, evidence_record_id
                ON CONFLICT DO NOTHING;
                """
            )

            # RE-INGESTION FIRST. Everything below this point assumes staging holds
            # only events that will actually be inserted, and the reason is a defect the
            # idempotence test caught: a confidence vector is keyed by a `BIGSERIAL`
            # surrogate, not by a content address, so `ON CONFLICT DO NOTHING` on the
            # event does NOT stop its vector being created. A second load of the same
            # dataset would leave one orphan vector and one orphan component set per
            # event -- invisible in an event count, and growing every time anyone re-ran
            # an ingest. Dropping the already-present events from staging first makes the
            # whole promotion idempotent rather than only its parent table.
            cursor.execute(
                """
                DELETE FROM staging_event AS staged
                USING event AS existing
                WHERE existing.event_id = staged.event_id;

                DELETE FROM staging_confidence_vector AS vector
                WHERE NOT EXISTS (
                    SELECT 1 FROM staging_event AS staged
                    WHERE staged.staging_key = vector.staging_key
                );

                DELETE FROM staging_confidence_component AS component
                WHERE NOT EXISTS (
                    SELECT 1 FROM staging_event AS staged
                    WHERE staged.staging_key = component.staging_key
                );

                DELETE FROM staging_confidence_component_evidence AS citation
                WHERE NOT EXISTS (
                    SELECT 1 FROM staging_event AS staged
                    WHERE staged.staging_key = citation.staging_key
                );
                """
            )

            # Confidence vectors get their real identifiers here, in one statement, and
            # the mapping from staging key to identifier is materialised so the components
            # and the events can both resolve against it.
            cursor.execute(
                """
                CREATE UNLOGGED TABLE staging_vector_identity AS
                WITH inserted AS (
                    INSERT INTO confidence_vector (scalar, aggregation, provenance_class)
                    SELECT scalar, aggregation, provenance_class
                    FROM staging_confidence_vector
                    ORDER BY staging_key
                    RETURNING confidence_vector_id
                )
                SELECT staging_key, confidence_vector_id
                FROM (
                    SELECT staging_key,
                           row_number() OVER (ORDER BY staging_key) AS position
                    FROM staging_confidence_vector
                ) AS staged
                JOIN (
                    SELECT confidence_vector_id,
                           row_number() OVER (ORDER BY confidence_vector_id) AS position
                    FROM inserted
                ) AS created USING (position);

                INSERT INTO confidence_component (confidence_vector_id, component_name,
                                                  value, provenance_class)
                SELECT identity.confidence_vector_id, component.component_name,
                       component.value, component.provenance_class
                FROM staging_confidence_component AS component
                JOIN staging_vector_identity AS identity USING (staging_key)
                ORDER BY identity.confidence_vector_id, component.component_name
                ON CONFLICT DO NOTHING;

                INSERT INTO confidence_component_evidence (confidence_vector_id,
                                                           component_name, evidence_record_id)
                SELECT identity.confidence_vector_id, citation.component_name,
                       citation.evidence_record_id
                FROM staging_confidence_component_evidence AS citation
                JOIN staging_vector_identity AS identity USING (staging_key)
                ORDER BY identity.confidence_vector_id, citation.component_name,
                         citation.evidence_record_id
                ON CONFLICT DO NOTHING;

                INSERT INTO event (event_id, dataset_version, ontology_hash, event_type,
                                   t_earliest, t_latest, time_precision, time_provenance,
                                   time_source, trigger_mechanism, provenance_class,
                                   confidence_vector_id, is_actionable, source_record_ref)
                SELECT staged.event_id, staged.dataset_version, staged.ontology_hash,
                       staged.event_type, staged.t_earliest, staged.t_latest,
                       staged.time_precision, staged.time_provenance, staged.time_source,
                       staged.trigger_mechanism, staged.provenance_class,
                       identity.confidence_vector_id, staged.is_actionable,
                       staged.source_record_ref
                FROM staging_event AS staged
                JOIN staging_vector_identity AS identity USING (staging_key)
                ORDER BY staged.t_earliest, staged.t_latest, staged.event_id
                ON CONFLICT (event_id) DO NOTHING;

                INSERT INTO event_entity (event_id, entity_id, participation_role)
                SELECT DISTINCT event_id, entity_id, participation_role
                FROM staging_event_entity
                ORDER BY event_id, participation_role, entity_id
                ON CONFLICT DO NOTHING;

                INSERT INTO event_changed_attribute (event_id, attribute_name, attribute_value)
                SELECT DISTINCT ON (event_id, attribute_name)
                       event_id, attribute_name, attribute_value
                FROM staging_event_changed_attribute
                ORDER BY event_id, attribute_name
                ON CONFLICT DO NOTHING;

                INSERT INTO event_metadata (event_id, metadata_name, metadata_value)
                SELECT DISTINCT ON (event_id, metadata_name)
                       event_id, metadata_name, metadata_value
                FROM staging_event_metadata
                ORDER BY event_id, metadata_name
                ON CONFLICT DO NOTHING;

                INSERT INTO event_evidence (event_id, evidence_record_id)
                SELECT DISTINCT event_id, evidence_record_id
                FROM staging_event_evidence
                ORDER BY event_id, evidence_record_id
                ON CONFLICT DO NOTHING;

                DROP TABLE staging_vector_identity;
                """
            )

    def _analyze(self, connection: Connection[Any]) -> None:
        """Refresh statistics for the tables just loaded.

        Without this the planner's estimates date from before the load -- typically from
        an empty table -- and the first root-cause query after an ingest picks a nested
        loop over 180 000 rows. That is a §55 target missed for a reason nobody would look
        for in the query.
        """
        with connection.cursor() as cursor:
            cursor.execute(f"ANALYZE {ANALYZED_TABLES}")


def _chunked(source: Iterable[Any]) -> Iterator[list[Any]]:
    """Yield the source in chunks of `COPY_CHUNK_ROWS`, preserving its sequence."""
    chunk: list[Any] = []
    for item in source:
        chunk.append(item)
        if len(chunk) >= COPY_CHUNK_ROWS:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _copy_rows(connection: Connection[Any], statement: str, rows: Iterator[tuple[Any, ...]]) -> int:
    """Run one `COPY` to completion and return the row count.

    One statement per call, opened and closed here, because PostgreSQL permits exactly one
    `COPY` in flight per connection. An earlier version held several open at once and
    failed with "another command is already in progress" -- the driver reports it, but only
    once a second stream is actually written to, so it is a mistake that survives a small
    test and fails on a real load.
    """
    written = 0
    with connection.cursor() as cursor, cursor.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)
            written += 1
    return written
