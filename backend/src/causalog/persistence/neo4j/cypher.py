"""Every Cypher statement the projection issues, as named constants.

Explicit Cypher for all graph work -- the brief's constraint and the right one. A query
builder would hide the traversal shape, and the traversal shape *is* the thing under the
prd.md §55 targets: whether a root-cause query is an index seek plus a bounded expansion
or an unbounded scan is not a detail to delegate.

Every statement is parameterized. Interpolating an identifier into Cypher would make the
statement text depend on the data, which breaks the driver's plan cache and, more
seriously, makes an injected identifier possible in a store that is dropped and rebuilt by
an automated command. The one substitution that is not a parameter is a relationship
TYPE -- Cypher cannot parameterize one -- and it is always taken from the closed tuple of
constants in `schema.INFERRED_RELATIONSHIP_TYPES`, never from a row value. That is the
difference between a template and an injection.

Writes are `UNWIND $rows AS row` plus `MERGE`, not one statement per element. `UNWIND`
sends a batch as one message; per-element statements would put a round trip on each of the
~180 000 events, and the rebuild sits on the prd.md §55 sixty-second graph-generation
budget. `MERGE` rather than `CREATE`, so a rebuild is idempotent by construction: the
projection is a function of the facts, and running the function twice must produce one
graph rather than two overlaid.

EVERY PATTERN IS KEYED ON `namespace` AS WELL AS ON THE CONTENT ADDRESS. That is what
makes staging real. `docs/architecture.md` §3.3 step 2 requires that the live namespace is
never mutated in place, so a failed rebuild leaves the previous projection serving. Neo4j
Community Edition serves one database, so a namespace here is a property rather than a
separate store -- and a `MERGE` keyed on the content address ALONE would have matched the
live node and mutated it, which is exactly the in-place mutation step 2 forbids. Keyed on
both, a staged build is a disjoint subgraph beside the live one, verification reads only
the staged namespace, and the swap is a registry update in PostgreSQL.

The cost is stated rather than hidden: during a rebuild the store holds two copies of the
graph. The superseded copy is removed after the swap succeeds, and a rebuild that failed
leaves its staged copy until the next one drops it.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "COUNT_ELEMENTS",
    "CREATE_TIME_BUCKETS",
    "DROP_NAMESPACE_NODES",
    "DROP_NAMESPACE_RELATIONSHIPS",
    "DROP_RUN_INFERENCES",
    "LABEL_EXTERNAL_EVENTS",
    "LABEL_LOCATIONS",
    "MERGE_BELONGS_TO",
    "MERGE_CAUSAL_EDGES",
    "MERGE_ENTITIES",
    "MERGE_EVENTS",
    "MERGE_LOCATED_AT",
    "MERGE_PART_OF",
    "MERGE_PRECEDES",
    "MERGE_STATES",
    "MERGE_TRANSITIONS_TO",
    "PROJECTION_FINGERPRINT",
]

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

#: `entity_type` is a PROPERTY, never a second label. A label per ontology type would put
#: domain vocabulary into the graph schema itself, where every traversal would then have to
#: name it -- LAW-DOMAIN defeated by the store rather than by the code.
#:
#: `Location` is applied as an ADDITIONAL label by `LABEL_LOCATIONS`, so a traversal that
#: does not care never has to know the distinction exists (ADR-0034). A second statement
#: over the subset rather than a conditional `SET` here, because Cypher has no conditional
#: label without APOC and this project takes no database-plugin dependency: ADR-0015
#: governs every dependency, and a server plugin is one.
MERGE_ENTITIES: Final[str] = """
UNWIND $rows AS row
MERGE (n:Entity {entity_id: row.entity_id, namespace: $namespace})
SET n.entity_type = row.entity_type,
    n.natural_key = row.natural_key,
    n.provenance_class = row.provenance_class,
    n.dataset_version = row.dataset_version
RETURN count(n) AS written
"""

LABEL_LOCATIONS: Final[str] = """
UNWIND $entity_ids AS entity_id
MATCH (n:Entity {entity_id: entity_id, namespace: $namespace})
SET n:Location
RETURN count(n) AS written
"""

MERGE_EVENTS: Final[str] = """
UNWIND $rows AS row
MERGE (n:Event {event_id: row.event_id, namespace: $namespace})
SET n.event_type = row.event_type,
    n.t_earliest = datetime(row.t_earliest),
    n.t_latest = datetime(row.t_latest),
    n.time_precision = row.time_precision,
    n.time_provenance = row.time_provenance,
    n.provenance_class = row.provenance_class,
    n.is_actionable = row.is_actionable,
    n.confidence_scalar = row.confidence_scalar,
    n.confidence_aggregation = row.confidence_aggregation,
    n.source_record_ref = row.source_record_ref,
    n.dataset_version = row.dataset_version
