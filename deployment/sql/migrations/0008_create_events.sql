-- 0008_create_events.sql
--
-- The largest table in the system and the one the whole engine reads from. Events are
-- append-only and immutable: a correction emits a NEW event with a new content address
-- (ADR-0004). prd.md §54 requires immutable event history; this migration is where that
-- requirement stops being prose.
--
-- ENFORCEMENT, stated plainly because "immutable" is easy to claim and easy to lose:
--
--   1. `event_is_append_only` -- BEFORE UPDATE OR DELETE FOR EACH ROW, raising
--      `restrict_violation` via causalog_refuse_mutation() (0004). Both UPDATE and DELETE
--      raise. There is no flag, no session variable, and no role that turns it off; a
--      migration that needs to drop the table drops the trigger with it and is itself a
--      recorded, reviewed, reversible file.
--   2. `REVOKE UPDATE, DELETE ON event` from the application role, applied by deployment.
--      The trigger is the guard; the grant is the first line, because a grant failure is
--      cheaper than a raised exception mid-transaction.
--   3. `tests/law/test_events_are_append_only.py` observes both statements RAISE, rather
--      than observing that nothing wrote. A check that has never been seen to fire has
--      not been seen to work (DEF-0001).
--
-- Why a raising trigger and not a `DO INSTEAD NOTHING` rule: a rule reports success for a
-- write it discarded, and a discarded write that returns success is indistinguishable
-- from an accepted one. 0002 made that mistake for audit_log; 0014 corrects it.
--
-- The timestamp interval is FLATTENED into columns rather than stored as a composite or a
-- range. `TimeInterval` carries four facts -- two bounds, a precision, and a provenance
-- with its source -- and a `tstzrange` can hold only the first two. Splitting the bounds
-- out also lets the canonical sequence key `(t_earliest, t_latest, event_id)` be a plain
-- btree, which is what the rebuild stream and `GET /events` both need. A generated range
-- column is added beside them for containment queries; it is derived, never authoritative.

CREATE TABLE IF NOT EXISTS event (
    event_id              TEXT PRIMARY KEY,   -- evt:<sha256(...)[:16]>, recipe in CONVENTIONS.md §9
    dataset_version       TEXT        NOT NULL REFERENCES dataset_version (dataset_version),
    ontology_hash         TEXT        NOT NULL REFERENCES ontology_version (ontology_hash),
    event_type            TEXT        NOT NULL,
    -- occurred_at: the TimeInterval, flattened.
    t_earliest            TIMESTAMPTZ NOT NULL,
    t_latest              TIMESTAMPTZ NOT NULL,
    time_precision        TEXT        NOT NULL,
    time_provenance       TEXT        NOT NULL,
    time_source           TEXT        NOT NULL,
    occurred_over         TSTZRANGE   GENERATED ALWAYS AS (tstzrange(t_earliest, t_latest, '[]')) STORED,
    trigger_mechanism     TEXT,               -- Event.trigger; OBSERVED, and never read by inference (ADR-0020)
    provenance_class      TEXT        NOT NULL,
    confidence_vector_id  BIGINT      NOT NULL REFERENCES confidence_vector (confidence_vector_id),
    is_actionable         BOOLEAN     NOT NULL,
    source_record_ref     TEXT        NOT NULL REFERENCES evidence_record (evidence_record_id),

    CONSTRAINT event_interval_ordered CHECK (t_earliest <= t_latest),
    CONSTRAINT event_precision_is_declared CHECK (
        time_precision IN ('EXACT', 'SECOND', 'MINUTE', 'HOUR', 'DAY', 'UNKNOWN')
    ),
    CONSTRAINT event_time_provenance_is_admissible CHECK (
        time_provenance IN ('OBSERVED', 'ASSUMED', 'INFERRED')
    ),
    CONSTRAINT event_time_source_non_empty CHECK (length(time_source) > 0),
    CONSTRAINT event_exact_implies_point CHECK (
        time_precision <> 'EXACT' OR t_earliest = t_latest
    ),
    CONSTRAINT event_unknown_implies_assumed_and_unbounded CHECK (
        time_precision <> 'UNKNOWN'
        OR (time_provenance = 'ASSUMED'
            AND t_earliest = '0001-01-01T00:00:00Z'::timestamptz
            AND t_latest  = '9999-12-31T23:59:59.999999Z'::timestamptz)
    ),
    CONSTRAINT event_inferred_time_is_not_exact CHECK (
        time_provenance <> 'INFERRED' OR time_precision <> 'EXACT'
    ),
    CONSTRAINT event_provenance_is_declared CHECK (
        provenance_class IN ('OBSERVED', 'ASSUMED', 'STATISTICAL', 'INFERRED', 'SIMULATED')
    )
);

