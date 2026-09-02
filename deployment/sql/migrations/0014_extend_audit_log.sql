-- 0014_extend_audit_log.sql
--
-- Two changes, and the second is a defect fix.
--
-- 1. prd.md §54 requires an audit record to name an ACTOR, an ACTION, a TARGET, a
--    TIMESTAMP, the BEFORE and AFTER state, and the request it arrived on. 0002 shipped
--    actor, a single `auditable_event`, a correlation id, a timestamp, and an
--    undifferentiated payload -- which is enough to record that something happened and
--    not enough to say what it happened TO or what changed. `action` and `target` split
--    the conflated `auditable_event`; `before` and `after` make a change inspectable
--    without re-deriving it.
--
--    `request_id` is NOT added. It is `correlation_id`, which CONVENTIONS.md §8 and
--    GLOSSARY.md already define as the identifier threading through one API request. A
--    second name for one concept is a defect by CONTEXT.md §5, so the synonym is recorded
--    in docs/data-model.md instead of minted here.
--
-- 2. DEF-0003. 0002 enforced append-only with
--        CREATE RULE ... ON UPDATE TO audit_log DO INSTEAD NOTHING
--    which REPORTS SUCCESS for a write it discarded. A rejected write that returns success
--    is indistinguishable from an accepted one, and an audit log that silently ignores an
--    UPDATE is worse than one that has none: the caller believes the edit landed. This is
--    the DEF-0001 shape -- a guard that cannot be observed to fire -- in the one table
--    whose whole purpose is being trustworthy. The rules are dropped and replaced with the
--    raising trigger every other fact table uses (0004).

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS action TEXT,
    ADD COLUMN IF NOT EXISTS target TEXT,
    ADD COLUMN IF NOT EXISTS target_kind TEXT,
    ADD COLUMN IF NOT EXISTS before_state JSONB,
    ADD COLUMN IF NOT EXISTS after_state JSONB;

COMMENT ON COLUMN audit_log.actor IS
    'Who or what performed the action. prd.md §54 requires role-based access and audit logging; an unattributed entry cannot discharge either.';
COMMENT ON COLUMN audit_log.action IS
    'What was done, from the CONVENTIONS.md §8 closed list. Split out of `auditable_event`, which conflated the verb with its subject.';
COMMENT ON COLUMN audit_log.target IS
    'The identifier acted upon -- an edge id, a run id, an endpoint path. Content-addressed wherever the target is an artifact, so an audit entry resolves back to the exact thing it describes.';
COMMENT ON COLUMN audit_log.target_kind IS
    'The artifact family `target` addresses, so a reader resolves it without parsing the prefix.';
COMMENT ON COLUMN audit_log.before_state IS
    'State before the action, canonical JSON. NULL for a creation, which is a meaningful NULL and not a missing value.';
COMMENT ON COLUMN audit_log.after_state IS
    'State after the action. For an append-only table the pair is (NULL, inserted); for a retraction it is (open belief, closed belief). The pair is what makes a change inspectable without re-deriving it.';
COMMENT ON COLUMN audit_log.correlation_id IS
    'The identifier threading through one API request. This IS what prd.md §54 and the persistence contract call a request id; CONVENTIONS.md §8 and GLOSSARY.md name it correlation_id, and one concept gets one name (CONTEXT.md §5).';

-- DEF-0003: replace silence with a raised exception.
DROP RULE IF EXISTS audit_log_no_update ON audit_log;
DROP RULE IF EXISTS audit_log_no_delete ON audit_log;

CREATE TRIGGER audit_log_is_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION causalog_refuse_mutation();

COMMENT ON TABLE audit_log IS
    'Append-only, enforced by a RAISING trigger. Until 0014 it was enforced by a rule that rewrote UPDATE and DELETE to no-ops, which reported success for a discarded write -- DEF-0003. The history is left visible here rather than tidied away.';

CREATE INDEX IF NOT EXISTS audit_log_by_target_idx
    ON audit_log (target, recorded_at DESC);
COMMENT ON INDEX audit_log_by_target_idx IS
    'Justifying query: "everything that has happened to this artifact" -- the LAW-EVIDENCE hook of CONVENTIONS.md §8, which requires that a confidence number be reconstructible from an audit record alone.';

CREATE INDEX IF NOT EXISTS audit_log_by_correlation_idx
    ON audit_log (correlation_id, audit_id)
    WHERE correlation_id IS NOT NULL;
COMMENT ON INDEX audit_log_by_correlation_idx IS
    'Justifying query: "everything one API request did" -- prd.md §54 access auditing, and the first query of any incident review. Partial, because pipeline-internal entries carry no request.';
