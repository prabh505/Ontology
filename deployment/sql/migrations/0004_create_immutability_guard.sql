-- 0004_create_immutability_guard.sql
--
-- Append-only enforcement, at the database, for every table holding a fact or an
-- addressed artifact. prd.md §54 requires immutable event history and that no inferred
-- result overwrite an observed fact; ADR-0004 requires that a correction emit a NEW event
-- rather than mutate one. Neither is a storage preference and neither may be left to
-- application discipline: the reasoning modules are not the only thing that can hold a
-- connection.
--
-- Two functions, because there are exactly two shapes of immutability in this schema.
--
--   causalog_refuse_mutation()      -- nothing may change. UPDATE and DELETE both raise.
--   causalog_close_system_period()  -- the ONE sanctioned mutation, attached in 0009
--                                      and 0010: closing a bi-temporal system period.
--                                      Every other column change, and any reopening,
--                                      raises.
--
-- Why a trigger that RAISES rather than a RULE that rewrites to nothing. 0002 used
-- `DO INSTEAD NOTHING`, which reports success for a write it discarded. A rejected write
-- that returns success is indistinguishable from an accepted one -- the DEF-0001 shape,
-- where a check that cannot fire reads exactly like a check that passed. 0014 replaces
-- those two rules with these triggers, and a regression test pins the behaviour.
--
-- The trigger is the second line of defence, not the only one: a deployment additionally
-- REVOKEs UPDATE and DELETE from the application role. The trigger exists because a
-- superuser connection, a migration, and a psql session all bypass a grant.
--
-- BEFORE vs AFTER, because the difference is load-bearing and not obvious.
-- `causalog_refuse_mutation` is a BEFORE trigger: it always raises, so it never needs to
-- look at a value. `causalog_close_system_period` COMPARES the old and new rows, and it is
-- attached AFTER for that reason: in a BEFORE trigger PostgreSQL has not yet computed the
-- GENERATED columns, so `NEW.held_over` is NULL while `OLD.held_over` holds a value, and
-- every legitimate retraction would look like a content change. Running AFTER, both rows
-- are fully materialised and the comparison is honest. Raising from an AFTER trigger still
-- aborts the transaction, so nothing is written either way.

CREATE OR REPLACE FUNCTION causalog_refuse_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'LAW-PROVENANCE: % on table "%" is refused. This table is append-only: an '
        'observed fact is never edited and never removed (prd.md §54, ADR-0004). A '
        'correction is a NEW row with a new content address; a retraction closes a '
        'system period, it does not delete history.',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;

COMMENT ON FUNCTION causalog_refuse_mutation() IS
    'BEFORE UPDATE OR DELETE guard for append-only tables. Raises; never silently discards. A discarded write that reports success is the DEF-0001 failure shape.';

-- ---------------------------------------------------------------------------
-- The bi-temporal guard. Attached in 0009 and 0010, defined here beside its sibling so
-- the two shapes of immutability are read together.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION causalog_close_system_period() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'LAW-PROVENANCE: DELETE on table "%" is refused. A belief the engine has '
            'abandoned is RETRACTED by closing its system period, never erased -- '
            'erasing it would make every past conclusion computed against it '
            'unauditable (ADR-0032).',
            TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- The single sanctioned mutation: close an open system period, once.
    IF OLD.system_to <> 'infinity'::timestamptz THEN
        RAISE EXCEPTION
            'LAW-PROVENANCE: the system period of a "%" row is already closed at %. '
            'Reopening a closed belief rewrites what the engine is recorded as having '
            'believed (ADR-0032).',
            TG_TABLE_NAME, OLD.system_to
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.system_to = 'infinity'::timestamptz THEN
        RAISE EXCEPTION
            'LAW-PROVENANCE: an UPDATE on "%" that leaves system_to open changes a '
            'recorded belief in place. The only admissible update closes the system '
            'period (ADR-0032).',
            TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.system_to <= OLD.system_from THEN
        RAISE EXCEPTION
            'LAW-PROVENANCE: system_to % is not after system_from % on "%". A belief '
            'cannot end before it began (ADR-0032).',
            NEW.system_to, OLD.system_from, TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- Every other column must be unchanged. The comparison is over the WHOLE row as
    -- jsonb, minus the two system-period columns, rather than over a per-table column
    -- list: a list would have to be maintained in step with every table this trigger
    -- guards, and the first column somebody added without updating it would become
    -- silently editable. Whole-row comparison cannot drift, and it covers columns added
    -- by a future migration for free.
    --
    -- A generated column rendering the same thing was the first attempt and does not
    -- work: PostgreSQL requires a generation expression to be IMMUTABLE, and every
    -- rendering of a `timestamptz` (`::text`, `to_char`) is only STABLE because it
    -- depends on the session TimeZone. Doing the comparison here, at trigger time,
    -- sidesteps that entirely.
    IF (to_jsonb(NEW) - 'system_from' - 'system_to')
       IS DISTINCT FROM (to_jsonb(OLD) - 'system_from' - 'system_to') THEN
        RAISE EXCEPTION
            'LAW-PROVENANCE: an UPDATE on "%" changed row content, not only the system '
            'period. A revised belief is INSERTed as a new row; the superseded one is '
            'closed, never edited (ADR-0032).',
            TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION causalog_close_system_period() IS
    'BEFORE UPDATE OR DELETE guard for bi-temporal tables. Admits exactly one mutation -- closing an open system period once -- and raises on every other change, on reopening, and on DELETE (ADR-0032).';
