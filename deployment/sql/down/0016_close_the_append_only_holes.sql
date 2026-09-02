-- down/0016_close_the_append_only_holes.sql -- reverse of
-- migrations/0016_close_the_append_only_holes.sql.
--
-- Restores DEF-0005 and DEF-0006 verbatim, on the same principle as down/0014: a reversal
-- that kept the fix would leave the database in a state no migration describes, and the
-- ledger would then disagree with the schema. Reversing this migration reopens both holes.
-- That is the correct behaviour and is the reason `make migrate-down` is not a routine
-- operation on anything holding real facts.
--
-- The TRUNCATE triggers are dropped by the same catalogue query that created them, so the
-- two cannot drift: whatever the forward migration attached, this detaches.

DO $$
DECLARE
    target text;
BEGIN
    FOR target IN
        SELECT c.relname
        FROM pg_trigger g
        JOIN pg_class c ON c.oid = g.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND NOT g.tgisinternal
          AND g.tgname = c.relname || '_refuses_truncate'
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', target || '_refuses_truncate', target);
    END LOOP;
END;
$$;

DROP FUNCTION IF EXISTS causalog_refuse_truncate();

DROP TRIGGER IF EXISTS entity_lifecycle_transition_is_append_only ON entity_lifecycle_transition;
DROP TRIGGER IF EXISTS entity_lifecycle_state_is_append_only ON entity_lifecycle_state;
DROP TRIGGER IF EXISTS causal_edge_fired_rule_is_append_only ON causal_edge_fired_rule;
DROP TRIGGER IF EXISTS causal_edge_co_cause_is_append_only ON causal_edge_co_cause;
DROP TRIGGER IF EXISTS causal_edge_evidence_is_append_only ON causal_edge_evidence;
DROP TRIGGER IF EXISTS confidence_component_evidence_is_append_only ON confidence_component_evidence;
DROP TRIGGER IF EXISTS entity_evidence_is_append_only ON entity_evidence;

COMMENT ON INDEX audit_log_run_idx IS NULL;

-- The 0014 wording, restored exactly.
COMMENT ON TABLE audit_log IS
    'Append-only, enforced by a RAISING trigger. Until 0014 it was enforced by a rule that rewrote UPDATE and DELETE to no-ops, which reported success for a discarded write -- DEF-0003. The history is left visible here rather than tidied away.';

-- The 0006 and 0007 wordings, restored exactly.
COMMENT ON TABLE confidence_component_evidence IS
    'The LAW-EVIDENCE hook: which source records produced which component. A component that cannot reach this table is undefended, and the module that wrote it is not done (CONVENTIONS.md §8).';

COMMENT ON TABLE entity_evidence IS
    'LAW-EVIDENCE: which source records asserted this participant exists. An OBSERVED artifact with no citation cannot be audited.';
