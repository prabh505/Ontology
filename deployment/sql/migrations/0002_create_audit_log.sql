-- 0002_create_audit_log.sql
--
-- The audit trail (CONVENTIONS.md §8). Append-only, retained independently of logs.
--
-- LAW-EVIDENCE hook: it must be possible, from an audit record alone, to reconstruct why
-- a confidence number has the value it has. An audit row that cannot do that means the
-- module that wrote it is not done.

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id         BIGSERIAL PRIMARY KEY,   -- storage surrogate; never crosses a module boundary
    run_id           TEXT        REFERENCES run (run_id),
    auditable_event  TEXT        NOT NULL,    -- CONVENTIONS.md §8 closed list
    actor            TEXT,
    correlation_id   TEXT,
    execution_id     TEXT,
    payload          JSONB       NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_run_idx ON audit_log (run_id, audit_id);

-- Append-only is enforced, not merely intended.
CREATE OR REPLACE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE OR REPLACE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;

COMMENT ON TABLE audit_log IS
    'Append-only. UPDATE and DELETE are rewritten to no-ops so that history cannot be edited.';
