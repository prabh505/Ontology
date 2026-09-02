-- 0015_create_projection_registry.sql
--
-- The projection registry: PostgreSQL's record of what the derived graph store currently
-- holds. ADR-0001 makes Neo4j a projection with NO authority, which means the answer to
-- "which namespace is live for this run, and is it the one I think it is" must live HERE,
-- in the system of record, and not be discovered by asking the projection about itself.
--
-- It drives the six-step rebuild of docs/architecture.md §3.3:
--
--   stage   -- INSERT a row with status 'staged' and a fresh namespace. The live namespace
--              is never mutated in place, so a failed rebuild leaves the previous
--              projection serving.
--   verify  -- compare node_count, edge_count, and content_hash against the values
--              computed from the facts. A mismatch aborts BEFORE any swap.
--   swap    -- one transaction: the staged row becomes 'live', the previous live row
--              becomes 'superseded'. The partial unique index below makes "two live
--              projections for one run" unrepresentable rather than merely unlikely.
--   assert  -- for the same run_id, the rebuilt content_hash must equal the prior build's.
--              A mismatch is a DETERMINISM DEFECT, not a retryable error: it means
--              something in the pipeline is not a function of its inputs.
--
-- The row is the only thing in this schema that is legitimately UPDATEd, and only along
-- the status ladder staged -> live -> superseded. A projection build is not a fact; it is
-- an operational record of a derived store, and the facts it was derived from are
-- untouched by every transition.

CREATE TABLE IF NOT EXISTS graph_projection (
    projection_id             BIGSERIAL   PRIMARY KEY,
    run_id                    TEXT        NOT NULL REFERENCES run (run_id),
    graph_projection_version  TEXT        NOT NULL,
    namespace                 TEXT        NOT NULL,
    content_hash              TEXT        NOT NULL,
    node_count                BIGINT      NOT NULL,
    edge_count                BIGINT      NOT NULL,
    status                    TEXT        NOT NULL,
    built_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at             TIMESTAMPTZ,
    CONSTRAINT graph_projection_status_is_declared CHECK (
        status IN ('staged', 'live', 'superseded', 'failed')
    ),
    CONSTRAINT graph_projection_counts_non_negative CHECK (node_count >= 0 AND edge_count >= 0),
    CONSTRAINT graph_projection_superseded_has_an_instant CHECK (
        (status = 'superseded') = (superseded_at IS NOT NULL)
    ),
    UNIQUE (namespace)
);

COMMENT ON TABLE graph_projection IS
    'What the derived graph store holds, recorded in the system of record. Neo4j has no authority (ADR-0001), so it is never asked which projection is current -- this table is.';
COMMENT ON COLUMN graph_projection.graph_projection_version IS
    'gpv:<sha256(run_id|content_hash)[:16]>. Stamped on every graph query response so staleness is detectable; a reader asking for a version the store is not serving gets ProjectionStaleError rather than an older graph (docs/architecture.md §3.2).';
COMMENT ON COLUMN graph_projection.namespace IS
    'The staging namespace this build wrote into. Unique, so a rebuild cannot silently reuse a namespace another build is still serving from.';
COMMENT ON COLUMN graph_projection.content_hash IS
    'A canonical hash of the projected content. Compared against the value computed from PostgreSQL before the swap, and against the PRIOR build for the same run afterwards. A mismatch on the second comparison is a determinism defect, never a retry (docs/architecture.md §3.3 step 6).';
COMMENT ON COLUMN graph_projection.status IS
    'staged -> live -> superseded, or staged -> failed. The one legitimate UPDATE path in this schema, and only along that ladder: a projection build is an operational record of a derived store, not a fact.';

CREATE UNIQUE INDEX IF NOT EXISTS graph_projection_one_live_per_run_idx
    ON graph_projection (run_id)
    WHERE status = 'live';
COMMENT ON INDEX graph_projection_one_live_per_run_idx IS
    'Makes "two live projections for one run" unrepresentable rather than merely unlikely, so the alias swap is atomic by construction: the second live insert conflicts instead of racing.';

CREATE INDEX IF NOT EXISTS graph_projection_history_idx
    ON graph_projection (run_id, built_at DESC);
COMMENT ON INDEX graph_projection_history_idx IS
    'Justifying query: "what was the previous build''s content hash for this run" -- step 6 of the rebuild, the determinism assertion.';

-- The status ladder, enforced. A projection row may move forward and never backward, and
-- nothing but its status, superseded_at, and the verification counts may change.
CREATE OR REPLACE FUNCTION causalog_projection_status_ladder() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'A projection build record is not deleted. A superseded build is marked '
            'superseded so the determinism comparison in docs/architecture.md §3.3 step 6 '
            'still has a prior hash to compare against.'
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF (OLD.run_id, OLD.namespace, OLD.built_at) IS DISTINCT FROM
       (NEW.run_id, NEW.namespace, NEW.built_at) THEN
        RAISE EXCEPTION
            'A projection build record may change only its status, its supersession '
            'instant, and its verification counts. Rewriting which run or namespace it '
            'describes would make the registry disagree with the store it describes.'
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NOT (
        (OLD.status = 'staged' AND NEW.status IN ('live', 'failed'))
        OR (OLD.status = 'live' AND NEW.status = 'superseded')
        OR (OLD.status = NEW.status)
    ) THEN
        RAISE EXCEPTION
            'Projection status may not move % -> %. The ladder is staged -> live -> '
            'superseded, or staged -> failed; a build that went backwards would leave the '
            'store serving a version this registry says is retired.',
            OLD.status, NEW.status
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION causalog_projection_status_ladder() IS
    'Confines graph_projection to a forward-only status ladder and refuses DELETE, so the prior build''s hash always survives for the determinism assertion.';

CREATE TRIGGER graph_projection_follows_the_status_ladder
    BEFORE UPDATE OR DELETE ON graph_projection
    FOR EACH ROW EXECUTE FUNCTION causalog_projection_status_ladder();
