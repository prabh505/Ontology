-- 0016_close_the_append_only_holes.sql
--
-- Two defects, found by running the Validation Gate checklist against a live database on
-- 2026-08-29 rather than by reading the migrations. Both are the same failure shape as
-- DEF-0001 and DEF-0003: a guard that reads as present, a test suite that reads as green,
-- and an operation that walks straight past both.
--
-- DEF-0005 -- TRUNCATE was never refused.
--   0004's `causalog_refuse_mutation` is attached BEFORE UPDATE OR DELETE. TRUNCATE is
--   neither, so it bypassed every append-only guard in the schema. Observed in psql against
--   a migrated database holding one event: UPDATE raised, DELETE raised, and
--   `TRUNCATE event CASCADE` succeeded -- emptying `event` and cascading into
--   `event_entity`, `event_changed_attribute`, `event_metadata`, `event_evidence`, `state`,
--   `state_transition`, `causal_edge`, `causal_edge_co_cause`, `causal_edge_evidence` and
--   `causal_edge_fired_rule`. Ten tables the statement never named.
--
--   This sits inside the threat model 0004 writes for itself. It says a deployment REVOKEs
--   UPDATE and DELETE from the application role, and that the trigger exists anyway because
--   "a superuser connection, a migration, and a psql session all bypass a grant". TRUNCATE
--   is the verb that reaches the fact tables down exactly that path. (It also needs table
--   ownership, so the application role could not have issued it -- but ownership is what a
--   migration, a restore and an operator shell all have, and those are three of the four
--   things 0004 named.)
--
-- DEF-0006 -- seven fact tables had no append-only trigger at all.
--   Not a missing verb this time, a missing attachment. `entity_evidence`,
--   `confidence_component_evidence`, `causal_edge_evidence`, `causal_edge_co_cause`,
--   `causal_edge_fired_rule`, `entity_lifecycle_state` and `entity_lifecycle_transition`
--   accepted plain UPDATE and DELETE. `DELETE FROM confidence_component_evidence` succeeded
--   and removed a row -- the table CONVENTIONS.md §8 requires precisely so that a confidence
--   number can be reconstructed from an audit record alone. Its sibling `event_evidence`
--   refused the identical statement, which is what made the gap invisible: the shape that
--   was checked was guarded, and the shape that was not checked was not.
--
-- Why a statement-level trigger for TRUNCATE. TRUNCATE does not visit rows -- that is the
-- whole reason it is fast, and the reason a FOR EACH ROW trigger can never see it. It is
-- also why an empty table cannot be used to test any of this: with no rows, a row-level
-- guard never fires and every one of these operations "passes" whether or not a guard
-- exists. `tests/law/test_facts_are_append_only.py` now asserts the seed is non-empty
-- before it asserts anything else.
--
-- Deliberately NOT guarded, and each has to stay unguarded for a reason:
--   schema_migration  -- the ledger; `migrate --down` deletes from it by design.
--   dataset_version, ontology_version, rule_pack_version -- input registries, not facts.
--   run               -- rows are inserted and never edited, but immutability here is not
--                        part of the LAW-PROVENANCE claim; adding a row guard is a design
--                        change and belongs in an ADR, not in a defect fix. It DOES get the
--                        TRUNCATE guard, because emptying it orphans every inference.
--   graph_projection  -- a DERIVED registry whose rows move along a status ladder
--                        (staged -> live -> superseded), enforced by its own trigger from
--                        0015. Row mutation is legitimate here. It gets the TRUNCATE guard
--                        only, because losing the table loses the previous-build hash that
--                        step 6 of the rebuild compares against -- the determinism tripwire.
--
-- The exemption list is not a comment any more: `MUTABLE_BY_DESIGN` in the law test carries
-- the same names with the same reasons, and `test_every_fact_table_is_guarded` reads the
-- system catalogue and fails on any table in `public` that is neither guarded nor named
-- there. A table added in a later migration cannot arrive unguarded and unnoticed, which is
-- the actual repair -- DEF-0006 was one missing attachment repeated seven times, and closing
-- the seven without closing the class would leave the eighth to the next reader's attention.

-- ---------------------------------------------------------------------------
-- The TRUNCATE guard.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION causalog_refuse_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'LAW-PROVENANCE: TRUNCATE on table "%" is refused. This table is append-only, and '
        'TRUNCATE is not an exception to that because it is fast (prd.md §54, ADR-0004). '
        'Rebuilding from source means dropping the DATABASE and re-migrating, or reversing '
        'the migration that created this table -- both of which are recorded operations. '
        'Emptying a fact table in place is not.',
        TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;

