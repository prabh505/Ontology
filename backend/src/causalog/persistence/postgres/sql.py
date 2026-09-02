"""Every SQL statement this package issues, as named constants.

Explicit queries, not a builder and not an ORM. Three reasons, in the order they matter
here:

1. **Canonical sequence is visible.** `CONVENTIONS.md` §11 requires every read to carry an
   explicit `ORDER BY` on a unique key. Written out, a missing `ORDER BY` is a diff anyone
   can see; generated, it is a default somebody has to know about.
2. **No hidden round trip.** A lazily loaded relationship on the largest table in the
   system turns one canonical read into one query per row, and the calling code looks
   identical either way. Every fetch here is a statement somebody wrote.
3. **The column order is the contract** between these statements and `rows.py`. Keeping
   both in view makes a mismatch a two-file diff instead of an inference.

Statements that read a child collection take an array of parent identifiers and return
`(parent_id, …)` pairs, so a batch of parents costs one round trip rather than one each.
That is the explicit alternative to lazy loading, and it is why there is no N+1 here.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "COUNT_FACTS_FOR_DATASET",
    "DELETE_NOTHING",
    "INSERT_AUDIT_ENTRY",
    "INSERT_CAUSAL_EDGE",
    "INSERT_CONFIDENCE_COMPONENT",
    "INSERT_CONFIDENCE_VECTOR",
    "INSERT_ENTITY",
    "INSERT_EVENT",
    "INSERT_EVIDENCE_RECORD",
    "INSERT_RUN",
    "INSERT_STATE",
    "RETRACT_STATES",
    "SELECT_CAUSAL_EDGES_FOR_RUN",
    "SELECT_ENTITIES_FOR_DATASET",
    "SELECT_EVENTS_FOR_DATASET",
    "SELECT_EVENTS_FOR_ENTITY",
    "SELECT_RELATIONSHIPS_FOR_DATASET",
    "SELECT_RUN",
    "SELECT_STATES_AS_BELIEVED_AT",
    "SELECT_STATES_FOR_DATASET",
    "SELECT_TRANSITIONS_FOR_DATASET",
]

# ---------------------------------------------------------------------------
# The run registry
# ---------------------------------------------------------------------------

#: Idempotent by the natural key: two executions of one Run are one Run (ADR-0013), so a
#: second registration returns the existing identifier rather than minting a second row.
#: `DO UPDATE SET run_id = EXCLUDED.run_id` rather than `DO NOTHING` because `DO NOTHING`
#: returns no row, and the caller needs the identifier back on both paths.
INSERT_RUN: Final[str] = """
INSERT INTO run (run_id, dataset_version, ontology_hash, ontology_version,
                 rule_pack_version, engine_version, seed)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (dataset_version, ontology_hash, rule_pack_version, engine_version, seed)
DO UPDATE SET run_id = run.run_id
RETURNING run_id
"""

SELECT_RUN: Final[str] = """
SELECT run_id, dataset_version, ontology_hash, rule_pack_version, engine_version,
       seed, registered_at
FROM run
WHERE run_id = %s
"""

# ---------------------------------------------------------------------------
# Observed facts -- writes
# ---------------------------------------------------------------------------

INSERT_EVIDENCE_RECORD: Final[str] = """
INSERT INTO evidence_record (evidence_record_id, dataset_version, source_locator, source_timezone)
VALUES (%s, %s, %s, %s)
ON CONFLICT (evidence_record_id) DO NOTHING
"""

INSERT_ENTITY: Final[str] = """
INSERT INTO entity (entity_id, dataset_version, ontology_hash, entity_type, natural_key,
                    provenance_class)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (entity_id) DO NOTHING
"""

INSERT_EVENT: Final[str] = """
INSERT INTO event (event_id, dataset_version, ontology_hash, event_type,
                   t_earliest, t_latest, time_precision, time_provenance, time_source,
                   trigger_mechanism, provenance_class, confidence_vector_id,
                   is_actionable, source_record_ref)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (event_id) DO NOTHING
