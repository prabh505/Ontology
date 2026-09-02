-- down/0003_create_version_registries.sql -- reverse of migrations/0003_create_version_registries.sql.
--
-- Drops the foreign keys before the tables they point at, so the reversal succeeds
-- whatever order the planner would otherwise choose.

ALTER TABLE run
    DROP CONSTRAINT IF EXISTS run_rule_pack_version_fk,
    DROP CONSTRAINT IF EXISTS run_ontology_hash_fk,
    DROP CONSTRAINT IF EXISTS run_dataset_version_fk;

DROP TABLE IF EXISTS rule_pack_version;
DROP TABLE IF EXISTS ontology_version;
DROP TABLE IF EXISTS dataset_version;
