-- down/0008_create_events.sql -- reverse of migrations/0008_create_events.sql.
DROP TABLE IF EXISTS event_evidence;
DROP TABLE IF EXISTS event_metadata;
DROP TABLE IF EXISTS event_changed_attribute;
DROP TABLE IF EXISTS event_entity;
DROP TABLE IF EXISTS event;
