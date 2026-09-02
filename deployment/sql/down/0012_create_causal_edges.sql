-- down/0012_create_causal_edges.sql -- reverse of migrations/0012_create_causal_edges.sql.
DROP TABLE IF EXISTS causal_edge_fired_rule;
DROP TABLE IF EXISTS causal_edge_co_cause;
DROP TABLE IF EXISTS causal_edge_evidence;
DROP TABLE IF EXISTS causal_edge;