RETURN count(n) AS written
"""

LABEL_EXTERNAL_EVENTS: Final[str] = """
UNWIND $event_ids AS event_id
MATCH (n:Event {event_id: event_id, namespace: $namespace})
SET n:ExternalEvent
RETURN count(n) AS written
"""

MERGE_STATES: Final[str] = """
UNWIND $rows AS row
MERGE (n:State {state_id: row.state_id, namespace: $namespace})
SET n.entity_id = row.entity_id,
    n.state_name = row.state_name,
    n.valid_from = datetime(row.valid_from),
    n.valid_to = datetime(row.valid_to),
    n.valid_precision = row.valid_precision,
    n.provenance_class = row.provenance_class,
    n.dataset_version = row.dataset_version
RETURN count(n) AS written
"""

#: Day buckets, computed in Python from the event bounds and passed in. Deliberately NOT
#: computed in Cypher: a bucket derived inside the projection would be a value the system
#: of record cannot reproduce, and step 4 of the rebuild compares the projection against
#: values computed from the facts.
CREATE_TIME_BUCKETS: Final[str] = """
UNWIND $rows AS row
MERGE (t:Time {bucket_start: date(row.bucket_start), namespace: $namespace})
SET t.granularity = row.granularity,
    t.dataset_version = row.dataset_version
WITH t, row
UNWIND row.event_ids AS event_id
MATCH (e:Event {event_id: event_id, namespace: $namespace})
MERGE (e)-[r:PART_OF]->(t)
SET r.dataset_version = row.dataset_version,
    r.namespace = $namespace
RETURN count(r) AS written
"""

# ---------------------------------------------------------------------------
# Observed edges. `dataset_version`, never `run_id`.
# ---------------------------------------------------------------------------

#: PRECEDES is temporal ORDER, not causation. It exists because one event sequenced before
#: another for the same participant, and `GLOSSARY.md` §2.1 is explicit that adjacency on
#: a timeline is sequence and never a causal claim. Module 8 writes this family; only
#: module 10 writes CAUSES; the two never meet in one statement in this file.
MERGE_PRECEDES: Final[str] = """
UNWIND $rows AS row
MATCH (a:Event {event_id: row.source_event_id, namespace: $namespace})
MATCH (b:Event {event_id: row.target_event_id, namespace: $namespace})
MERGE (a)-[r:PRECEDES {entity_id: row.entity_id}]->(b)
SET r.dataset_version = row.dataset_version,
    r.namespace = $namespace
RETURN count(r) AS written
"""

MERGE_BELONGS_TO: Final[str] = """
UNWIND $rows AS row
MATCH (a:Entity {entity_id: row.source_entity_id, namespace: $namespace})
MATCH (b:Entity {entity_id: row.target_entity_id, namespace: $namespace})
MERGE (a)-[r:BELONGS_TO {relationship_id: row.relationship_id}]->(b)
SET r.dataset_version = row.dataset_version,
    r.namespace = $namespace,
    r.valid_from = datetime(row.valid_from),
    r.valid_to = datetime(row.valid_to),
    r.provenance_class = row.provenance_class
RETURN count(r) AS written
"""

MERGE_LOCATED_AT: Final[str] = """
UNWIND $rows AS row
MATCH (a:Entity {entity_id: row.source_entity_id, namespace: $namespace})
MATCH (b:Entity {entity_id: row.target_entity_id, namespace: $namespace})
MERGE (a)-[r:LOCATED_AT {relationship_id: row.relationship_id}]->(b)
SET r.dataset_version = row.dataset_version,
    r.namespace = $namespace,
    r.valid_from = datetime(row.valid_from),
    r.valid_to = datetime(row.valid_to),
    r.provenance_class = row.provenance_class
RETURN count(r) AS written
"""

MERGE_PART_OF: Final[str] = """
UNWIND $rows AS row
MATCH (a:Entity {entity_id: row.source_entity_id, namespace: $namespace})
MATCH (b:Entity {entity_id: row.target_entity_id, namespace: $namespace})
MERGE (a)-[r:PART_OF {relationship_id: row.relationship_id}]->(b)
SET r.dataset_version = row.dataset_version,
    r.namespace = $namespace,
    r.valid_from = datetime(row.valid_from),
    r.valid_to = datetime(row.valid_to),
    r.provenance_class = row.provenance_class
RETURN count(r) AS written
"""

#: A transition connects the two State nodes it moved between and names the event that
#: occasioned it. "Causing" here is the OBSERVED attribution recorded at state-derivation
#: time; it is not an inferred causal edge, which is why it sits in this family and carries
#: no run (docs/contracts.md §5).
MERGE_TRANSITIONS_TO: Final[str] = """
UNWIND $rows AS row
MATCH (a:State {state_id: row.from_state_id, namespace: $namespace})
MATCH (b:State {state_id: row.to_state_id, namespace: $namespace})
MERGE (a)-[r:TRANSITIONS_TO {transition_id: row.transition_id}]->(b)
SET r.dataset_version = row.dataset_version,
    r.namespace = $namespace,
    r.causing_event_id = row.causing_event_id,
    r.provenance_class = row.provenance_class
