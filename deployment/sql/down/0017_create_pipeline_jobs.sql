-- down/0017_create_pipeline_jobs.sql -- reverse of migrations/0017_create_pipeline_jobs.sql.
--
-- The triggers go with their tables; DROP TABLE removes them. They are named here anyway
-- so a reader of this file alone knows the append-only guard is being removed and not
-- merely detached.
DROP TABLE IF EXISTS idempotency_record;
DROP TABLE IF EXISTS pipeline_stage;
DROP TABLE IF EXISTS pipeline_job;
