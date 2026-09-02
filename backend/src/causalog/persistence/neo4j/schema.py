"""The Neo4j projection schema: labels, relationship types, constraints, indexes.

Node labels and relationship types are **exactly** prd.md §47. Nothing is added and
nothing is renamed, because §47 is the published graph contract the frontend's traversal
queries are written against.

THE TWO EDGE FAMILIES, and why they must never be confused
----------------------------------------------------------
This is the load-bearing distinction in the whole projection.

  OBSERVED   PRECEDES, BELONGS_TO, LOCATED_AT, TRANSITIONS_TO, PART_OF
             Written from facts. Carry `dataset_version`. Carry NO `run_id`, and an
             existence constraint makes that structural rather than conventional.
             PRECEDES is temporal ORDER and is not a causal claim: adjacency on a timeline
             is sequence, never causation (`GLOSSARY.md` §2.1).

  INFERRED   CAUSES, AFFECTS, BLOCKS, AMPLIFIES, REDUCES, RECOMMENDS
             Written from run-scoped artifacts. Carry `run_id` NOT NULL, enforced by an
             existence constraint, plus the provenance, the confidence rollup with the
             aggregation that produced it, the temporal verdict, and the fired rule ids.

What the separation buys, concretely:

  * `MATCH ()-[r]->() WHERE r.run_id = $run_id DELETE r` removes one run's inferences and
    is INCAPABLE of touching observed structure, because observed edges have no `run_id`
    to match. Dropping a run is therefore routine and safe, which is what ADR-0001
    requires of a derived store.
  * Two runs coexist in one namespace and are diffable: "the new rule pack changed 340
    edges" is a query, not an argument (`docs/architecture.md` §4.4).
  * A traversal that forgot to scope itself reads every run at once and produces a
    visibly wrong answer, rather than a subtly wrong one. That is deliberate: the failure
    is loud.

DERIVED LABELS, stated plainly
-------------------------------
ADR-0001 requires every projected element to trace to a PostgreSQL fact. Three §47 labels
are *functions of* facts rather than rows themselves, and ADR-0034 records the distinction
so nobody later mistakes it for an exception:

  * `Time`   -- deterministic day buckets computed from `event.t_earliest`/`t_latest`.
                A pure function of the event table: same events, same buckets, and the
                buckets participate in the projection content hash like everything else.
                They exist so §53's period filters and the propagation window are index
                lookups rather than range scans.
  * `Location` and `ExternalEvent` -- projections of `Entity` and `Event` rows whose
                ontology-declared type the pack marks as a place or as externally
                originated. The row is the fact; the label is a rendering of it. The label
                is applied in ADDITION to `Entity`/`Event`, never instead, so a traversal
                that does not care about the distinction never has to know it exists.

`Recommendation` and `Intervention` have their constraints created here and no writer yet:
their modules (13, 14) are not built. An empty constrained label is honest -- the shape is
declared, nothing is invented -- and it means the first write lands against a constraint
rather than creating one.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CONSTRAINTS",
    "EXISTENCE_INVARIANTS",
    "INDEXES",
    "INFERRED_RELATIONSHIP_TYPES",
    "NODE_LABELS",
    "OBSERVED_RELATIONSHIP_TYPES",
    "RELATIONSHIP_TYPES",
    "existence_invariant_queries",
    "schema_statements",
]

#: prd.md §47, verbatim. `ExternalEvent` is §47's "External Event" in the PascalCase form
#: Cypher labels take (`CONVENTIONS.md` §5).
NODE_LABELS: Final[tuple[str, ...]] = (
    "Entity",
    "Event",
    "State",
    "Location",
    "Time",
    "ExternalEvent",
    "Recommendation",
    "Intervention",
)

#: Written from facts. No `run_id` -- ever.
OBSERVED_RELATIONSHIP_TYPES: Final[tuple[str, ...]] = (
    "PRECEDES",
    "BELONGS_TO",
    "LOCATED_AT",
    "TRANSITIONS_TO",
    "PART_OF",
)

#: Written from run-scoped artifacts. `run_id` NOT NULL, by existence constraint.
INFERRED_RELATIONSHIP_TYPES: Final[tuple[str, ...]] = (
    "CAUSES",
    "AFFECTS",
    "BLOCKS",
    "AMPLIFIES",
    "REDUCES",
    "RECOMMENDS",
)

#: The union, which is prd.md §47's list exactly.
RELATIONSHIP_TYPES: Final[tuple[str, ...]] = (
    OBSERVED_RELATIONSHIP_TYPES + INFERRED_RELATIONSHIP_TYPES
)

#: Node keys. Every one pairs the artifact's PostgreSQL content address with the build
#: namespace, so a projected node cannot exist under an identifier the system of record
#: does not hold, a duplicate projection write conflicts instead of creating a second node,
#: and a STAGED build is a disjoint subgraph beside the live one rather than an in-place
#: mutation of it (`docs/architecture.md` §3.3 step 2, ADR-0034).
#:
#: The address alone would have been the obvious key and is the wrong one: `MERGE` on it
#: would match the live node and overwrite its properties, which is precisely the in-place
#: mutation that makes a failed rebuild take the previous projection down with it.
UNIQUENESS_CONSTRAINTS: Final[tuple[str, ...]] = (
    "CREATE CONSTRAINT entity_key IF NOT EXISTS "
    "FOR (n:Entity) REQUIRE (n.entity_id, n.namespace) IS UNIQUE",
    "CREATE CONSTRAINT event_key IF NOT EXISTS "
    "FOR (n:Event) REQUIRE (n.event_id, n.namespace) IS UNIQUE",
    "CREATE CONSTRAINT state_key IF NOT EXISTS "
    "FOR (n:State) REQUIRE (n.state_id, n.namespace) IS UNIQUE",
    "CREATE CONSTRAINT time_key IF NOT EXISTS "
    "FOR (n:Time) REQUIRE (n.bucket_start, n.namespace) IS UNIQUE",
    "CREATE CONSTRAINT recommendation_key IF NOT EXISTS "
    "FOR (n:Recommendation) REQUIRE (n.recommendation_id, n.namespace) IS UNIQUE",
    "CREATE CONSTRAINT intervention_key IF NOT EXISTS "
    "FOR (n:Intervention) REQUIRE (n.intervention_id, n.namespace) IS UNIQUE",
)

#: Node existence constraints. **ENTERPRISE EDITION ONLY** -- see DEF-0004 below.
#: `Location` and `ExternalEvent` are ADDITIONAL labels on an Entity/Event node, so their
#: identity is that node's and they get no key of their own.
NODE_EXISTENCE_CONSTRAINTS: Final[tuple[str, ...]] = (
    "CREATE CONSTRAINT event_type_exists IF NOT EXISTS "
    "FOR (n:Event) REQUIRE n.event_type IS NOT NULL",
    "CREATE CONSTRAINT event_provenance_exists IF NOT EXISTS "
    "FOR (n:Event) REQUIRE n.provenance_class IS NOT NULL",
    "CREATE CONSTRAINT recommendation_run_exists IF NOT EXISTS "
    "FOR (n:Recommendation) REQUIRE n.run_id IS NOT NULL",
    "CREATE CONSTRAINT intervention_run_exists IF NOT EXISTS "
    "FOR (n:Intervention) REQUIRE n.run_id IS NOT NULL",
)


def _inferred_edge_constraints() -> tuple[str, ...]:
    """Require `run_id` on every inferred relationship type.

    Generated from `INFERRED_RELATIONSHIP_TYPES` rather than written out, so adding a kind
    to that tuple cannot leave it unconstrained. A `CAUSES` edge with no run would be an
    inference with nothing to scope it -- the one thing ADR-0013 makes structurally
    impossible in PostgreSQL, and it must be equally impossible here or the projection
    becomes the way around it.
    """
    statements = []
    for relationship_type in INFERRED_RELATIONSHIP_TYPES:
        lowered = relationship_type.lower()
        statements.append(
            f"CREATE CONSTRAINT {lowered}_run_exists IF NOT EXISTS "
            f"FOR ()-[r:{relationship_type}]-() REQUIRE r.run_id IS NOT NULL"
        )
        statements.append(
            f"CREATE CONSTRAINT {lowered}_provenance_exists IF NOT EXISTS "
            f"FOR ()-[r:{relationship_type}]-() REQUIRE r.provenance_class IS NOT NULL"
        )
    return tuple(statements)


def _observed_edge_constraints() -> tuple[str, ...]:
    """Require `dataset_version` on every observed relationship type.

    The mirror of the inferred constraint, and it earns its place for the same reason: an
    observed edge with no dataset version could not be traced back to the facts it was
    projected from, which is exactly the "write with no backing PostgreSQL fact" ADR-0001
    calls a defect.
    """
    return tuple(
        f"CREATE CONSTRAINT {relationship_type.lower()}_dataset_exists IF NOT EXISTS "
        f"FOR ()-[r:{relationship_type}]-() REQUIRE r.dataset_version IS NOT NULL"
        for relationship_type in OBSERVED_RELATIONSHIP_TYPES
    )


#: Each index names the query that justifies it, in the comment beside it. An index with
#: no query above it does not belong in a store that is dropped and rebuilt routinely --
#: every index is paid for again on every rebuild, and the rebuild sits on the prd.md §55
#: sixty-second graph-generation budget.
INDEXES: Final[tuple[str, ...]] = (
    # Justifying query: GET /events and the period filters of prd.md §51, which select
    # events within a window before traversing.
    "CREATE INDEX event_t_earliest IF NOT EXISTS FOR (n:Event) ON (n.t_earliest)",
    # Justifying query: module 9 selects candidate pairs by the event types a rule
    # declares; without this the rule sweep scans every Event node.
    "CREATE INDEX event_type IF NOT EXISTS FOR (n:Event) ON (n.event_type)",
    # Justifying query: the entity workspace lists participants of one ontology-declared
    # type. The type is a PROPERTY and never a second label, so LAW-DOMAIN vocabulary
    # never enters the schema itself.
    "CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)",
    # Justifying query: the as-of read, which locates the states holding at an instant.
    "CREATE INDEX state_entity IF NOT EXISTS FOR (n:State) ON (n.entity_id)",
    # Justifying query: the Time bucket lookup that period filters resolve through.
    "CREATE INDEX time_bucket IF NOT EXISTS FOR (n:Time) ON (n.bucket_start)",
    # Justifying queries: EVERY read and EVERY write filters on the namespace, because
    # a staged build and the live build share one database (Community Edition). Without
    # this index the verification pass and the superseded-build drop each scan both.
    "CREATE INDEX event_namespace IF NOT EXISTS FOR (n:Event) ON (n.namespace)",
    "CREATE INDEX entity_namespace IF NOT EXISTS FOR (n:Entity) ON (n.namespace)",
    "CREATE INDEX state_namespace IF NOT EXISTS FOR (n:State) ON (n.namespace)",
)


def _inferred_edge_indexes() -> tuple[str, ...]:
    """Index `run_id` on every inferred relationship type.

    Justifying queries: every root-cause and propagation traversal is run-scoped, and so
    is `drop_run`. Without this index, isolating one run means scanning every inferred
    edge of every run, and the cost grows with the number of runs anyone has ever
    executed -- which is the number that grows fastest in a system built to re-run.
    """
    return tuple(
        f"CREATE INDEX {relationship_type.lower()}_run IF NOT EXISTS "
        f"FOR ()-[r:{relationship_type}]-() ON (r.run_id)"
        for relationship_type in INFERRED_RELATIONSHIP_TYPES
    )


#: Backwards-compatible union. Kept because callers and tests refer to it by name; the
#: edition split is expressed by `schema_statements(existence_constraints=...)`.
CONSTRAINTS: Final[tuple[str, ...]] = UNIQUENESS_CONSTRAINTS + NODE_EXISTENCE_CONSTRAINTS


def existence_constraint_statements() -> tuple[str, ...]:
    """Return every ENTERPRISE-ONLY statement, node and relationship alike.

    DEF-0004. Property existence constraints (`REQUIRE ... IS NOT NULL`) are a Neo4j
    Enterprise feature. `deployment/docker-compose.yml` pins `neo4j:5.26.0-community`, so
    on the stack this repository actually ships, every one of these fails with
    `Neo.DatabaseError.Schema.ConstraintCreationFailed`. Before the split, `_apply_schema`
    ran them unconditionally and the FIRST live rebuild aborted on step 2 -- the schema had
    never been applied to a real Neo4j, only asserted about in unit tests over this module,
    which is why a whole feature-gated family of statements read as working code.

    They are kept, not deleted, because on Enterprise they are the right enforcement and
    the projection should use the database when the database can do the job. On Community
    the same invariants are checked by `existence_invariant_queries()` after the projection
    is written and before it is allowed to go live. That is genuinely weaker -- a check
    after the fact rather than a constraint that makes the state unrepresentable -- and the
    difference is reported rather than smoothed over: `ProjectionReport.enforcement`
    records which of the two was in force for the build.
    """
    return NODE_EXISTENCE_CONSTRAINTS + _observed_edge_constraints() + _inferred_edge_constraints()


def existence_invariant_queries() -> tuple[tuple[str, str], ...]:
    """Return `(description, cypher)` pairs that find violations of the existence rules.

    The compensating check for Community Edition. Each query returns a COUNT of offending
    elements in one namespace; any non-zero count aborts the rebuild before the swap, so a
    projection that breaks an invariant never serves a reader -- which is the property the
    constraint was there to guarantee.

    Derived from the same tuples the constraints are derived from, so a relationship type
    added to `INFERRED_RELATIONSHIP_TYPES` gets a constraint on Enterprise AND a check on
    Community, and cannot be enforced in one place while being forgotten in the other.
    """
    checks: list[tuple[str, str]] = [
        (
            "Event nodes with no event_type",
            "MATCH (n:Event {namespace: $namespace}) WHERE n.event_type IS NULL "
            "RETURN count(n) AS violations",
        ),
        (
            "Event nodes with no provenance_class",
            "MATCH (n:Event {namespace: $namespace}) WHERE n.provenance_class IS NULL "
            "RETURN count(n) AS violations",
        ),
        (
            "Recommendation nodes with no run_id",
            "MATCH (n:Recommendation {namespace: $namespace}) WHERE n.run_id IS NULL "
            "RETURN count(n) AS violations",
        ),
        (
            "Intervention nodes with no run_id",
            "MATCH (n:Intervention {namespace: $namespace}) WHERE n.run_id IS NULL "
            "RETURN count(n) AS violations",
        ),
    ]
    for relationship_type in INFERRED_RELATIONSHIP_TYPES:
        checks.append(
            (
                f"{relationship_type} edges with no run_id",
                f"MATCH ()-[r:{relationship_type} {{namespace: $namespace}}]->() "
                "WHERE r.run_id IS NULL RETURN count(r) AS violations",
            )
        )
        checks.append(
            (
                f"{relationship_type} edges with no provenance_class",
                f"MATCH ()-[r:{relationship_type} {{namespace: $namespace}}]->() "
                "WHERE r.provenance_class IS NULL RETURN count(r) AS violations",
            )
        )
    for relationship_type in OBSERVED_RELATIONSHIP_TYPES:
        checks.append(
            (
                f"{relationship_type} edges with no dataset_version",
                f"MATCH ()-[r:{relationship_type} {{namespace: $namespace}}]->() "
                "WHERE r.dataset_version IS NULL RETURN count(r) AS violations",
            )
        )
        # The other half of the OBSERVED/INFERRED separation, and the one the constraints
        # never covered on ANY edition: an observed edge must carry no run_id. Without it,
        # `drop_run` could delete observed structure -- the exact guarantee the module
        # docstring above claims is structural.
        checks.append(
            (
                f"{relationship_type} edges carrying a run_id",
                f"MATCH ()-[r:{relationship_type} {{namespace: $namespace}}]->() "
                "WHERE r.run_id IS NOT NULL RETURN count(r) AS violations",
            )
        )
    return tuple(checks)


#: Exposed for the tests, which assert the two enforcement paths cover the same ground.
EXISTENCE_INVARIANTS: Final[tuple[tuple[str, str], ...]] = existence_invariant_queries()


def schema_statements(*, existence_constraints: bool = True) -> tuple[str, ...]:
    """Return every constraint and index statement, in a stable order.

    Idempotent: every statement carries `IF NOT EXISTS`, so applying the schema to a store
    that already has it is a no-op. That is a requirement rather than a convenience --
    `rebuild_from_facts` applies the schema on every run, and a rebuild that failed
    because the schema already existed would make the routine operation the fragile one.

    `existence_constraints=False` omits the Enterprise-only family (DEF-0004). The caller
    decides, rather than this module guessing, because the decision needs the live server's
    edition and this module does not hold a driver.
    """
    statements = UNIQUENESS_CONSTRAINTS
    if existence_constraints:
        statements = statements + existence_constraint_statements()
    return statements + INDEXES + _inferred_edge_indexes()
