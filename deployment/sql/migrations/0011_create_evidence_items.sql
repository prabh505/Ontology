-- 0011_create_evidence_items.sql
--
-- `EvidenceItem` is a JUSTIFICATION, and is a different thing from `EvidenceRecord`
-- (0005), which is a CITATION. docs/contracts.md §5 keeps them apart deliberately and so
-- does this schema:
--
--   evidence_record -- "where did this come from": a pointer at a source record.
--   evidence_item   -- "why is this believed": one named reason, carrying the rule
--                      identifier or query text that produced it.
--
-- `verification` is the load-bearing column. An item a reader cannot RE-EXECUTE is a
-- defect, not a weak item -- an explanation assembled from unverifiable items cannot be
-- audited by anyone who was not present when it ran. The CHECK that it is non-empty is
-- the cheapest possible enforcement of that and is not the whole of it; the repository
-- refuses an item whose verification does not name a registered rule or a runnable query.
--
-- `supporting_ids` is a JOIN TABLE, not an array column. The reverse query -- "which
-- justifications cite this event / this edge" -- is the first step of every audit that
-- starts from a disputed artifact, and it wants a btree, not a GIN scan over arrays. It
-- is also polymorphic: a supporting id may address an event, an entity, a state, or an
-- edge, so it carries no foreign key and instead names the kind it addresses. That is a
-- deliberate loss of referential integrity, and the drift check reports a dangling
-- support as drift rather than letting it pass unnoticed.

CREATE TABLE IF NOT EXISTS evidence_item (
    evidence_item_id  TEXT          PRIMARY KEY,
    kind              TEXT          NOT NULL,
    description       TEXT          NOT NULL,
    strength          NUMERIC(9, 6) NOT NULL,
    verification      TEXT          NOT NULL,
    provenance_class  TEXT          NOT NULL,
    CONSTRAINT evidence_item_kind_is_declared CHECK (
        kind IN ('RULE', 'TEMPORAL_PROXIMITY', 'SHARED_ENTITY', 'SHARED_IDENTIFIER',
                 'HISTORICAL_FREQUENCY', 'ONTOLOGY', 'STATISTICAL_ASSOCIATION')
    ),
    CONSTRAINT evidence_item_strength_bounded CHECK (strength >= 0 AND strength <= 1),
    CONSTRAINT evidence_item_verification_non_empty CHECK (length(verification) > 0),
    CONSTRAINT evidence_item_description_non_empty CHECK (length(description) > 0),
    CONSTRAINT evidence_item_provenance_is_declared CHECK (
        provenance_class IN ('OBSERVED', 'ASSUMED', 'STATISTICAL', 'INFERRED', 'SIMULATED')
    )
);

COMMENT ON TABLE evidence_item IS
    'One named reason an assertion is believed, carrying the rule id or query text that produced it. A justification, not a citation -- evidence_record is the citation (docs/contracts.md §5).';
COMMENT ON COLUMN evidence_item.kind IS
    'Closed set (prd.md §27). A justification fitting none of these is unmodelled, not weak, and needs an ADR before it can be stored.';
COMMENT ON COLUMN evidence_item.strength IS
    'One item''s own weight -- the single admissible bare float in the vicinity of a judgement, named `strength` precisely so it is not mistaken for a confidence. Confidence is the assembled vector in confidence_vector (docs/contracts.md §5).';
COMMENT ON COLUMN evidence_item.verification IS
    'The exact rule identifier or query text that produced the item. An item a reader cannot re-execute is a DEFECT, not a weak item. This column is what makes an explanation auditable by someone who was not present when it ran.';

CREATE TABLE IF NOT EXISTS evidence_item_support (
    evidence_item_id  TEXT NOT NULL REFERENCES evidence_item (evidence_item_id),
    supporting_id     TEXT NOT NULL,
    supporting_kind   TEXT NOT NULL,
    PRIMARY KEY (evidence_item_id, supporting_id),
    CONSTRAINT evidence_item_support_kind_is_declared CHECK (
        supporting_kind IN ('EVENT', 'ENTITY', 'STATE', 'TRANSITION', 'RELATIONSHIP',
                            'CAUSAL_EDGE', 'EVIDENCE_RECORD')
    )
);

COMMENT ON TABLE evidence_item_support IS
    'What an item points at. Polymorphic and therefore without a foreign key: a supporting id may address any addressed artifact. The trade is stated rather than hidden -- the projection drift check reports a dangling support instead of projecting it (docs/data-model.md).';
COMMENT ON COLUMN evidence_item_support.supporting_kind IS
    'The artifact family the id addresses, so a reader resolves it without parsing the identifier prefix. Prefix and kind must agree; the repository checks it on write.';

CREATE INDEX IF NOT EXISTS evidence_item_support_reverse_idx
    ON evidence_item_support (supporting_id, evidence_item_id);
COMMENT ON INDEX evidence_item_support_reverse_idx IS
    'Justifying query: "which justifications cite this artifact" -- the first step of every audit that starts from a disputed edge or event, and the drill-down behind the evidence panel (prd.md §51). A GIN index over an array column could not serve it as cheaply.';

CREATE TRIGGER evidence_item_is_append_only
    BEFORE UPDATE OR DELETE ON evidence_item
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER evidence_item_support_is_append_only
    BEFORE UPDATE OR DELETE ON evidence_item_support
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
