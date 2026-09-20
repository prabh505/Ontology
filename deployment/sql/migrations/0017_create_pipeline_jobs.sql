-- 0017_create_pipeline_jobs.sql
--
-- The execution ledger: what a pipeline RUN ATTEMPT did, stage by stage.
--
-- A Run (ADR-0013) is a set of inputs, content-addressed, and identical inputs are the
-- same run whatever hour they started. That is exactly the property that makes a Run
-- unable to describe an attempt: two executions of one Run share a `run_id` by design, so
-- "which stages completed, how long each took, and where do I resume" has nowhere to live
-- on it. That belongs to the `execution_id` -- random, per-execution, and excluded from
-- every determinism comparison (CONVENTIONS.md §9).
--
-- WHY POSTGRES AND NOT REDIS. docs/architecture.md §3 states the rule in one line: if
-- losing it would change an answer it belongs in PostgreSQL; if losing it would only
-- change how fast an answer arrives it belongs in Redis. Losing a stage ledger changes an
-- answer -- a resumed job re-runs stages that already committed facts, or skips stages
-- that never did. ADR-0083.
--
-- WHY APPEND-ONLY, for a table that is not a fact table. `pipeline_stage` records
-- TRANSITIONS, not statuses. A mutable `status` column makes "this stage ran, failed, and
-- was retried" unrepresentable: the retry overwrites the failure and the ledger reports a
-- clean run that was not clean. A retry that leaves no trace is the precise failure a job
-- ledger exists to prevent, so the history is the rows and the current status is derived
-- by taking the newest transition. The same `causalog_refuse_mutation()` trigger from 0004
-- enforces it, for the reason 0014 gave when it replaced 0002's silent rules: a guard that
-- reports success for a write it discarded is worse than no guard.
--
-- `pipeline_job` is the one table here that is NOT append-only. It carries the derived
-- roll-up -- current status and the `run_id` once one is known -- and an execution moves
-- through PENDING -> RUNNING -> terminal, which is a mutation by nature. Its history is
-- fully reconstructible from `pipeline_stage`, so nothing is lost by letting it change;
-- the constraint below forbids the one transition that would lose information, namely
-- leaving a terminal state.

CREATE TABLE IF NOT EXISTS pipeline_job (
    execution_id     TEXT        PRIMARY KEY,
    run_id           TEXT        REFERENCES run (run_id),
    dataset_id       TEXT        NOT NULL,
    status           TEXT        NOT NULL,
    requested_by     TEXT        NOT NULL,
    correlation_id   TEXT,
    idempotency_key  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pipeline_job_status_is_declared CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')
    ),
    CONSTRAINT pipeline_job_dataset_non_empty CHECK (length(dataset_id) > 0),
    CONSTRAINT pipeline_job_actor_non_empty CHECK (length(requested_by) > 0)
);

COMMENT ON TABLE pipeline_job IS
    'One pipeline EXECUTION, keyed by execution_id. Not keyed by run_id: two executions of identical inputs share a run_id by design (ADR-0013), so the run cannot identify the attempt.';
COMMENT ON COLUMN pipeline_job.run_id IS
    'NULLABLE, and the NULL is meaningful. A run_id is not known until the packs, the pin and the seed resolve -- stage one''s job. An execution that refuses before that point has no run_id, and minting a placeholder would create an identifier that addresses nothing (CONVENTIONS.md §9).';
COMMENT ON COLUMN pipeline_job.status IS
    'PARTIAL is not a synonym for FAILED. A refusing stage blocks its dependents and every independent stage still runs (ADR-0083); reporting six-of-nine completed stages as FAILED discards work that is on disk and valid.';
COMMENT ON COLUMN pipeline_job.requested_by IS
    'The prd.md §54 actor. NOT NULL with no default: an unattributed execution cannot discharge the audit requirement, and a default would attribute every execution to whoever the default names.';
COMMENT ON COLUMN pipeline_job.idempotency_key IS
    'The client-supplied key that created this execution. A second request carrying the same key returns THIS execution rather than starting a second one.';

-- Partial and UNIQUE: a key identifies at most one execution, and executions started
-- without a key do not collide with each other on a shared NULL.
CREATE UNIQUE INDEX IF NOT EXISTS pipeline_job_idempotency_key_idx
    ON pipeline_job (idempotency_key)
    WHERE idempotency_key IS NOT NULL;
COMMENT ON INDEX pipeline_job_idempotency_key_idx IS
    'Justifying query: "has this exact request already been accepted?" -- the uniqueness IS the idempotency guarantee, enforced by the database rather than by a read-then-write race in the API.';

CREATE INDEX IF NOT EXISTS pipeline_job_recent_idx
    ON pipeline_job (created_at DESC, execution_id);
