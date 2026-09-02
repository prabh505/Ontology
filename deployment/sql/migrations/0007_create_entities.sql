-- 0007_create_entities.sql
--
-- Entities: the participants the engine reasons about (LAW-EVENT). Dataset-scoped, never
-- run-scoped -- an entity is observed, and observation is not something an inference run
-- may restate (ADR-0013).
--
-- ATTRIBUTES ARE A CHILD TABLE, NOT JSONB. The justification, because the alternative is
-- the obvious one:
--
--   * `Entity.attributes` is `tuple[tuple[str, str], ...]` -- an ordered sequence of
--     name/value pairs, sorted by name. A `jsonb` object is an UNORDERED map, so the
--     round trip would depend on jsonb's own key ordering rather than on the canonical
--     sort key, and CONVENTIONS.md §11 requires reads in canonical sequence. A child
--     table with `ORDER BY attribute_name` reproduces the contract exactly.
--   * Attribute names are queried as predicates (the API entity view, the extractor's
--     natural-key derivation). A btree on `(entity_id, attribute_name)` serves those; the
--     jsonb equivalent needs a GIN index that is larger, slower to build, and cannot
--     produce sorted output without an extra sort node.
--   * The cardinality is small -- entities are participants, not rows. The DataCo pack
--     declares a handful of attributes per entity type. The row-count argument that
--     justifies JSONB on a wide, sparse, write-once payload does not apply here.
--
-- JSONB IS used in this schema, but only where the payload is genuinely opaque to SQL:
-- `audit_log.before/after`, `ontology_version.resolved_pack`, and the run-scoped artifact
-- payloads whose types are not yet frozen. The rule is: a value the database is asked to
-- sort, join, or constrain gets a column; a value it only has to hand back gets JSONB.

CREATE TABLE IF NOT EXISTS entity (
    entity_id         TEXT PRIMARY KEY,   -- ent:<sha256(ontology_hash|entity_type|natural_key)[:16]>
    dataset_version   TEXT NOT NULL REFERENCES dataset_version (dataset_version),
    ontology_hash     TEXT NOT NULL REFERENCES ontology_version (ontology_hash),
    entity_type       TEXT NOT NULL,      -- an opaque ontology-declared string; no engine code branches on its value
    natural_key       TEXT NOT NULL,
    provenance_class  TEXT NOT NULL,
    CONSTRAINT entity_provenance_is_observed CHECK (provenance_class = 'OBSERVED'),
    CONSTRAINT entity_natural_key_non_empty CHECK (length(natural_key) > 0),
    UNIQUE (ontology_hash, entity_type, natural_key)
);

COMMENT ON TABLE entity IS
    'A participant. Content-addressed, so the same participant seen in two batches is one row rather than two (docs/architecture.md §2, module 3). Append-only.';
COMMENT ON COLUMN entity.entity_type IS
    'Ontology data, opaque to every reasoning package. LAW-DOMAIN: no engine code may name or branch on a value of this column; the residual that it could is disclosed in docs/architecture.md §1.5.';
COMMENT ON COLUMN entity.provenance_class IS
    'Always OBSERVED, and constrained to it. An entity the engine inferred is not an entity; it is a claim, and claims are run-scoped artifacts (ADR-0013).';
COMMENT ON CONSTRAINT entity_ontology_hash_entity_type_natural_key_key ON entity IS
    'The address recipe inputs, as a unique key. A digest collision on DIFFERING payloads therefore surfaces here as a primary-key conflict rather than as a silent merge of two participants -- CRITICAL, never a retry (CONVENTIONS.md §9).';

CREATE TABLE IF NOT EXISTS entity_attribute (
    entity_id        TEXT NOT NULL REFERENCES entity (entity_id),
    attribute_name   TEXT NOT NULL,
    attribute_value  TEXT NOT NULL,
    PRIMARY KEY (entity_id, attribute_name)
);

COMMENT ON TABLE entity_attribute IS
    'The name/value pairs recorded about an entity. Deliberately NOT jsonb: the contract is an ordered, name-sorted sequence and canonical reads require ORDER BY (CONVENTIONS.md §11).';
COMMENT ON COLUMN entity_attribute.attribute_value IS
    'Text, because the source said text. Typing it here would be interpretation, and interpretation happens in module 2 against mapping.yaml, never in storage.';

-- Lifecycle. `Lifecycle` is ASSUMED configuration read from the ontology pack, not
-- observation, so it is stored beside the entity rather than inside it -- and it is
-- stored at all only so a past run can be read back against the lifecycle it actually
-- used, the same reason `ontology_version.resolved_pack` is stored.
CREATE TABLE IF NOT EXISTS entity_lifecycle_state (
    entity_id   TEXT NOT NULL REFERENCES entity (entity_id),
    state_name  TEXT NOT NULL,
    PRIMARY KEY (entity_id, state_name)
);

COMMENT ON TABLE entity_lifecycle_state IS
    'The declared state names of an entity lifecycle. Provenance is ASSUMED by contract (docs/contracts.md §5); it is configuration, never observation.';

CREATE TABLE IF NOT EXISTS entity_lifecycle_transition (
    entity_id        TEXT NOT NULL REFERENCES entity (entity_id),
    from_state_name  TEXT NOT NULL,
    to_state_name    TEXT NOT NULL,
    PRIMARY KEY (entity_id, from_state_name, to_state_name),
    FOREIGN KEY (entity_id, from_state_name) REFERENCES entity_lifecycle_state (entity_id, state_name),
    FOREIGN KEY (entity_id, to_state_name)   REFERENCES entity_lifecycle_state (entity_id, state_name)
);

COMMENT ON TABLE entity_lifecycle_transition IS
    'The legal transitions of a lifecycle. Both endpoints are foreign keys, so the "every endpoint declared" invariant of Lifecycle holds in storage and not only in the validator.';

CREATE TABLE IF NOT EXISTS entity_evidence (
    entity_id           TEXT NOT NULL REFERENCES entity (entity_id),
    evidence_record_id  TEXT NOT NULL REFERENCES evidence_record (evidence_record_id),
    PRIMARY KEY (entity_id, evidence_record_id)
);

COMMENT ON TABLE entity_evidence IS
    'LAW-EVIDENCE: which source records asserted this participant exists. An OBSERVED artifact with no citation cannot be audited.';

-- Justifying query: module 3 resolves "have I already seen this participant" for every
-- mapped record during ingestion -- 180k lookups inside the §55 30-second budget. The
-- UNIQUE constraint above already provides this index; it is named here rather than
-- duplicated.
--
-- Justifying query: `GET /events` and the entity workspace filter by type within a
-- dataset. The unique key leads on ontology_hash, so it cannot serve a type-only scan.
CREATE INDEX IF NOT EXISTS entity_by_dataset_type_idx
    ON entity (dataset_version, entity_type, entity_id);

COMMENT ON INDEX entity_by_dataset_type_idx IS
    'Justifying query: "every entity of this type in this dataset", used by the entity workspace (prd.md §51) and by the rebuild stream, which reads entities sequenced by entity_id.';

CREATE INDEX IF NOT EXISTS entity_evidence_by_record_idx
    ON entity_evidence (evidence_record_id, entity_id);

COMMENT ON INDEX entity_evidence_by_record_idx IS
    'Justifying query: the reverse citation "which participants did this source record assert", needed when a record is rejected or corrected and its downstream artifacts must be listed.';

CREATE TRIGGER entity_is_append_only
    BEFORE UPDATE OR DELETE ON entity
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER entity_attribute_is_append_only
    BEFORE UPDATE OR DELETE ON entity_attribute
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
