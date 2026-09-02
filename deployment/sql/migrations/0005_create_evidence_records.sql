-- 0005_create_evidence_records.sql
--
-- The citation layer. An `EvidenceRecord` is an opaque, dataset-scoped pointer at one
-- source record: it answers "where did this come from" and nothing else
-- (docs/contracts.md §5).
--
-- The raw record is NOT stored here and is never stored anywhere in this schema.
-- CONVENTIONS.md §7: no error message may leak a raw record, and §8: never log one. A
-- locator is a reference the Data Adapter can resolve back against the pinned source
-- file; storing the row itself would put source content inside the system of record with
-- no evidence chain of its own, and would make every log and error a leak risk.
--
-- Created before events, entities, and states because all three cite it. LAW-EVIDENCE has
-- no exceptions: an OBSERVED artifact with no evidence record cannot be audited and is a
-- defect, so the citation table is the first fact table in the schema.

CREATE TABLE IF NOT EXISTS evidence_record (
    evidence_record_id  TEXT PRIMARY KEY,     -- evd:<sha256(dataset_version|source_locator)[:16]>
    dataset_version     TEXT        NOT NULL REFERENCES dataset_version (dataset_version),
    source_locator      TEXT        NOT NULL, -- opaque pointer: file, offset, key. NEVER the record.
    source_timezone     TEXT,                 -- as declared by the source; NULL when it declared none
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT evidence_record_locator_non_empty CHECK (length(source_locator) > 0),
    UNIQUE (dataset_version, source_locator)
);

COMMENT ON TABLE evidence_record IS
    'A citation: one opaque pointer at one source record, scoped to a dataset version. Answers "where did this come from" (docs/contracts.md §5). Append-only.';
COMMENT ON COLUMN evidence_record.evidence_record_id IS
    'Content address evd:<sha256(dataset_version|source_locator)[:16]> (CONVENTIONS.md §9). Two citations of one source record in one dataset version are one row.';
COMMENT ON COLUMN evidence_record.source_locator IS
    'A resolvable reference, never the record content. Storing the row would put unevidenced source data in the system of record and make every log line a leak risk (CONVENTIONS.md §7, §8).';
COMMENT ON COLUMN evidence_record.source_timezone IS
    'What the source declared, not what we assumed. NULL means the source declared none -- which is a finding about the dataset, not a licence to default to UTC (CONVENTIONS.md §10).';
COMMENT ON CONSTRAINT evidence_record_dataset_version_fkey ON evidence_record IS
    'Evidence is dataset-scoped, never run-scoped. That asymmetry is what makes "inference never overwrites observation" structural (ADR-0013).';

-- The unique key is the address recipe's own input pair, so an identifier collision on
-- DIFFERING payloads surfaces as a primary-key conflict against a different locator
-- rather than as a silent merge of two citations. CONVENTIONS.md §9: a collision on
-- differing payloads is CRITICAL and is never retried.

CREATE TRIGGER evidence_record_is_append_only
    BEFORE UPDATE OR DELETE ON evidence_record
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
