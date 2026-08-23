-- 0001_create_run_registry.sql
--
-- The Run registry (ADR-0013). A Run is the unit of reproducibility: the five inputs
-- that can change engine output, condensed into one content-addressed identifier.
--
-- Every inferred artifact is scoped to a run_id. Observed facts are NOT run-scoped; they
-- are dataset-scoped. That asymmetry is what makes "inference never overwrites
-- observation" (LAW-PROVENANCE) structural rather than procedural.
--
-- No table in this migration is ever UPDATEd or DELETEd from. Immutable event history is
-- a product requirement (prd.md §54), not a storage preference.

CREATE TABLE IF NOT EXISTS run (
    run_id                   TEXT PRIMARY KEY,   -- run:<sha256(...)[:16]>
    dataset_version          TEXT        NOT NULL,
    ontology_hash            TEXT        NOT NULL,
    ontology_version         TEXT        NOT NULL,
    rule_pack_version        TEXT        NOT NULL,
    engine_version           TEXT        NOT NULL,
    seed                     BIGINT      NOT NULL,
    graph_projection_version TEXT,               -- NULL until module 8 projects the run
    registered_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dataset_version, ontology_hash, rule_pack_version, engine_version, seed)
);

COMMENT ON TABLE run IS
    'Unit of reproducibility. Identical five-tuple implies identical run_id implies byte-identical artifacts (CONVENTIONS.md §11).';
COMMENT ON COLUMN run.registered_at IS
    'Wall-clock, excluded from every determinism comparison. Never an input to reasoning.';