COMMENT ON INDEX pipeline_job_recent_idx IS
    'Justifying query: "the most recent executions" -- the job listing endpoint. execution_id is the tie-break so the sequence is total and a paged listing cannot repeat or drop a row.';

CREATE TABLE IF NOT EXISTS pipeline_stage (
    transition_id    BIGSERIAL   PRIMARY KEY,   -- storage surrogate; never crosses a module boundary
    execution_id     TEXT        NOT NULL REFERENCES pipeline_job (execution_id),
    stage_id         TEXT        NOT NULL,
    status           TEXT        NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    elapsed_seconds  DOUBLE PRECISION,
    error_code       TEXT,
    detail           TEXT,
    CONSTRAINT pipeline_stage_status_is_declared CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'BLOCKED', 'NOT_RUNNABLE')
    ),
    CONSTRAINT pipeline_stage_elapsed_is_non_negative CHECK (
        elapsed_seconds IS NULL OR elapsed_seconds >= 0
    ),
    -- A terminal status that is not SUCCEEDED must say why. A FAILED stage with no detail
    -- is an incident nobody can diagnose from the ledger, which is the only thing that
    -- survives the container.
    CONSTRAINT pipeline_stage_non_success_is_explained CHECK (
        status NOT IN ('FAILED', 'BLOCKED', 'NOT_RUNNABLE')
        OR (detail IS NOT NULL AND length(detail) > 0)
    )
);

COMMENT ON TABLE pipeline_stage IS
    'Append-only. Rows are TRANSITIONS, not statuses: the current status is the newest transition for a stage, derived rather than stored. A mutable status column would make a retry overwrite the failure it retried, and a retry that leaves no trace is what this ledger exists to prevent.';
COMMENT ON COLUMN pipeline_stage.status IS
    'NOT_RUNNABLE is distinct from FAILED and from a skip. A stage whose owning module has not been built did not fail -- it cannot run, and that is a fact about this repository rather than about this execution. It mirrors the exit-2 NOT-YET-RUNNABLE convention every scripts/check_*.py already uses: a gate that cannot run must never look like a gate that passed.';
COMMENT ON COLUMN pipeline_stage.elapsed_seconds IS
    'Measured, never estimated -- per-stage timing is a prd.md §55 obligation and an estimate would discharge it in appearance only. Excluded from determinism comparisons (CONVENTIONS.md §11 excludes performance measurements).';
COMMENT ON COLUMN pipeline_stage.detail IS
    'Why a non-SUCCEEDED terminal status happened: which module is missing, which prerequisite blocked, which error taxonomy member fired. Never a traceback and never a source record (CONVENTIONS.md §7).';

CREATE INDEX IF NOT EXISTS pipeline_stage_by_execution_idx
    ON pipeline_stage (execution_id, transition_id);
COMMENT ON INDEX pipeline_stage_by_execution_idx IS
    'Justifying query: "replay this execution''s history oldest first" -- what resumption folds over, and what the job-status endpoint renders.';

CREATE TRIGGER pipeline_stage_is_append_only
    BEFORE UPDATE OR DELETE ON pipeline_stage
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

-- The idempotency record for MUTATING API calls that are not pipeline executions
-- (prd.md §54 hardening, ADR-0084). Separate from pipeline_job.idempotency_key because it
-- answers a different question: that column says which execution a key started, this table
-- says what response a key already produced, for calls that start no execution at all.
CREATE TABLE IF NOT EXISTS idempotency_record (
    idempotency_key   TEXT        NOT NULL,
    endpoint          TEXT        NOT NULL,
    actor             TEXT        NOT NULL,
    request_digest    TEXT        NOT NULL,
    response_status   INTEGER     NOT NULL,
    response_body     JSONB       NOT NULL,
    correlation_id    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (idempotency_key, endpoint, actor),
    CONSTRAINT idempotency_record_body_is_an_object CHECK (
        jsonb_typeof(response_body) = 'object'
    ),
    CONSTRAINT idempotency_record_status_is_http CHECK (
        response_status BETWEEN 100 AND 599
    )
);

COMMENT ON TABLE idempotency_record IS
    'What a mutating request with a given key already returned. Replaying the stored response is what makes a retry safe; the key is scoped to the actor so one caller''s key cannot return another caller''s body.';
COMMENT ON COLUMN idempotency_record.request_digest IS
    'Content address of the request body. A second request reusing a key with a DIFFERENT body is a client defect and is refused (409), not served the first body -- silently returning an unrelated response is the failure idempotency is supposed to remove.';

CREATE TRIGGER idempotency_record_is_append_only
    BEFORE UPDATE OR DELETE ON idempotency_record
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
