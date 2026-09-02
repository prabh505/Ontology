-- 0012_create_causal_edges.sql
--
-- The first RUN-SCOPED table in the schema, and the reason the scoping asymmetry exists.
--
-- Observed facts (entity, event, state, transition, relationship, evidence) are scoped to
-- `dataset_version`. Inferred artifacts are scoped to `run_id`, NOT NULL, with no default
-- and no nullable variant. An inference module writing here is therefore INCAPABLE of
-- overwriting an observed fact -- it has nowhere to write that an observation lives --
-- rather than merely being forbidden from doing so. That is what makes LAW-PROVENANCE
-- structural (ADR-0013, docs/architecture.md §4.3).
--
-- LAW-TIME, in storage. `temporal_verdict` may never be VIOLATION: such an edge is never
-- created, so the value has no admissible row and the CHECK says so. INFERRED provenance
-- additionally requires a CERTAIN verdict and a clear `temporally_unverifiable` flag --
-- the two "we cannot tell" states are kept apart because they are different findings
-- about the dataset and collapsing them would hide which one a run hit (docs/contracts.md
-- §3, CONTEXT.md R-14).
--
-- The five edge kinds are PAYLOAD TYPES, not labels (ADR-0022). In a relational schema
-- that is a sparse-column union with a CHECK per kind: every payload column is NULL unless
-- its kind is present, and every kind's required columns are NOT NULL when it is. A single
-- jsonb payload column would have admitted an AmplifyingCause with no multiplier, which is
-- exactly what the typed union exists to prevent.

CREATE TABLE IF NOT EXISTS causal_edge (
    causal_edge_id            TEXT          PRIMARY KEY,  -- edg:<sha256(source|target|kind)[:16]>
    run_id                    TEXT          NOT NULL REFERENCES run (run_id),
    source_event_id           TEXT          NOT NULL REFERENCES event (event_id),
    target_event_id           TEXT          NOT NULL REFERENCES event (event_id),
    edge_kind                 TEXT          NOT NULL,
    confidence_vector_id      BIGINT        NOT NULL REFERENCES confidence_vector (confidence_vector_id),
    propagation_weight        NUMERIC(9, 6) NOT NULL,
    provenance_class          TEXT          NOT NULL,
    temporal_verdict          TEXT          NOT NULL,
    temporally_unverifiable   BOOLEAN       NOT NULL,
    -- Payload columns, one union across the five kinds (ADR-0022).
    condition_expression      TEXT,          -- CONDITIONAL
    condition_holds           BOOLEAN,       -- CONDITIONAL
    joint_cause_group_id      TEXT,          -- CONTRIBUTING
    magnitude_multiplier      NUMERIC(9, 6), -- AMPLIFYING | INHIBITING

    CONSTRAINT causal_edge_kind_is_declared CHECK (
        edge_kind IN ('DIRECT', 'CONDITIONAL', 'CONTRIBUTING', 'AMPLIFYING', 'INHIBITING')
    ),
    CONSTRAINT causal_edge_is_not_a_self_edge CHECK (source_event_id <> target_event_id),
    CONSTRAINT causal_edge_weight_bounded CHECK (propagation_weight >= 0 AND propagation_weight <= 1),
    CONSTRAINT causal_edge_provenance_is_declared CHECK (
        provenance_class IN ('ASSUMED', 'STATISTICAL', 'INFERRED', 'SIMULATED')
    ),
    -- LAW-TIME.
    CONSTRAINT causal_edge_verdict_is_never_a_violation CHECK (
        temporal_verdict IN ('CERTAIN', 'UNDETERMINED')
    ),
    CONSTRAINT causal_edge_inferred_requires_certain_time CHECK (
        provenance_class <> 'INFERRED'
        OR (temporal_verdict = 'CERTAIN' AND temporally_unverifiable = FALSE)
    ),
    -- The five payloads, as a discriminated union.
    CONSTRAINT causal_edge_direct_payload_is_empty CHECK (
        edge_kind <> 'DIRECT'
        OR (condition_expression IS NULL AND condition_holds IS NULL
            AND joint_cause_group_id IS NULL AND magnitude_multiplier IS NULL)
    ),
    CONSTRAINT causal_edge_conditional_payload_is_complete CHECK (
        edge_kind <> 'CONDITIONAL'
        OR (condition_expression IS NOT NULL AND length(condition_expression) > 0
            AND condition_holds IS NOT NULL
            AND joint_cause_group_id IS NULL AND magnitude_multiplier IS NULL)
    ),
    CONSTRAINT causal_edge_contributing_payload_is_complete CHECK (
        edge_kind <> 'CONTRIBUTING'
        OR (joint_cause_group_id IS NOT NULL AND length(joint_cause_group_id) > 0
            AND condition_expression IS NULL AND condition_holds IS NULL
            AND magnitude_multiplier IS NULL)
    ),
    CONSTRAINT causal_edge_amplifying_payload_is_complete CHECK (
        edge_kind <> 'AMPLIFYING'
        OR (magnitude_multiplier IS NOT NULL AND magnitude_multiplier > 1.0
            AND condition_expression IS NULL AND condition_holds IS NULL
            AND joint_cause_group_id IS NULL)
    ),
    CONSTRAINT causal_edge_inhibiting_payload_is_complete CHECK (
        edge_kind <> 'INHIBITING'
        OR (magnitude_multiplier IS NOT NULL
            AND magnitude_multiplier >= 0.0 AND magnitude_multiplier < 1.0
            AND condition_expression IS NULL AND condition_holds IS NULL
            AND joint_cause_group_id IS NULL)
    ),
    -- Named explicitly rather than left to PostgreSQL: the generated name for four
    -- columns this long exceeds the 63-character identifier limit and would be
    -- silently truncated, which makes every later reference to it a guess.
    CONSTRAINT causal_edge_canonical_key UNIQUE (run_id, source_event_id, target_event_id, edge_kind)
);

