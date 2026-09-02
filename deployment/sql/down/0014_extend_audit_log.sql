-- down/0014_extend_audit_log.sql -- reverse of migrations/0014_extend_audit_log.sql.
--
-- Restores 0002's rules verbatim, including the DEF-0003 defect. A reversal that "fixed"
-- the thing it reverses would leave the database in a state no migration describes, and
-- the ledger would then disagree with the schema.

DROP INDEX IF EXISTS audit_log_by_correlation_idx;
DROP INDEX IF EXISTS audit_log_by_target_idx;
DROP TRIGGER IF EXISTS audit_log_is_append_only ON audit_log;

CREATE OR REPLACE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE OR REPLACE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;

ALTER TABLE audit_log
    DROP COLUMN IF EXISTS after_state,
    DROP COLUMN IF EXISTS before_state,
    DROP COLUMN IF EXISTS target_kind,
    DROP COLUMN IF EXISTS target,
    DROP COLUMN IF EXISTS action;

COMMENT ON TABLE audit_log IS
    'Append-only. UPDATE and DELETE are rewritten to no-ops so that history cannot be edited.';
