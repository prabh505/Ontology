-- down/0002_create_audit_log.sql -- reverse of migrations/0002_create_audit_log.sql.
-- Dropping the table drops its rules with it.
DROP TABLE IF EXISTS audit_log;
