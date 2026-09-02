-- down/0009_create_states_and_transitions.sql -- reverse of migrations/0009_create_states_and_transitions.sql.
--
-- The extension is dropped too, so `migrate` -> `migrate-down` returns the database to
-- the state it was in. It is dropped last and without CASCADE: if anything outside this
-- migration has come to depend on btree_gist, the reversal fails loudly rather than
-- taking that dependant with it.

DROP TABLE IF EXISTS state_evidence;
DROP TABLE IF EXISTS state_transition;
DROP TABLE IF EXISTS state;
DROP EXTENSION IF EXISTS btree_gist;
