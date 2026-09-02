-- down/0015_create_projection_registry.sql -- reverse of migrations/0015_create_projection_registry.sql.
DROP TABLE IF EXISTS graph_projection;
DROP FUNCTION IF EXISTS causalog_projection_status_ladder();
