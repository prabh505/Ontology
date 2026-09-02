-- 0009_create_states_and_transitions.sql
--
-- BI-TEMPORAL STORAGE. Read this header before changing anything below it; ADR-0032 is
-- the decision record.
--
-- Two independent time axes, and they answer different questions:
--
--   VALID TIME   -- when the world was in this condition.
--                   Columns: valid_from, valid_to, valid_precision, valid_provenance,
--                   valid_source. This IS `State.held_over`, the frozen TimeInterval of
--                   docs/contracts.md §5, flattened for the same reason event.occurred_at
--                   is: an interval carries four facts and a range type holds two.
--
--   SYSTEM TIME  -- when this system believed it.
--                   Columns: system_from, system_to. Database-managed. It appears in NO
--                   content address, in NO output envelope, and in NO causalog.core type;
--                   no reasoning module may read it. Putting it in an address would make
--                   an identifier depend on insertion wall-clock, which destroys
--                   reproducibility (ADR-0013).
--
-- WHY A CAUSAL SYSTEM NEEDS THE SECOND AXIS, specifically:
--
-- Re-inference is routine here. A Run is re-derived whenever the ontology, the rule pack,
-- or the engine version changes (ADR-0013), and each re-derivation can narrow a state's
-- validity interval -- a better ontology places a transition more precisely, so the
-- interval the previous run reasoned over is no longer the interval this run computes.
--
-- With one time axis, that correction OVERWRITES the interval a past conclusion was
-- computed against. The conclusion then cannot be reproduced (its inputs are gone), cannot
-- be audited (the audit record cites a state that now says something else), and cannot be
-- compared against the new one (there is nothing left to compare). "Two runs differing in
-- exactly one input isolate that input's effect" -- docs/architecture.md §4.4 -- becomes
-- false, and prd.md §54's "no inferred result should overwrite observed facts" fails
-- silently, which is the worst way for it to fail.
--
-- With two axes, re-inference INSERTS a superseding row and CLOSES the prior belief.
-- Nothing is rewritten. "What did the engine believe on 2026-08-01, and what does it
-- believe now" are two queries over one table. A disputed root cause is re-derived rather
-- than re-argued, which is the property docs/architecture.md §4.4 promises.
--
-- THE ONE SANCTIONED MUTATION. `causalog_close_system_period()` (0004) admits exactly one
-- UPDATE: closing an open system period, once. It refuses DELETE, refuses reopening,
-- refuses closing at or before system_from, and refuses any change to row content -- which
-- it detects by comparing the WHOLE row as jsonb minus the two system-period columns,
-- rather than through a per-table column list that could silently drift from the table it
-- guards. A column added by a future migration is covered without editing the trigger.