COMMENT ON TABLE causal_edge IS
    'An inferred causal claim between two events, scoped to a run. Written only by module 10; module 8 may not write CAUSES and has no table to write it into (docs/architecture.md §1.3). Append-only like every fact table: a run whose conclusions are superseded is compared against, never erased. Dropping a run''s inferences is a PROJECTION operation -- Neo4j is rebuildable, this table is the record.';
COMMENT ON COLUMN causal_edge.run_id IS
    'NOT NULL, with no default. An inferred artifact with no run cannot exist, so an inference module is structurally incapable of overwriting an observed fact rather than merely forbidden from it (ADR-0013).';
COMMENT ON COLUMN causal_edge.provenance_class IS
    'Never OBSERVED, and constrained away from it: causation is never read from a source record (docs/contracts.md §5).';
COMMENT ON COLUMN causal_edge.temporal_verdict IS
    'CERTAIN or UNDETERMINED only. VIOLATION edges are never created, so the value has no admissible row here -- LAW-TIME enforced by the schema and not only by the constructor.';
COMMENT ON COLUMN causal_edge.temporally_unverifiable IS
    'TRUE when the data never PLACED one of the two events. Distinct from an UNDETERMINED verdict, which means the data placed both and could not separate them. Both block promotion to INFERRED; they are kept apart because they are different findings about the dataset (docs/contracts.md §3, CONTEXT.md R-14).';
COMMENT ON COLUMN causal_edge.magnitude_multiplier IS
    'AMPLIFYING requires > 1.0 and INHIBITING requires [0.0, 1.0). A multiplier of exactly 1.0 is deliberately unrepresentable: a no-op amplifier forces the caller to say what it meant (docs/contracts.md §9).';
COMMENT ON CONSTRAINT causal_edge_canonical_key ON causal_edge IS
    'The canonical edge sequence key (docs/architecture.md §3.3 step 3) as a unique constraint, which also makes projection writes idempotent: a rebuild inserts the same edges and conflicts rather than duplicating them.';