RETURN count(r) AS written
"""

# ---------------------------------------------------------------------------
# Inferred edges. `run_id` NOT NULL, always.
# ---------------------------------------------------------------------------

#: `{relationship_type}` is substituted from `schema.INFERRED_RELATIONSHIP_TYPES` -- a
#: closed tuple of module constants -- and never from a row value. Cypher cannot
#: parameterize a relationship type; taking it from data would be an injection, taking it
#: from a constant is a template.
MERGE_CAUSAL_EDGES: Final[str] = """
UNWIND $rows AS row
MATCH (a:Event {{event_id: row.source_event_id, namespace: $namespace}})
MATCH (b:Event {{event_id: row.target_event_id, namespace: $namespace}})
MERGE (a)-[r:{relationship_type} {{causal_edge_id: row.causal_edge_id}}]->(b)
SET r.run_id = row.run_id,
    r.namespace = $namespace,
    r.edge_kind = row.edge_kind,
    r.provenance_class = row.provenance_class,
    r.confidence_scalar = row.confidence_scalar,
    r.confidence_aggregation = row.confidence_aggregation,
    r.propagation_weight = row.propagation_weight,
    r.temporal_verdict = row.temporal_verdict,
    r.temporally_unverifiable = row.temporally_unverifiable,
    r.evidence_item_ids = row.evidence_item_ids,
    r.rule_ids = row.rule_ids
RETURN count(r) AS written
"""

#: Removes one run's inferences and NOTHING else. Observed edges carry no `run_id`, so
#: they cannot match this pattern -- the isolation is structural, not a filter somebody
#: remembered to write. The corresponding PostgreSQL rows are the record and are never
#: deleted; this is the derived store, and dropping from it is routine (ADR-0001).
DROP_RUN_INFERENCES: Final[str] = """
MATCH ()-[r]->()
WHERE r.run_id = $run_id
WITH r LIMIT $batch_size
DELETE r
RETURN count(r) AS removed
"""

#: Removes a superseded build. Relationships first, then nodes: Neo4j refuses to delete a
#: node that still has relationships, and `DETACH DELETE` would reach across into another
#: namespace's edges if one ever pointed here. Two explicit statements say what is removed.
DROP_NAMESPACE_RELATIONSHIPS: Final[str] = """
MATCH ()-[r {namespace: $namespace}]->()
WITH r LIMIT $batch_size
DELETE r
RETURN count(r) AS removed
"""

DROP_NAMESPACE_NODES: Final[str] = """
MATCH (n {namespace: $namespace})
WITH n LIMIT $batch_size
DELETE n
RETURN count(n) AS removed
"""

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

#: Per-label and per-type counts within one namespace, for the rebuild's verify step and
#: for the drift check. `Location` and `ExternalEvent` are additional labels, so their
#: totals are SUBSETS of `Entity` and `Event` rather than additions to them -- a reader
#: summing every label to get a node count would double-count, and the drift check does
#: not.
COUNT_ELEMENTS: Final[str] = """
CALL () {
  MATCH (n {namespace: $namespace})
  UNWIND labels(n) AS label
  RETURN label AS name, count(*) AS total
  UNION ALL
  MATCH ()-[r {namespace: $namespace}]->()
  RETURN type(r) AS name, count(*) AS total
}
RETURN name, sum(total) AS total ORDER BY name
"""

#: The token stream the projection content hash is computed over. Deterministic by
#: construction: every element contributes its content address and its family, the caller
#: sorts, and nothing contributes a timestamp, an internal id, or a traversal order. Two
#: rebuilds of one run must produce one hash, or the projection is not a function of the
#: facts (docs/architecture.md §3.3 step 6).
#:
#: The namespace itself is deliberately NOT in a token. It changes on every rebuild by
#: design, so including it would make the step-6 comparison always fail and the
#: determinism assertion worthless.
PROJECTION_FINGERPRINT: Final[str] = """
CALL () {
  MATCH (n:Event {namespace: $namespace}) RETURN 'evt|' + n.event_id AS token
  UNION ALL
  MATCH (n:Entity {namespace: $namespace}) RETURN 'ent|' + n.entity_id AS token
  UNION ALL
  MATCH (n:State {namespace: $namespace}) RETURN 'sta|' + n.state_id AS token
  UNION ALL
  MATCH (n:Time {namespace: $namespace}) RETURN 'tim|' + toString(n.bucket_start) AS token
  UNION ALL
  MATCH (n:Location {namespace: $namespace}) RETURN 'loc|' + n.entity_id AS token
  UNION ALL
  MATCH (a)-[r {namespace: $namespace}]->(b)
  WHERE r.run_id IS NULL
  RETURN 'obs|' + type(r) + '|'
         + coalesce(a.event_id, a.entity_id, a.state_id, '') + '|'
         + coalesce(b.event_id, b.entity_id, b.state_id, toString(b.bucket_start), '')
         AS token
  UNION ALL
  MATCH ()-[r {namespace: $namespace}]->()
  WHERE r.run_id = $run_id
  RETURN 'inf|' + type(r) + '|' + r.causal_edge_id AS token
}
RETURN token
"""