COMMENT ON TABLE event IS
    'Something that happened. Append-only and immutable: a correction emits a NEW event, never an edit (ADR-0004, prd.md §54). The LAW-EVENT boundary sits above this table -- no row, frame, or column of the source survives into it.';
COMMENT ON COLUMN event.event_id IS
    'Content address. The recipe includes the interval bounds, so narrowing an interval mints a new event -- a different claim about when something happened is a different claim (docs/contracts.md §2).';
COMMENT ON COLUMN event.t_earliest IS
    'Inclusive lower bound of the occurrence interval, UTC. Never imputed: an absent instant is UNKNOWN precision spanning the sentinels, not now(), not epoch, not the previous event (CONVENTIONS.md §10).';
COMMENT ON COLUMN event.t_latest IS
    'Inclusive upper bound, UTC. LAW-TIME is evaluated as cause.t_latest < effect.t_earliest; overlap is UNDETERMINED and is never resolved by a midpoint or a sort position (docs/contracts.md §3).';
COMMENT ON COLUMN event.occurred_over IS
    'Derived from the two bounds for containment queries. Never authoritative and never an input to a verdict -- a range cannot carry the precision and provenance the verdict table reads.';
COMMENT ON COLUMN event.time_precision IS
    'UNKNOWN means the source never placed this event. It may sit on a timeline and may NEVER participate in an INFERRED causal edge (docs/contracts.md §5).';
COMMENT ON COLUMN event.trigger_mechanism IS
    'Event.trigger: the proximate mechanism recorded ON the event, OBSERVED and intrinsic. NO module may read it to create, filter, or score a causal edge -- doing so turns an observation into a causal claim that skipped both the LAW-TIME and LAW-EVIDENCE gates (ADR-0020).';
COMMENT ON COLUMN event.confidence_vector_id IS
    'NOT NULL, and a reference rather than a number. LAW-EVIDENCE exempts no type, including this one; the storage cost on the largest table was accepted deliberately (ADR-0009, docs/contracts.md §9).';
COMMENT ON COLUMN event.is_actionable IS
    'Ontology-declared and stamped on at generation time so the ranking module never reads the ontology (forbidden edge F3, ADR-0008). A mis-declared flag silently changes the headline ranking and nothing can detect it -- CONTEXT.md R-15.';
COMMENT ON COLUMN event.source_record_ref IS
    'The single record this event was generated from, for traceability back to the raw row. It also appears in event_evidence; the contract requires both (docs/contracts.md §5).';

-- Participation. Two tables would duplicate the join; one table with a role column keeps
-- "which events touched this entity" -- the timeline query -- a single index scan.
CREATE TABLE IF NOT EXISTS event_entity (
    event_id             TEXT NOT NULL REFERENCES event (event_id),
    entity_id            TEXT NOT NULL REFERENCES entity (entity_id),
    participation_role   TEXT NOT NULL,
    PRIMARY KEY (event_id, entity_id, participation_role),
    CONSTRAINT event_entity_role_is_declared CHECK (participation_role IN ('SOURCE', 'TARGET'))
);

COMMENT ON TABLE event_entity IS
    'Which participants an event touched, and in which direction. Module 5 groups timelines by entity participation and has never known what an entity is (docs/architecture.md §5.3).';

CREATE TABLE IF NOT EXISTS event_changed_attribute (
    event_id         TEXT NOT NULL REFERENCES event (event_id),
    attribute_name   TEXT NOT NULL,
    attribute_value  TEXT NOT NULL,
    PRIMARY KEY (event_id, attribute_name)
);

COMMENT ON TABLE event_changed_attribute IS
    'What the event changed. Participates in the event address (CONVENTIONS.md §9), so it is a child table for the same ordering reason entity_attribute is: the contract is a name-sorted sequence, and jsonb has no order.';

