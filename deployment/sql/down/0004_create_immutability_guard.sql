-- down/0004_create_immutability_guard.sql -- reverse of migrations/0004_create_immutability_guard.sql.
--
-- The triggers that reference these functions live in the migrations that create their
-- tables, and each of those reversals drops its own table (and with it its triggers), so
-- by the time this runs nothing depends on either function.

DROP FUNCTION IF EXISTS causalog_close_system_period();
DROP FUNCTION IF EXISTS causalog_refuse_mutation();