-- `state_as_of_idx` below is a GiST index whose leading column is TEXT. Core PostgreSQL
-- has no GiST opclass for scalar types, so the composite (entity_id, held_over) index --
-- the one that makes the as-of query an index scan rather than a per-entity filter --
-- needs `btree_gist`. It ships with the standard contrib set and is present in the
-- postgres:16 image the compose file pins.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS state (
    state_id               TEXT        NOT NULL,   -- sta:<sha256(entity_id|state_name|interval)[:16]>
    entity_id              TEXT        NOT NULL REFERENCES entity (entity_id),
    dataset_version        TEXT        NOT NULL REFERENCES dataset_version (dataset_version),
    state_name             TEXT        NOT NULL,
    -- VALID TIME: State.held_over. t_earliest is valid_from, t_latest is valid_to.
    valid_from             TIMESTAMPTZ NOT NULL,
    valid_to               TIMESTAMPTZ NOT NULL,
    valid_precision        TEXT        NOT NULL,
    valid_provenance       TEXT        NOT NULL,
    valid_source           TEXT        NOT NULL,
    held_over              TSTZRANGE   GENERATED ALWAYS AS (tstzrange(valid_from, valid_to, '[]')) STORED,
    -- SYSTEM TIME: when this system believed the above.
    system_from            TIMESTAMPTZ NOT NULL DEFAULT now(),
    system_to              TIMESTAMPTZ NOT NULL DEFAULT 'infinity',
    -- Content and provenance.
    derived_from_event_id  TEXT        NOT NULL REFERENCES event (event_id),
    provenance_class       TEXT        NOT NULL,

    PRIMARY KEY (state_id, system_from),
    CONSTRAINT state_valid_interval_ordered CHECK (valid_from <= valid_to),
    CONSTRAINT state_system_interval_ordered CHECK (system_from < system_to),
    CONSTRAINT state_precision_is_declared CHECK (
        valid_precision IN ('EXACT', 'SECOND', 'MINUTE', 'HOUR', 'DAY', 'UNKNOWN')
    ),
    CONSTRAINT state_valid_provenance_is_admissible CHECK (
        valid_provenance IN ('OBSERVED', 'ASSUMED', 'INFERRED')
    ),
    CONSTRAINT state_valid_source_non_empty CHECK (length(valid_source) > 0),
    CONSTRAINT state_exact_implies_point CHECK (
        valid_precision <> 'EXACT' OR valid_from = valid_to
    ),
    -- A state still holding at the end of the dataset has valid_to at UNKNOWN_LATEST: the
    -- honest statement that no end was recorded (docs/contracts.md §5). That is a real
    -- interval and is deliberately NOT treated as UNKNOWN precision.
    CONSTRAINT state_provenance_is_not_inferred CHECK (
        provenance_class IN ('OBSERVED', 'ASSUMED')
    )
);

COMMENT ON TABLE state IS
    'A condition an entity held over an interval, bi-temporal. Module 6 emits only OBSERVED or explicitly ASSUMED states; INFERRED provenance here would put inference below the inference boundary (docs/architecture.md §1.3).';
COMMENT ON COLUMN state.state_id IS
    'Content address. NOT the primary key on its own: one state_id may have several system periods, one per belief the engine has held about it. The key is (state_id, system_from).';
COMMENT ON COLUMN state.valid_from IS
    'VALID TIME lower bound -- when the world entered this condition. This half of State.held_over (docs/contracts.md §5).';
COMMENT ON COLUMN state.valid_to IS
    'VALID TIME upper bound. UNKNOWN_LATEST (9999-12-31) means no end was recorded, which is a statement about the dataset and not a placeholder to be cleaned up.';
COMMENT ON COLUMN state.system_from IS
    'SYSTEM TIME lower bound -- when this system began believing the row. Wall-clock, database-supplied, excluded from every content address and every determinism comparison (ADR-0032).';