COMMENT ON FUNCTION causalog_refuse_truncate() IS
    'BEFORE TRUNCATE FOR EACH STATEMENT guard. Statement-level because TRUNCATE visits no rows, which is exactly why the FOR EACH ROW guard of 0004 could not see it (DEF-0005).';

-- ---------------------------------------------------------------------------
-- DEF-0006: the seven missing row guards, attached first so that the coverage query
-- below is satisfied by real triggers rather than by the loop that follows.
-- ---------------------------------------------------------------------------
CREATE TRIGGER entity_evidence_is_append_only
    BEFORE UPDATE OR DELETE ON entity_evidence
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER confidence_component_evidence_is_append_only
    BEFORE UPDATE OR DELETE ON confidence_component_evidence
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER causal_edge_evidence_is_append_only
    BEFORE UPDATE OR DELETE ON causal_edge_evidence
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER causal_edge_co_cause_is_append_only
    BEFORE UPDATE OR DELETE ON causal_edge_co_cause
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER causal_edge_fired_rule_is_append_only
    BEFORE UPDATE OR DELETE ON causal_edge_fired_rule
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER entity_lifecycle_state_is_append_only
    BEFORE UPDATE OR DELETE ON entity_lifecycle_state
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER entity_lifecycle_transition_is_append_only
    BEFORE UPDATE OR DELETE ON entity_lifecycle_transition
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

-- ---------------------------------------------------------------------------
-- DEF-0005: the TRUNCATE guard, on every table that asserts immutability.
--
-- Driven by a query over the catalogue rather than by a written-out list of thirty table
-- names. The list is what failed in DEF-0006 -- a name is omitted once and the omission is
-- then invisible forever, because the artifact that would reveal it is the same artifact
-- that is missing the entry. Deriving the set from "has a row-level immutability guard"
-- means the two can never disagree: a table guarded against UPDATE and DELETE is guarded
-- against TRUNCATE in the same breath, including tables added by future migrations, which
-- get theirs by re-running this block's logic in their own migration.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    target text;
BEGIN
    FOR target IN
        SELECT DISTINCT t.relname
        FROM pg_class t
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_trigger g ON g.tgrelid = t.oid AND NOT g.tgisinternal
        WHERE n.nspname = 'public'
          AND t.relkind = 'r'
          -- Any row-level guard: `causalog_refuse_mutation` on the append-only tables,
          -- `causalog_close_system_period` on the bi-temporal ones, and the status ladder
          -- on `graph_projection`. All three make a claim about what may not be destroyed.
          AND (g.tgtype & 8 > 0 OR g.tgtype & 16 > 0)
        UNION
        -- `run` has no row guard by design (see the header) and still must not be emptied:
        -- every inference in the system is scoped to a row in it.
        SELECT 'run'
        ORDER BY 1
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE TRUNCATE ON %I '
            'FOR EACH STATEMENT EXECUTE FUNCTION causalog_refuse_truncate()',
            target || '_refuses_truncate', target
        );
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- The audit index that never stated its justifying query.
--
-- Every index in this schema carries a COMMENT naming the query that justifies it, and 26
-- of the 27 declared indexes did. `audit_log_run_idx` came from 0002, before the convention
-- existed; 0014 commented the two indexes it added to the same table and left this one. An
-- index with no stated consumer is an index nobody can safely drop.
-- ---------------------------------------------------------------------------
COMMENT ON INDEX audit_log_run_idx IS
    'Justifying query: "everything this run did, in sequence" -- the run detail view and the replay path, which read a run''s audit trail start to finish. Leading on run_id keeps one run''s trail off another''s pages; audit_id second gives the sequence without a sort.';

-- ---------------------------------------------------------------------------
-- Table comments corrected. Both previously claimed a guarantee the schema did not provide.
-- ---------------------------------------------------------------------------
COMMENT ON TABLE audit_log IS
    'Append-only, enforced by trigger: UPDATE, DELETE and TRUNCATE all raise. The 0002 rules that silently discarded writes were DEF-0003 and are gone; TRUNCATE was DEF-0005.';

COMMENT ON TABLE confidence_component_evidence IS
    'LAW-EVIDENCE (CONVENTIONS.md §8): which source records justify this component, so a confidence number can be reconstructed from an audit record alone. Append-only -- and unguarded until 0016, which was DEF-0006.';

COMMENT ON TABLE entity_evidence IS
    'LAW-EVIDENCE: which source records asserted this participant exists. An OBSERVED artifact with no citation cannot be audited. Append-only; unguarded until 0016 (DEF-0006).';