"""

#: `system_from` is SUPPLIED, not left to the column default. `CONVENTIONS.md` §11: time
#: is injected, never read -- the instant comes from the `Clock` port. Relying on `now()`
#: would also make the bi-temporal behaviour untestable, because a test cannot assert an
#: as-of read against an instant it did not choose.
INSERT_STATE: Final[str] = """
INSERT INTO state (state_id, entity_id, dataset_version, state_name,
                   valid_from, valid_to, valid_precision, valid_provenance, valid_source,
                   derived_from_event_id, provenance_class, system_from)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""

#: The one sanctioned mutation in the fact store: close an open system period (ADR-0032).
#: `WHERE system_to = 'infinity'` means a second retraction of an already-closed belief
#: touches nothing and reports zero, rather than reaching the trigger and raising -- a
#: repeated retraction is idempotent, an *edit* is what raises.
RETRACT_STATES: Final[str] = """
UPDATE state
SET system_to = %s
WHERE state_id = ANY(%s) AND system_to = 'infinity'::timestamptz
"""

INSERT_CONFIDENCE_VECTOR: Final[str] = """
INSERT INTO confidence_vector (scalar, aggregation, provenance_class)
VALUES (%s, %s, %s)
RETURNING confidence_vector_id
"""

INSERT_CONFIDENCE_COMPONENT: Final[str] = """
INSERT INTO confidence_component (confidence_vector_id, component_name, value, provenance_class)
VALUES (%s, %s, %s, %s)
"""

INSERT_CAUSAL_EDGE: Final[str] = """
INSERT INTO causal_edge (causal_edge_id, run_id, source_event_id, target_event_id,
                         edge_kind, confidence_vector_id, propagation_weight,
                         provenance_class, temporal_verdict, temporally_unverifiable,
                         condition_expression, condition_holds, joint_cause_group_id,
                         magnitude_multiplier)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (causal_edge_id) DO NOTHING
"""

# ---------------------------------------------------------------------------
# Observed facts -- reads, every one in canonical sequence
# ---------------------------------------------------------------------------

#: Sequenced by `entity_id` (docs/architecture.md §3.3 step 3).
SELECT_ENTITIES_FOR_DATASET: Final[str] = """
SELECT entity_id, entity_type, natural_key, provenance_class
FROM entity
WHERE dataset_version = %s
ORDER BY entity_id
"""

#: Sequenced by `(t_earliest, t_latest, event_id)` -- the canonical event sequence of
#: `CONVENTIONS.md` §11. The index `event_canonical_sequence_idx` exists for this
#: statement and names it.
SELECT_EVENTS_FOR_DATASET: Final[str] = """
SELECT event_id, event_type, t_earliest, t_latest, time_precision, time_provenance,
       time_source, trigger_mechanism, provenance_class, is_actionable, source_record_ref,
       confidence_vector_id
FROM event
WHERE dataset_version = %s
ORDER BY t_earliest, t_latest, event_id
"""

#: `GET /timeline/{ref}` (prd.md §53). Served by `event_entity_timeline_idx`.
SELECT_EVENTS_FOR_ENTITY: Final[str] = """
SELECT e.event_id, e.event_type, e.t_earliest, e.t_latest, e.time_precision,
       e.time_provenance, e.time_source, e.trigger_mechanism, e.provenance_class,
       e.is_actionable, e.source_record_ref, e.confidence_vector_id
FROM event AS e
JOIN event_entity AS ee ON ee.event_id = e.event_id
WHERE ee.entity_id = %s
ORDER BY e.t_earliest, e.t_latest, e.event_id
"""

#: Current beliefs only. A past belief is a different call (`SELECT_STATES_AS_BELIEVED_AT`)
#: so that an ordinary read cannot return stale history by accident (ADR-0032).
SELECT_STATES_FOR_DATASET: Final[str] = """
SELECT state_id, entity_id, state_name, valid_from, valid_to, valid_precision,
       valid_provenance, valid_source, derived_from_event_id, provenance_class
FROM state
WHERE dataset_version = %s AND system_to = 'infinity'::timestamptz
ORDER BY state_id
"""

#: The bi-temporal read: what this system believed at a past instant. The predicate is
#: half-open on the upper bound -- `system_from <= t < system_to` -- so a belief closed at
#: exactly `t` is not returned by a query as of `t`. A closed period ends at its closing
#: instant; including it would return two beliefs for one state at the moment of
#: retraction, which `core.derivation.current_state` treats as a contradiction.
SELECT_STATES_AS_BELIEVED_AT: Final[str] = """
SELECT state_id, entity_id, state_name, valid_from, valid_to, valid_precision,
       valid_provenance, valid_source, derived_from_event_id, provenance_class
FROM state
WHERE dataset_version = %s AND system_from <= %s AND %s < system_to
ORDER BY state_id
"""