COMMENT ON COLUMN state.system_to IS
    '''infinity'' while the belief is current. Closing it is the ONLY mutation this table admits; reopening it, and every other UPDATE, raises (ADR-0032).';
COMMENT ON COLUMN state.held_over IS
    'Derived valid-time range, for as-of containment queries. Never authoritative: it cannot carry precision or provenance, and a verdict that read it would lose both.';
COMMENT ON COLUMN state.derived_from_event_id IS
    'The event this state was derived from. There is no state without an event behind it -- LAW-EVENT reasons over events, and a state with no origin could not be traced back to a source record.';

CREATE TABLE IF NOT EXISTS state_transition (
    transition_id      TEXT        NOT NULL,   -- trn:<sha256(from_state_id|to_state_id|causing_event_id)[:16]>
    from_state_id      TEXT        NOT NULL,
    to_state_id        TEXT        NOT NULL,
    causing_event_id   TEXT        NOT NULL REFERENCES event (event_id),
    dataset_version    TEXT        NOT NULL REFERENCES dataset_version (dataset_version),
    provenance_class   TEXT        NOT NULL,
    system_from        TIMESTAMPTZ NOT NULL DEFAULT now(),
    system_to          TIMESTAMPTZ NOT NULL DEFAULT 'infinity',

    PRIMARY KEY (transition_id, system_from),
    CONSTRAINT state_transition_system_interval_ordered CHECK (system_from < system_to),
    CONSTRAINT state_transition_endpoints_differ CHECK (from_state_id <> to_state_id),
    CONSTRAINT state_transition_provenance_is_not_inferred CHECK (
        provenance_class IN ('OBSERVED', 'ASSUMED')
    )
);

COMMENT ON TABLE state_transition IS
    'One observed move between two states, accompanied by the event that occasioned it. Bi-temporal for the same reason `state` is: a re-derivation supersedes, never rewrites.';
COMMENT ON COLUMN state_transition.causing_event_id IS
    '"Causing" here is the OBSERVED attribution recorded at state-derivation time. It is NOT an inferred causal edge and never carries INFERRED -- the inference boundary sits two layers above this table (docs/contracts.md §5).';
COMMENT ON COLUMN state_transition.provenance_class IS
    'Constrained away from INFERRED, STATISTICAL, and SIMULATED. Module 6 sits below the inference boundary (docs/architecture.md §1.3) and is structurally incapable of writing one.';

-- No foreign key from state_transition to state, deliberately: `state` is keyed by
-- (state_id, system_from) and a transition names a state_id without naming a belief about
-- it, so a composite reference would force a transition to be superseded whenever either
-- endpoint's belief changed. The referential claim is checked at read time by the
-- repository and at rebuild time by the drift check, which reports a dangling endpoint as
-- drift rather than silently projecting it.

-- ---------------------------------------------------------------------------
-- Indexes.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS state_as_of_idx
    ON state USING GIST (entity_id, held_over);
COMMENT ON INDEX state_as_of_idx IS
    'Justifying query: core.derivation.states_holding_at / current_state -- "which state did this entity hold at instant X". Range containment, which a btree on two bound columns cannot answer without scanning. On the §55 <3s root-cause path.';

CREATE INDEX IF NOT EXISTS state_current_belief_idx
    ON state (entity_id, state_id)
    WHERE system_to = 'infinity'::timestamptz;
COMMENT ON INDEX state_current_belief_idx IS
    'Justifying query: every ordinary read, which wants what the engine believes NOW. Partial, so superseded beliefs never enter the hot index -- the cost of bi-temporality stays on the audit path rather than on the read path.';

CREATE INDEX IF NOT EXISTS state_canonical_sequence_idx
    ON state (dataset_version, state_id)
    WHERE system_to = 'infinity'::timestamptz;
COMMENT ON INDEX state_canonical_sequence_idx IS
    'Justifying query: the rebuild stream reads states sequenced by state_id (docs/architecture.md §3.3 step 3), and projects only current beliefs.';

CREATE INDEX IF NOT EXISTS state_transition_by_event_idx
    ON state_transition (causing_event_id, transition_id)
    WHERE system_to = 'infinity'::timestamptz;
COMMENT ON INDEX state_transition_by_event_idx IS
    'Justifying query: "what did this event change" -- the explanation generator cites it for every sentence about a state change, and the projection writes TRANSITIONS_TO from it.';

CREATE INDEX IF NOT EXISTS state_transition_canonical_sequence_idx
    ON state_transition (dataset_version, transition_id)
    WHERE system_to = 'infinity'::timestamptz;
COMMENT ON INDEX state_transition_canonical_sequence_idx IS
    'Justifying query: the rebuild stream reads transitions sequenced by transition_id (docs/architecture.md §3.3 step 3).';

CREATE TABLE IF NOT EXISTS state_evidence (
    state_id            TEXT NOT NULL,
    evidence_record_id  TEXT NOT NULL REFERENCES evidence_record (evidence_record_id),
    PRIMARY KEY (state_id, evidence_record_id)
);

COMMENT ON TABLE state_evidence IS
    'LAW-EVIDENCE citations for a state, keyed by content address rather than by belief: the citations do not change when the system period does, because the source record said what it said.';

CREATE TRIGGER state_is_bitemporal
    AFTER UPDATE OR DELETE ON state
    FOR EACH ROW EXECUTE FUNCTION causalog_close_system_period();

CREATE TRIGGER state_transition_is_bitemporal
    AFTER UPDATE OR DELETE ON state_transition
    FOR EACH ROW EXECUTE FUNCTION causalog_close_system_period();

CREATE TRIGGER state_evidence_is_append_only
    BEFORE UPDATE OR DELETE ON state_evidence
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