CREATE TABLE IF NOT EXISTS event_metadata (
    event_id         TEXT NOT NULL REFERENCES event (event_id),
    metadata_name    TEXT NOT NULL,
    metadata_value   TEXT NOT NULL,
    PRIMARY KEY (event_id, metadata_name)
);

COMMENT ON TABLE event_metadata IS
    'Ancillary name/value pairs carried on the event. Does NOT participate in the address: metadata is what has been recorded about an occurrence, not which occurrence it is.';

CREATE TABLE IF NOT EXISTS event_evidence (
    event_id            TEXT NOT NULL REFERENCES event (event_id),
    evidence_record_id  TEXT NOT NULL REFERENCES evidence_record (evidence_record_id),
    PRIMARY KEY (event_id, evidence_record_id)
);

COMMENT ON TABLE event_evidence IS
    'LAW-EVIDENCE: every OBSERVED event has at least one citation. Enforced at write time by the repository, which refuses an OBSERVED event with an empty set.';

-- ---------------------------------------------------------------------------
-- Indexes. Each names the query that justifies it. An index with no query above it does
-- not belong here: on the largest table in the system every index is paid for on every
-- one of the ~180k inserts inside the prd.md §55 30-second load budget.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS event_canonical_sequence_idx
    ON event (dataset_version, t_earliest, t_latest, event_id);
COMMENT ON INDEX event_canonical_sequence_idx IS
    'Justifying queries: (a) GET /events (prd.md §53); (b) the rebuild stream, which reads events sequenced by (t_earliest, t_latest, event_id) -- docs/architecture.md §3.3 step 3. Leading on dataset_version keeps one dataset''s stream off another''s pages.';

CREATE INDEX IF NOT EXISTS event_by_type_idx
    ON event (event_type, dataset_version, t_earliest);
COMMENT ON INDEX event_by_type_idx IS
    'Justifying query: module 9 selects candidate cause/effect pairs by the event types a rule declares (`when: {cause_type: ..., effect_type: ...}`). Without it every rule evaluation is a full scan of the largest table, against the §55 <3s root-cause target.';

CREATE INDEX IF NOT EXISTS event_entity_timeline_idx
    ON event_entity (entity_id, event_id);
COMMENT ON INDEX event_entity_timeline_idx IS
    'Justifying query: GET /timeline/{ref} (prd.md §53) and module 5''s per-process grouping. The primary key leads on event_id and cannot serve it.';

CREATE INDEX IF NOT EXISTS event_evidence_by_record_idx
    ON event_evidence (evidence_record_id, event_id);
COMMENT ON INDEX event_evidence_by_record_idx IS
    'Justifying query: the reverse citation "which events did this source record produce", the first step of any audit that starts from a disputed source row.';

-- Deliberately ABSENT, and recorded so the absence is a decision rather than an oversight:
--   * a GiST index on `occurred_over`. It was written, measured, and removed. It would
--     serve "which events overlap this interval" -- the temporal-proximity evidence kind
--     and the propagation window -- but NO MODULE ISSUES THAT QUERY YET: modules 9 and 12
--     are not built. Measured cost on the reference dataset: ~3 seconds of the prd.md §55
--     thirty-second load budget, about a tenth of it, paid on every ingest and again on
--     every rebuild. The rule at the top of this section says an index needs a query
--     above it, and a query that does not exist cannot be one; adding it back is a
--     one-line migration at the point module 9 can measure what it buys.
--     The `occurred_over` COLUMN stays: it costs nothing to store and is what such an
--     index would be built on.
--   * an index on `trigger_mechanism` -- nothing may query by it, because no inference
--     path may read Event.trigger (ADR-0020). An index would invite the violation.
--   * an index on `is_actionable` -- module 11 reads it per candidate cause, already
--     located by causal_edge; a standalone scan of actionable events has no caller.
--   * an index on `provenance_class` -- its selectivity is near zero on this table, where
--     essentially every row is OBSERVED.

CREATE TRIGGER event_is_append_only
    BEFORE UPDATE OR DELETE ON event
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER event_entity_is_append_only
    BEFORE UPDATE OR DELETE ON event_entity
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER event_changed_attribute_is_append_only
    BEFORE UPDATE OR DELETE ON event_changed_attribute
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER event_metadata_is_append_only
    BEFORE UPDATE OR DELETE ON event_metadata
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER event_evidence_is_append_only
    BEFORE UPDATE OR DELETE ON event_evidence
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
