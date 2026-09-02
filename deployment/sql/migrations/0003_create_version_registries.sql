-- 0003_create_version_registries.sql
--
-- The three version registries that, with `engine_version` and `seed`, determine a
-- `run_id` (ADR-0013). Each row is a pin: an immutable statement that a named version of
-- an input existed and had exactly this content.
--
-- These tables are the reason `run` can carry foreign keys rather than free text. A run
-- naming a dataset version nobody registered is unreproducible by construction, and the
-- constraint says so at insert rather than at re-derivation time.
--
-- Every table here is append-only. A version is never edited: a changed input is a new
-- version, which is the whole content-addressing premise (CONVENTIONS.md §9).

-- ---------------------------------------------------------------------------
-- dataset_version -- prd.md §54 "dataset versioning"; ADR-0013 input 1
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dataset_version (
    dataset_version   TEXT PRIMARY KEY,
    source_locator    TEXT        NOT NULL,   -- opaque; never the raw record, never a credential
    source_sha256     TEXT        NOT NULL,   -- the pinned file hash; a mismatch is a hard error
    record_count      BIGINT      NOT NULL,
    accepted_count    BIGINT      NOT NULL,
    rejected_count    BIGINT      NOT NULL,
    registered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT dataset_version_counts_reconcile
        CHECK (accepted_count + rejected_count = record_count),
    CONSTRAINT dataset_version_counts_non_negative
        CHECK (accepted_count >= 0 AND rejected_count >= 0)
);

COMMENT ON TABLE dataset_version IS
    'One pinned external dataset. Two datasets differing by one byte are two rows and two Runs; their conclusions are not comparable (ADR-0013).';
COMMENT ON COLUMN dataset_version.source_sha256 IS
    'The hash module 1 pins. A source whose hash no longer matches is a hard error, never a silent substitution -- a substituted dataset invalidates every run_id built on it.';
COMMENT ON COLUMN dataset_version.rejected_count IS
    'Malformed records are rejected and COUNTED, never repaired (CONVENTIONS.md §7). A rejected record still appears in the run summary.';
COMMENT ON COLUMN dataset_version.registered_at IS
    'Wall-clock. Excluded from every determinism comparison and never an input to reasoning.';

-- ---------------------------------------------------------------------------
-- ontology_version -- ADR-0026, ADR-0028; ADR-0013 input 2
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ontology_version (
    ontology_hash        TEXT PRIMARY KEY,    -- ont:<sha256(to_canonical_json(resolved_pack))[:16]>
    pack_id              TEXT        NOT NULL,
    ontology_version     TEXT        NOT NULL,-- the pack's own semver
    pack_schema_version  TEXT        NOT NULL,-- the DSL version; same for every pack
    extends_pack_id      TEXT,                -- NULL for a base pack
    resolved_pack        JSONB       NOT NULL,-- the canonical JSON the hash addresses
    registered_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pack_id, ontology_version)
);

COMMENT ON TABLE ontology_version IS
    'One resolved domain pack. The ontology decides what an event IS, so a different pack is a different reading of the same bytes and therefore a different Run (ADR-0026).';
COMMENT ON COLUMN ontology_version.ontology_hash IS
    'digest(ONTOLOGY, to_canonical_json(resolved_pack)) (ADR-0028). The primary key IS the content, so a stored pack that disagrees with its hash cannot exist.';
COMMENT ON COLUMN ontology_version.resolved_pack IS
    'The base-plus-overlay resolution, not the source YAML. Stored so a past run can be re-read against the pack it actually used rather than against the pack the file holds today.';
COMMENT ON COLUMN ontology_version.pack_schema_version IS
    'Versions the DSL itself, not the pack. Two numbers deliberately (CONTEXT.md §7).';

-- ---------------------------------------------------------------------------
-- rule_pack_version -- prd.md §46; ADR-0013 input 3
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rule_pack_version (
    rule_pack_version  TEXT PRIMARY KEY,
    pack_id            TEXT        NOT NULL,
    rule_ids           TEXT[]      NOT NULL,  -- sorted; the fired-rule references in evidence resolve here
    content_sha256     TEXT        NOT NULL,
    registered_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT rule_pack_version_rules_non_empty CHECK (cardinality(rule_ids) > 0)
);

COMMENT ON TABLE rule_pack_version IS
    'One loaded, conflict-checked rule pack. Rules are data, not code (prd.md §46); editing one changes the causal graph and therefore mints a new Run.';
COMMENT ON COLUMN rule_pack_version.rule_ids IS
    'Sorted rule identifiers. An EvidenceItem of kind RULE names one of these, and the citation must resolve or the item is unverifiable (docs/contracts.md §5).';

-- ---------------------------------------------------------------------------
-- Tie the run registry to the pins it names.
-- ---------------------------------------------------------------------------
ALTER TABLE run
    ADD CONSTRAINT run_dataset_version_fk
        FOREIGN KEY (dataset_version) REFERENCES dataset_version (dataset_version),
    ADD CONSTRAINT run_ontology_hash_fk
        FOREIGN KEY (ontology_hash) REFERENCES ontology_version (ontology_hash),
    ADD CONSTRAINT run_rule_pack_version_fk
        FOREIGN KEY (rule_pack_version) REFERENCES rule_pack_version (rule_pack_version);

COMMENT ON CONSTRAINT run_dataset_version_fk ON run IS
    'A Run may not name an unregistered input. Reproducibility is the point of the five-tuple; an unpinned input makes it a wish (ADR-0013).';