SELECT_TRANSITIONS_FOR_DATASET: Final[str] = """
SELECT transition_id, from_state_id, to_state_id, causing_event_id, provenance_class
FROM state_transition
WHERE dataset_version = %s AND system_to = 'infinity'::timestamptz
ORDER BY transition_id
"""

SELECT_RELATIONSHIPS_FOR_DATASET: Final[str] = """
SELECT relationship_id, relationship_type, source_entity_id, target_entity_id,
       valid_from, valid_to, valid_precision, valid_provenance, valid_source,
       provenance_class
FROM relationship
WHERE dataset_version = %s AND system_to = 'infinity'::timestamptz
ORDER BY relationship_id
"""

#: Sequenced by `(source_event_id, target_event_id, edge_kind)` -- the canonical edge
#: sequence. Run-scoped first, always: a query that forgot the run would read another
#: run's inferences.
SELECT_CAUSAL_EDGES_FOR_RUN: Final[str] = """
SELECT causal_edge_id, source_event_id, target_event_id, propagation_weight,
       provenance_class, temporal_verdict, temporally_unverifiable, run_id,
       edge_kind, confidence_vector_id, condition_expression, condition_holds,
       joint_cause_group_id, magnitude_multiplier
FROM causal_edge
WHERE run_id = %s
ORDER BY source_event_id, target_event_id, edge_kind
"""

# ---------------------------------------------------------------------------
# Child collections -- batched by parent, never one query per parent
# ---------------------------------------------------------------------------

SELECT_ENTITY_ATTRIBUTES: Final[str] = """
SELECT entity_id, attribute_name, attribute_value
FROM entity_attribute
WHERE entity_id = ANY(%s)
ORDER BY entity_id, attribute_name
"""

SELECT_ENTITY_LIFECYCLE_STATES: Final[str] = """
SELECT entity_id, state_name
FROM entity_lifecycle_state
WHERE entity_id = ANY(%s)
ORDER BY entity_id, state_name
"""

SELECT_ENTITY_LIFECYCLE_TRANSITIONS: Final[str] = """
SELECT entity_id, from_state_name, to_state_name
FROM entity_lifecycle_transition
WHERE entity_id = ANY(%s)
ORDER BY entity_id, from_state_name, to_state_name
"""

SELECT_ENTITY_EVIDENCE: Final[str] = """
SELECT entity_id, evidence_record_id
FROM entity_evidence
WHERE entity_id = ANY(%s)
ORDER BY entity_id, evidence_record_id
"""

SELECT_EVENT_PARTICIPANTS: Final[str] = """
SELECT event_id, entity_id, participation_role
FROM event_entity
WHERE event_id = ANY(%s)
ORDER BY event_id, participation_role, entity_id
"""

SELECT_EVENT_CHANGED_ATTRIBUTES: Final[str] = """
SELECT event_id, attribute_name, attribute_value
FROM event_changed_attribute
WHERE event_id = ANY(%s)
ORDER BY event_id, attribute_name
"""

SELECT_EVENT_METADATA: Final[str] = """
SELECT event_id, metadata_name, metadata_value
FROM event_metadata
WHERE event_id = ANY(%s)
ORDER BY event_id, metadata_name
"""

SELECT_EVENT_EVIDENCE: Final[str] = """
SELECT event_id, evidence_record_id
FROM event_evidence
WHERE event_id = ANY(%s)
ORDER BY event_id, evidence_record_id
"""

SELECT_STATE_EVIDENCE: Final[str] = """
SELECT state_id, evidence_record_id
FROM state_evidence
WHERE state_id = ANY(%s)
ORDER BY state_id, evidence_record_id
"""

SELECT_RELATIONSHIP_EVIDENCE: Final[str] = """
SELECT relationship_id, evidence_record_id
FROM relationship_evidence
WHERE relationship_id = ANY(%s)
ORDER BY relationship_id, evidence_record_id
"""

