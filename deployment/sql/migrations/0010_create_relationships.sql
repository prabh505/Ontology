-- 0010_create_relationships.sql
--
-- Structural, NON-CAUSAL edges between entities (module 7). `CAUSES` may never be a
-- relationship_type -- causal edges are a separate artifact produced only by the causal
-- engine, and this table sits below the inference boundary (docs/contracts.md §5,
-- docs/architecture.md §1.3). The CHECK below makes that structural rather than
-- conventional: the string cannot be stored.
--
-- Bi-temporal for the same reason `state` is: `Relationship.valid_over` is a validity
-- interval because structural facts are themselves temporal -- a participant belongs to a
-- group for a period, not forever -- and a re-derivation that narrows that period must
-- supersede rather than rewrite (ADR-0032).

CREATE TABLE IF NOT EXISTS relationship (
    relationship_id    TEXT        NOT NULL,
    relationship_type  TEXT        NOT NULL,
    source_entity_id   TEXT        NOT NULL REFERENCES entity (entity_id),
    target_entity_id   TEXT        NOT NULL REFERENCES entity (entity_id),
    dataset_version    TEXT        NOT NULL REFERENCES dataset_version (dataset_version),
    -- VALID TIME: Relationship.valid_over, flattened as in `state`.
    valid_from         TIMESTAMPTZ NOT NULL,
    valid_to           TIMESTAMPTZ NOT NULL,
    valid_precision    TEXT        NOT NULL,
    valid_provenance   TEXT        NOT NULL,
    valid_source       TEXT        NOT NULL,
    valid_over         TSTZRANGE   GENERATED ALWAYS AS (tstzrange(valid_from, valid_to, '[]')) STORED,
    -- SYSTEM TIME.
    system_from        TIMESTAMPTZ NOT NULL DEFAULT now(),
    system_to          TIMESTAMPTZ NOT NULL DEFAULT 'infinity',
    provenance_class   TEXT        NOT NULL,

    PRIMARY KEY (relationship_id, system_from),
    CONSTRAINT relationship_valid_interval_ordered CHECK (valid_from <= valid_to),
    CONSTRAINT relationship_system_interval_ordered CHECK (system_from < system_to),
    CONSTRAINT relationship_precision_is_declared CHECK (
        valid_precision IN ('EXACT', 'SECOND', 'MINUTE', 'HOUR', 'DAY', 'UNKNOWN')
    ),
    CONSTRAINT relationship_valid_provenance_is_admissible CHECK (
        valid_provenance IN ('OBSERVED', 'ASSUMED', 'INFERRED')
    ),
    CONSTRAINT relationship_valid_source_non_empty CHECK (length(valid_source) > 0),
    CONSTRAINT relationship_endpoints_differ CHECK (source_entity_id <> target_entity_id),
    CONSTRAINT relationship_provenance_is_not_inferred CHECK (
        provenance_class IN ('OBSERVED', 'ASSUMED')
    ),
    -- LAW-PROVENANCE and the inference boundary, in storage. The structural vocabulary is
    -- prd.md §47's non-causal half; the causal half lives in `causal_edge` and is
    -- run-scoped. A schema that could hold both in one table would make "module 7 may not
    -- emit CAUSES" a matter of discipline.
    CONSTRAINT relationship_type_is_structural CHECK (
        relationship_type IN ('BELONGS_TO', 'LOCATED_AT', 'PART_OF')
    )
);

COMMENT ON TABLE relationship IS
    'Structural, non-causal edges between entities (module 7). Bi-temporal: structural facts are themselves temporal, so a narrowed validity supersedes rather than overwrites (ADR-0032).';
COMMENT ON COLUMN relationship.relationship_type IS
    'Constrained to the prd.md §47 types module 7 may actually emit. CAUSES, AFFECTS, BLOCKS, AMPLIFIES, REDUCES and RECOMMENDS are inferred, live in causal_edge, and are run-scoped; PRECEDES is derived at projection time from event ordering and TRANSITIONS_TO from state_transition, so neither is ever a row here. The CHECK is what makes "module 7 may not emit CAUSES" structural rather than conventional (docs/architecture.md §2, module 7).';
COMMENT ON COLUMN relationship.valid_over IS
    'Derived valid-time range for containment queries. Never authoritative; it cannot carry precision or provenance.';
COMMENT ON COLUMN relationship.system_to IS
    '''infinity'' while current. Closing it is the only admissible mutation (ADR-0032).';

CREATE TABLE IF NOT EXISTS relationship_evidence (
    relationship_id     TEXT NOT NULL,
    evidence_record_id  TEXT NOT NULL REFERENCES evidence_record (evidence_record_id),
    PRIMARY KEY (relationship_id, evidence_record_id)
);

COMMENT ON TABLE relationship_evidence IS
    'LAW-EVIDENCE citations for a structural edge. An association implied by co-occurrence and cited by nothing is not created at all (docs/architecture.md §2, module 7).';

CREATE INDEX IF NOT EXISTS relationship_canonical_sequence_idx
    ON relationship (dataset_version, relationship_id)
    WHERE system_to = 'infinity'::timestamptz;
COMMENT ON INDEX relationship_canonical_sequence_idx IS
    'Justifying query: the rebuild stream reads relationships sequenced by relationship_id (docs/architecture.md §3.3 step 3), projecting current beliefs only.';

CREATE INDEX IF NOT EXISTS relationship_by_source_idx
    ON relationship (source_entity_id, relationship_type, relationship_id)
    WHERE system_to = 'infinity'::timestamptz;
COMMENT ON INDEX relationship_by_source_idx IS
    'Justifying query: "what does this participant belong to / sit inside", read by module 5 when grouping timelines and by the entity workspace (prd.md §51).';

CREATE INDEX IF NOT EXISTS relationship_by_target_idx
    ON relationship (target_entity_id, relationship_type, relationship_id)
    WHERE system_to = 'infinity'::timestamptz;
COMMENT ON INDEX relationship_by_target_idx IS
    'Justifying query: the reverse traversal "what belongs to this group", used by propagation when it reports the affected-entity set.';

CREATE TRIGGER relationship_is_bitemporal
    AFTER UPDATE OR DELETE ON relationship
    FOR EACH ROW EXECUTE FUNCTION causalog_close_system_period();

CREATE TRIGGER relationship_evidence_is_append_only
    BEFORE UPDATE OR DELETE ON relationship_evidence
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