CREATE TABLE IF NOT EXISTS causal_edge_evidence (
    causal_edge_id    TEXT NOT NULL REFERENCES causal_edge (causal_edge_id),
    evidence_item_id  TEXT NOT NULL REFERENCES evidence_item (evidence_item_id),
    PRIMARY KEY (causal_edge_id, evidence_item_id)
);

COMMENT ON TABLE causal_edge_evidence IS
    'LAW-EVIDENCE: the justifications behind an edge. `CausalEdge.evidence` is non-empty by contract, and the repository refuses an edge with no row here.';

CREATE TABLE IF NOT EXISTS causal_edge_co_cause (
    causal_edge_id  TEXT NOT NULL REFERENCES causal_edge (causal_edge_id),
    co_cause_event_id TEXT NOT NULL REFERENCES event (event_id),
    PRIMARY KEY (causal_edge_id, co_cause_event_id)
);

COMMENT ON TABLE causal_edge_co_cause IS
    'The co-causes of a CONTRIBUTING edge. A child table rather than an array, because the contract sorts them and because the reverse query "which joint causes name this event" is a real read. Conjunctive, never ranked (docs/contracts.md §5).';

CREATE TABLE IF NOT EXISTS causal_edge_fired_rule (
    causal_edge_id  TEXT NOT NULL REFERENCES causal_edge (causal_edge_id),
    rule_id         TEXT NOT NULL,
    PRIMARY KEY (causal_edge_id, rule_id)
);

COMMENT ON TABLE causal_edge_fired_rule IS
    'Which rules proposed this candidate (module 9 invariant). CONVENTIONS.md §8 requires the fired rule ids on the audit record for every inferred edge; this is where they resolve from.';

-- ---------------------------------------------------------------------------
-- Indexes. Every one is run-scoped first: a query that forgot the run would read another
-- run''s inferences, and leading on run_id makes that mistake a planner-visible one.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS causal_edge_backward_idx
    ON causal_edge (run_id, target_event_id, source_event_id);
COMMENT ON INDEX causal_edge_backward_idx IS
    'Justifying query: GET /root-cause/{ref} (prd.md §53) -- backward traversal from an effect toward its causes, the seed of module 11. On the prd.md §55 <3s root-cause path.';

CREATE INDEX IF NOT EXISTS causal_edge_forward_idx
    ON causal_edge (run_id, source_event_id, target_event_id);
COMMENT ON INDEX causal_edge_forward_idx IS
    'Justifying query: GET /counterfactual and module 12''s propagation sweep -- forward traversal from a seed toward its consequences. On the prd.md §55 <5s counterfactual path.';

CREATE INDEX IF NOT EXISTS causal_edge_canonical_sequence_idx
    ON causal_edge (run_id, source_event_id, target_event_id, edge_kind);
COMMENT ON INDEX causal_edge_canonical_sequence_idx IS
    'Justifying query: the rebuild stream reads edges sequenced by (source_event_id, target_event_id, edge_type) -- docs/architecture.md §3.3 step 3. The UNIQUE constraint provides it; it is named here so the sequence has a stated owner.';

CREATE INDEX IF NOT EXISTS causal_edge_unpromotable_idx
    ON causal_edge (run_id, temporal_verdict)
    WHERE temporal_verdict = 'UNDETERMINED' OR temporally_unverifiable;
COMMENT ON INDEX causal_edge_unpromotable_idx IS
    'Justifying query: the run summary reports the CERTAIN/UNDETERMINED ratio on every run, because a dominant UNDETERMINED share is a finding about the dataset that must stay visible rather than be tuned away (CONTEXT.md R-14). Partial, so it costs nothing on a healthy run.';

CREATE INDEX IF NOT EXISTS causal_edge_evidence_reverse_idx
    ON causal_edge_evidence (evidence_item_id, causal_edge_id);
COMMENT ON INDEX causal_edge_evidence_reverse_idx IS
    'Justifying query: "which edges rest on this justification", needed when a rule is changed and every conclusion that fired it must be listed.';

CREATE TRIGGER causal_edge_is_append_only
    BEFORE UPDATE OR DELETE ON causal_edge
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
