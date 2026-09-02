-- 0006_create_confidence_vectors.sql
--
-- LAW-EVIDENCE in storage form: "every confidence number decomposes into named,
-- inspectable components with the evidence records that produced them. A bare float is a
-- defect."
--
-- The schema is therefore two tables, not a column. A `numeric` confidence column on
-- `event` or on `causal_edge` would be exactly the bare float the law forbids, and no
-- amount of application discipline could stop a later reader treating it as authoritative.
-- Storing the decomposition and DERIVING the scalar makes the law structural: there is
-- nowhere to put an undecomposable number.
--
-- Created before `event` because Event.confidence is a full ConfidenceVector (ADR-0009) --
-- LAW-EVIDENCE exempts no type, including the largest table in the system. The cost is
-- real and was accepted: docs/contracts.md §9 records it.

CREATE TABLE IF NOT EXISTS confidence_vector (
    confidence_vector_id  BIGSERIAL PRIMARY KEY,  -- storage surrogate; NEVER crosses a module boundary (CONVENTIONS.md §9)
    scalar                NUMERIC(9, 6) NOT NULL, -- DERIVED and non-authoritative
    aggregation           TEXT          NOT NULL, -- the registered aggregator name that produced `scalar`
    provenance_class      TEXT          NOT NULL,
    CONSTRAINT confidence_vector_scalar_bounded CHECK (scalar >= 0 AND scalar <= 1),
    CONSTRAINT confidence_vector_aggregation_non_empty CHECK (length(aggregation) > 0),
    CONSTRAINT confidence_vector_provenance_is_declared CHECK (
        provenance_class IN ('OBSERVED', 'ASSUMED', 'STATISTICAL', 'INFERRED', 'SIMULATED')
    )
);

COMMENT ON TABLE confidence_vector IS
    'A decomposed judgement. LAW-EVIDENCE: a bare float is a defect, so there is no confidence column anywhere in this schema -- only a reference to one of these rows.';
COMMENT ON COLUMN confidence_vector.confidence_vector_id IS
    'A storage surrogate, permitted by CONVENTIONS.md §9 for efficiency and forbidden from crossing a module boundary or appearing in an API response. The vector has no content address of its own: it is a component OF an addressed artifact, not an artifact.';
COMMENT ON COLUMN confidence_vector.scalar IS
    'Derived, non-authoritative, displayable. NUMERIC(9,6) matches the six-place quantization every serialization boundary applies (CONVENTIONS.md §11); a float8 here would reintroduce the drift the quantization exists to remove.';
COMMENT ON COLUMN confidence_vector.aggregation IS
    'Names the function that produced the scalar so it can be recomputed and disagreed with. A scalar whose function is unnamed is the unexplained number prd.md §49 forbids (ADR-0009).';
COMMENT ON COLUMN confidence_vector.provenance_class IS
    'The WEAKEST component class, computed by core.provenance.combine -- never by the aggregator arithmetic. combine has no promotion path (docs/contracts.md §4).';

CREATE TABLE IF NOT EXISTS confidence_component (
    confidence_vector_id  BIGINT        NOT NULL REFERENCES confidence_vector (confidence_vector_id),
    component_name        TEXT          NOT NULL,
    value                 NUMERIC(9, 6) NOT NULL,
    provenance_class      TEXT          NOT NULL,
    PRIMARY KEY (confidence_vector_id, component_name),
    CONSTRAINT confidence_component_value_bounded CHECK (value >= 0 AND value <= 1),
    CONSTRAINT confidence_component_provenance_is_declared CHECK (
        provenance_class IN ('OBSERVED', 'ASSUMED', 'STATISTICAL', 'INFERRED', 'SIMULATED')
    )
);

-- No ON DELETE CASCADE anywhere here, deliberately. The parent carries a raising
-- append-only trigger, so a cascade could never fire; declaring one would describe a
-- deletion path that does not exist and cannot be tested.

COMMENT ON TABLE confidence_component IS
    'One named, inspectable component of a judgement. The primary key is (vector, name), which enforces the "sorted by name, no repeats" invariant of ConfidenceVector at the storage layer.';
COMMENT ON COLUMN confidence_component.component_name IS
    'Deliberately NOT constrained to the six weighted names. `minimum_v1` is name-agnostic, and the admissible set is part of confidence_schema_version rather than of this schema -- a CHECK here would force a migration for a contract change the aggregator registry already governs (ADR-0009).';
COMMENT ON COLUMN confidence_component.value IS
    'A component expressing a count is normalized BEFORE it becomes a component, so no reader has to know which components are counts (docs/contracts.md §5).';

-- Each component cites the evidence that produced it. This join is the LAW-EVIDENCE hook
-- CONVENTIONS.md §8 requires: from an audit record alone, a confidence number must be
-- reconstructible back to the evidence behind it. Without this table the components are
-- named but unverifiable, which is a decomposition and not a justification.
CREATE TABLE IF NOT EXISTS confidence_component_evidence (
    confidence_vector_id  BIGINT NOT NULL,
    component_name        TEXT   NOT NULL,
    evidence_record_id    TEXT   NOT NULL REFERENCES evidence_record (evidence_record_id),
    PRIMARY KEY (confidence_vector_id, component_name, evidence_record_id),
    FOREIGN KEY (confidence_vector_id, component_name)
        REFERENCES confidence_component (confidence_vector_id, component_name)
);

COMMENT ON TABLE confidence_component_evidence IS
    'The LAW-EVIDENCE hook: which source records produced which component. A component that cannot reach this table is undefended, and the module that wrote it is not done (CONVENTIONS.md §8).';

-- Justifying query: "decompose this edge's confidence" -- the panel prd.md §49 and the
-- explanation generator both render. Reached on every root-cause and every edge-detail
-- read, so it is on the §55 <3s path. The primary key already sequences components by
-- name within a vector, which is also the canonical order the contract requires, so no
-- separate index is needed for the decomposition read itself.
CREATE INDEX IF NOT EXISTS confidence_component_evidence_by_record_idx
    ON confidence_component_evidence (evidence_record_id, confidence_vector_id);

COMMENT ON INDEX confidence_component_evidence_by_record_idx IS
    'Justifying query: the reverse drill-down "which judgements rest on this source record", used when a rejected or corrected record must have its downstream conclusions listed.';

CREATE TRIGGER confidence_vector_is_append_only
    BEFORE UPDATE OR DELETE ON confidence_vector
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER confidence_component_is_append_only
    BEFORE UPDATE OR DELETE ON confidence_component
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
