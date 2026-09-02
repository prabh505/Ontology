-- 0013_create_run_scoped_artifacts.sql
--
-- Recommendations (module 14) and counterfactual scenarios (module 13).
--
-- THESE TABLES ARE DELIBERATELY UNDER-SPECIFIED, and the reason is recorded rather than
-- apologised for. `Intervention`, `SimulatedWorld`, and `RootCauseRanking` are all `draft`
-- in CONTEXT.md §6, and modules 13 and 14 do not exist. Inventing their columns here
-- would freeze a contract ahead of its module -- precisely the assertion-not-specification
-- failure OQ-009 existed to prevent -- and would do it in a place (a migration) where
-- reversing it costs a data migration rather than an edit.
--
-- So each table carries exactly what is ALREADY decided:
--
--   * run scoping, NOT NULL (ADR-0013). No inferred artifact exists without a run.
--   * a content-addressed identifier, per the recipe its module will use.
--   * the provenance class, constrained. A simulated world is SIMULATED, always.
--   * the output envelope fields a persisted artifact must carry (CONVENTIONS.md §11).
--   * `payload jsonb` holding `to_canonical_json` output -- the canonical wire form, with
--     its own schema_version inside it, so the artifact is re-validatable on read even
--     though this schema cannot describe it.
--
-- OQ-017 tracks the normalization, with "normalize when modules 13 and 14 freeze their
-- types" as the stated default. The jsonb here is a HOLDING SHAPE, not a modelling
-- preference: everywhere else in this schema a value the database must sort, join, or
-- constrain gets a column.

CREATE TABLE IF NOT EXISTS recommendation (
    recommendation_id   TEXT        PRIMARY KEY,
    run_id              TEXT        NOT NULL REFERENCES run (run_id),
    provenance_class    TEXT        NOT NULL,
    payload             JSONB       NOT NULL,
    canonical_schema_version TEXT   NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT recommendation_provenance_is_declared CHECK (
        provenance_class IN ('ASSUMED', 'STATISTICAL', 'INFERRED', 'SIMULATED')
    ),
    CONSTRAINT recommendation_payload_is_an_object CHECK (jsonb_typeof(payload) = 'object')
);

COMMENT ON TABLE recommendation IS
    'A ranked intervention proposal (module 14). Under-specified by intent: Intervention is still a draft contract, and inventing its columns would freeze it ahead of its module. Tracked as OQ-017.';
COMMENT ON COLUMN recommendation.run_id IS
    'NOT NULL with no default, like every inferred artifact. The system recommends and a human decides (prd.md §6); the run scoping is what lets a recommendation be traced back to the exact inputs that produced it.';
COMMENT ON COLUMN recommendation.provenance_class IS
    'Never OBSERVED. A recommendation is a claim about what WOULD help, and cost inputs are ASSUMED ordinal bands, never inferred (ADR-0008 / OQ-013).';
COMMENT ON COLUMN recommendation.payload IS
    'to_canonical_json output. Holding shape only -- see this migration''s header and OQ-017. The embedded schema_version lets a reader re-validate the artifact this schema cannot describe.';

CREATE TABLE IF NOT EXISTS counterfactual_scenario (
    simulated_world_id   TEXT        PRIMARY KEY,  -- sim:<sha256(base_graph_id|mutations)[:16]>
    run_id               TEXT        NOT NULL REFERENCES run (run_id),
    base_graph_id        TEXT        NOT NULL,
    provenance_class     TEXT        NOT NULL,
    assumption_statement TEXT        NOT NULL,
    payload              JSONB       NOT NULL,
    canonical_schema_version TEXT    NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT counterfactual_scenario_is_simulated CHECK (provenance_class = 'SIMULATED'),
    CONSTRAINT counterfactual_scenario_assumption_non_empty CHECK (length(assumption_statement) > 0),
    CONSTRAINT counterfactual_scenario_payload_is_an_object CHECK (jsonb_typeof(payload) = 'object')
);

COMMENT ON TABLE counterfactual_scenario IS
    'One simulated world (module 13). Nothing here is ever written back into facts: SIMULATED may never overwrite OBSERVED, and the schema enforces it by having no path from this table into any fact table (docs/architecture.md §6.3).';
COMMENT ON COLUMN counterfactual_scenario.provenance_class IS
    'Constrained to SIMULATED, the single admissible value. A simulated figure presented as a prediction is the overclaiming risk R-11; the constraint makes the label unremovable.';
COMMENT ON COLUMN counterfactual_scenario.assumption_statement IS
    'The explicit no-unobserved-confounder statement, NOT NULL and non-empty. V1 output is a PLAUSIBILITY SIMULATION, not a causal effect estimate (OQ-007); dropping this statement from the envelope is forbidden, so it cannot be stored absent.';
COMMENT ON COLUMN counterfactual_scenario.base_graph_id IS
    'The frozen base world the mutations were applied to a COPY of. Part of the sim: address recipe, so two simulations over one base with one mutation set are one row.';

CREATE INDEX IF NOT EXISTS recommendation_by_run_idx
    ON recommendation (run_id, recommendation_id);
COMMENT ON INDEX recommendation_by_run_idx IS
    'Justifying query: GET /recommendations (prd.md §53), always run-scoped. On the prd.md §55 <5s recommendation path.';

CREATE INDEX IF NOT EXISTS counterfactual_scenario_by_run_idx
    ON counterfactual_scenario (run_id, simulated_world_id);
COMMENT ON INDEX counterfactual_scenario_by_run_idx IS
    'Justifying query: GET /counterfactual (prd.md §53), always run-scoped. On the prd.md §55 <5s counterfactual path.';

CREATE TRIGGER recommendation_is_append_only
    BEFORE UPDATE OR DELETE ON recommendation
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

CREATE TRIGGER counterfactual_scenario_is_append_only
    BEFORE UPDATE OR DELETE ON counterfactual_scenario
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();