SELECT_CONFIDENCE_VECTORS: Final[str] = """
SELECT confidence_vector_id, scalar, aggregation, provenance_class
FROM confidence_vector
WHERE confidence_vector_id = ANY(%s)
ORDER BY confidence_vector_id
"""

#: Components come back already sorted by name, which is the order `ConfidenceVector`
#: requires. Sorting in Python instead would hide an unsequenced read behind a repair.
SELECT_CONFIDENCE_COMPONENTS: Final[str] = """
SELECT c.confidence_vector_id, c.component_name, c.value, c.provenance_class,
       COALESCE(array_agg(e.evidence_record_id ORDER BY e.evidence_record_id)
                FILTER (WHERE e.evidence_record_id IS NOT NULL), '{}') AS evidence_record_ids
FROM confidence_component AS c
LEFT JOIN confidence_component_evidence AS e
       ON e.confidence_vector_id = c.confidence_vector_id
      AND e.component_name = c.component_name
WHERE c.confidence_vector_id = ANY(%s)
GROUP BY c.confidence_vector_id, c.component_name, c.value, c.provenance_class
ORDER BY c.confidence_vector_id, c.component_name
"""

SELECT_CAUSAL_EDGE_CO_CAUSES: Final[str] = """
SELECT causal_edge_id, co_cause_event_id
FROM causal_edge_co_cause
WHERE causal_edge_id = ANY(%s)
ORDER BY causal_edge_id, co_cause_event_id
"""

SELECT_CAUSAL_EDGE_EVIDENCE_ITEMS: Final[str] = """
SELECT ce.causal_edge_id, i.evidence_item_id, i.kind, i.description, i.strength,
       i.verification, i.provenance_class,
       COALESCE(array_agg(s.supporting_id ORDER BY s.supporting_id)
                FILTER (WHERE s.supporting_id IS NOT NULL), '{}') AS supporting_ids
FROM causal_edge_evidence AS ce
JOIN evidence_item AS i ON i.evidence_item_id = ce.evidence_item_id
LEFT JOIN evidence_item_support AS s ON s.evidence_item_id = i.evidence_item_id
WHERE ce.causal_edge_id = ANY(%s)
GROUP BY ce.causal_edge_id, i.evidence_item_id, i.kind, i.description, i.strength,
         i.verification, i.provenance_class
ORDER BY ce.causal_edge_id, i.evidence_item_id
"""

SELECT_EVIDENCE_RECORDS: Final[str] = """
SELECT evidence_record_id, dataset_version, source_locator, source_timezone
FROM evidence_record
WHERE evidence_record_id = ANY(%s)
ORDER BY evidence_record_id
"""

# ---------------------------------------------------------------------------
# The audit trail
# ---------------------------------------------------------------------------

INSERT_AUDIT_ENTRY: Final[str] = """
INSERT INTO audit_log (run_id, auditable_event, action, target, target_kind, actor,
                       correlation_id, execution_id, before_state, after_state, payload)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

#: Counts used by the projection drift check and the rebuild's verify step. One statement
#: rather than five, so the counts are read at one instant and cannot disagree with each
#: other because a write landed between two of them.
COUNT_FACTS_FOR_DATASET: Final[str] = """
SELECT
  (SELECT count(*) FROM entity WHERE dataset_version = %(dataset_version)s) AS entity_count,
  (SELECT count(*) FROM event  WHERE dataset_version = %(dataset_version)s) AS event_count,
  (SELECT count(*) FROM state
    WHERE dataset_version = %(dataset_version)s
      AND system_to = 'infinity'::timestamptz) AS state_count,
  (SELECT count(*) FROM state_transition
    WHERE dataset_version = %(dataset_version)s
      AND system_to = 'infinity'::timestamptz) AS transition_count,
  (SELECT count(*) FROM relationship
    WHERE dataset_version = %(dataset_version)s
      AND system_to = 'infinity'::timestamptz) AS relationship_count,
  (SELECT count(*) FROM causal_edge WHERE run_id = %(run_id)s) AS causal_edge_count
"""

#: Named so that the absence of a delete path is visible in this file rather than
#: inferable from its absence. There is no DELETE statement in this package: every fact
#: table refuses one at the database (0004), and the projection -- which is rebuildable --
#: is where a run's elements are dropped.
DELETE_NOTHING: Final[str] = ""
