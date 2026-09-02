"""The derived graph projection (`GraphProjection`), and the rebuild ADR-0001 requires.

PostgreSQL is the system of record. This store holds nothing that is not a function of
those facts, and dropping and rebuilding the whole projection must always be safe. That
is not an aspiration here: `rebuild_from_facts` is the only write path, it always stages
into a fresh namespace, it always verifies before it swaps, and it always compares the
result against the previous build for the same run.

THE SIX STEPS (`docs/architecture.md` §3.3), each with what it defends against:

  1. RESOLVE  the run to its five-tuple. A rebuild for a run nobody registered would
              produce a graph nothing can reproduce.
  2. STAGE    into a NEW versioned namespace. The live namespace is never mutated in
              place, so a rebuild that fails at step 4 leaves the previous projection
              serving rather than leaving a half-graph in front of users.
  3. STREAM   the facts in canonical sequence, every read carrying an explicit ORDER BY
              on a unique key (`CONVENTIONS.md` §11). An unsequenced stream produces a
              graph whose content hash differs between two runs over identical facts,
              which reads exactly like a determinism defect and is not one.
  4. VERIFY   counts and content hash against the values computed from PostgreSQL. A
              mismatch aborts BEFORE any swap: this is the step that catches "a node with
              no backing fact", which ADR-0001 calls a defect.
  5. SWAP     the alias, in one transaction against the registry. The partial unique index
              on `graph_projection` makes two live projections for one run
              unrepresentable, so the swap is atomic by construction rather than by lock.
  6. ASSERT   the rebuilt hash equals the prior build's for the same run. A mismatch is a
              DETERMINISM DEFECT, not a retryable error -- it means something in the
              pipeline is not a function of its inputs, and retrying would hide it.

NAMESPACES, and the honest limitation. Neo4j Community Edition serves one database, so a
"namespace" here is a property stamped on every element of a build rather than a separate
database. The staging build writes elements tagged with the new namespace, verification
reads only that namespace, and the swap flips which namespace the registry calls live.
The previous build's elements stay until the swap succeeds and are removed after. That is
weaker than Enterprise's database-per-build in exactly one way -- a failed rebuild leaves
its staged elements behind until the next run drops them, so the store is briefly larger
than it needs to be. It is not weaker in the way that matters: readers resolve the live
namespace from PostgreSQL, so they never see a staged build.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from typing import Any, Final

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import Neo4jError

from causalog.core.errors import ContractViolationError, ProjectionStaleError
from causalog.core.identifiers import DIGEST_LENGTH
from causalog.persistence.neo4j import cypher, schema
from causalog.persistence.postgres.connection import PostgresConnectionFactory
from causalog.persistence.postgres.fact_repository import PostgresFactRepository

__all__ = ["Neo4jProjection", "ProjectionReport", "projection_version_for"]

#: Elements sent per `UNWIND`. Large enough that the round trip is amortised, small enough
#: that one message stays inside the driver's default limits on a 1 GB container.
WRITE_BATCH_SIZE: Final[int] = 5_000

#: Relationships deleted per `drop_run` batch. Bounded so a large run's removal does not
#: build one transaction big enough to exhaust the 512 MB heap the compose file pins.
DELETE_BATCH_SIZE: Final[int] = 10_000

#: The version prefix, in the same shape as every other identifier (`CONVENTIONS.md` §9).
PROJECTION_VERSION_PREFIX: Final[str] = "gpv"


def projection_version_for(run_id: str, content_hash: str) -> str:
    """Return `gpv:<sha256(run_id|content_hash)[:16]>`.

    Derived from both, deliberately. From the run alone, two builds of one run would share
    a version and staleness would be undetectable; from the hash alone, two runs that
    happened to project identically would share one, and a reader could not tell which run
    it was looking at.
    """
    payload = f"{run_id}|{content_hash}".encode()
    return f"{PROJECTION_VERSION_PREFIX}:{hashlib.sha256(payload).hexdigest()[:DIGEST_LENGTH]}"


@dataclass(frozen=True)
class ProjectionReport:
    """The outcome of one rebuild, as the command prints it and the registry stores it."""

    run_id: str
    namespace: str
    graph_projection_version: str
    content_hash: str
    node_count: int
    edge_count: int
    matched_previous_build: bool | None
    #: Which of the two enforcement paths was in force for this build (DEF-0004):
    #: "constraints" when the server is Enterprise and the database itself makes an
    #: existence violation unrepresentable, "post-write checks" when it is Community and
    #: the invariants were verified after the write instead. Recorded rather than assumed,
    #: because the two are NOT equally strong and a reader of a report is entitled to know
    #: which one produced it.
    enforcement: str = "constraints"


class Neo4jProjection:
    """The `GraphProjection` adapter. Reads facts through the repository, never directly."""

    def __init__(
        self,
        driver: Driver,
        repository: PostgresFactRepository,
        connection_factory: PostgresConnectionFactory,
    ) -> None:
        """Bind the projection to a graph driver and to the system of record.

        The repository is passed in rather than constructed, so the projection cannot
        acquire its own connection to PostgreSQL and cannot read anything the repository
        does not expose -- which is what keeps "every projected element traces to a fact"
        checkable rather than hopeful.
        """
        self._driver = driver
        self._repository = repository
        self._factory = connection_factory

    @classmethod
    def from_environment(
        cls,
        repository: PostgresFactRepository,
        connection_factory: PostgresConnectionFactory,
    ) -> Neo4jProjection:
        """Build a projection from `CAUSALOG_NEO4J_URI` and `CAUSALOG_NEO4J_AUTH`."""
        import os

        uri = os.environ.get("CAUSALOG_NEO4J_URI")
        auth = os.environ.get("CAUSALOG_NEO4J_AUTH", "")
        if not uri:
            raise ContractViolationError(
                "No Neo4j URI: set CAUSALOG_NEO4J_URI. The projection is derived and "
                "rebuildable, but it is not optional -- a missing URI must fail loudly "
                "rather than silently degrade a graph query to nothing."
            )
        user, _, password = auth.partition("/")
        return cls(GraphDatabase.driver(uri, auth=(user, password)), repository, connection_factory)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def projection_version(self, run_id: str) -> str | None:
        """Return the version currently served for a run, or None.

        Read from PostgreSQL, not from Neo4j. The derived store has no authority
        (ADR-0001), so asking it which version it is serving would be asking the
        unreliable party to certify itself.
        """
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT graph_projection_version FROM graph_projection "
                "WHERE run_id = %s AND status = 'live'",
                (run_id,),
            )
            record = cursor.fetchone()
        return None if record is None else str(record[0])

    def require_version(self, run_id: str, expected_version: str) -> None:
        """Raise `ProjectionStaleError` unless the live version is the one expected.

        A reader that asks for a version the store is not serving never silently receives
        an older graph (`docs/architecture.md` §3.2). The message names both versions,
        because "stale" without the two numbers is a fact nobody can act on.
        """
        live = self.projection_version(run_id)
        if live != expected_version:
            raise ProjectionStaleError(
                f"Projection for run {run_id} is at {live!r}; {expected_version!r} was "
                "requested. A stale projection is never served as if fresh; rebuild with "
                f"`make rebuild-graph RUN_ID={run_id}`."
            )

    def content_hash(self, run_id: str, namespace: str | None = None) -> str:
        """Return a canonical hash of the projected content for a run.

        Computed over a sorted token stream, so it depends on the CONTENT and not on
        traversal order, insertion order, internal identifiers, or wall-clock. Anything
        else would make two rebuilds of one run disagree and turn the determinism
        assertion at step 6 into a coin flip.
        """
        resolved = namespace if namespace is not None else self._live_namespace(run_id)
        with self._driver.session() as session:
            tokens = [
                record["token"]
                for record in session.run(
                    cypher.PROJECTION_FINGERPRINT, run_id=run_id, namespace=resolved
                )
            ]
        digest = hashlib.sha256("\n".join(sorted(tokens)).encode()).hexdigest()
        return digest[:DIGEST_LENGTH]

    def element_counts(self, run_id: str, namespace: str | None = None) -> dict[str, int]:
        """Return per-label and per-relationship-type counts for the drift check."""
        resolved = namespace if namespace is not None else self._live_namespace(run_id)
        with self._driver.session() as session:
            return {
                record["name"]: record["total"]
                for record in session.run(cypher.COUNT_ELEMENTS, namespace=resolved)
            }

    # ------------------------------------------------------------------
    # The rebuild
    # ------------------------------------------------------------------

    def rebuild_from_facts(self, run_id: str) -> str:
        """Rebuild the projection for a run and return the resulting version."""
        return self.rebuild(run_id).graph_projection_version

    def rebuild(self, run_id: str, *, verify_only: bool = False) -> ProjectionReport:
        """Run the six-step rebuild and return its report."""
        # 1. RESOLVE.
        run = self._repository.run(run_id)
        if run is None:
            raise ContractViolationError(
                f"No run registered as {run_id!r}. A projection built for an unregistered "
                "run could not be reproduced from its inputs, which is the one thing a "
                "derived store must always be able to do (ADR-0013)."
            )
        dataset_version = run.key.dataset_version

        # 2. STAGE.
        namespace = self._next_namespace(run_id)
        enterprise = self._supports_existence_constraints()
        self._apply_schema(existence_constraints=enterprise)
        previous_hash = self._previous_content_hash(run_id)

        # 3. STREAM, in canonical sequence.
        node_count = 0
        edge_count = 0
        node_count += self._project_entities(dataset_version, namespace)
        node_count += self._project_events(dataset_version, namespace)
        node_count += self._project_states(dataset_version, namespace)
        node_count += self._project_time_buckets(dataset_version, namespace)
        edge_count += self._project_precedes(dataset_version, namespace)
        edge_count += self._project_relationships(dataset_version, namespace)
        edge_count += self._project_transitions(dataset_version, namespace)
        edge_count += self._project_causal_edges(run_id, namespace)

        # 4. VERIFY, before any swap.
        content_hash = self.content_hash(run_id, namespace)
        self._verify_against_facts(run_id, dataset_version, namespace)
        if not enterprise:
            self._verify_existence_invariants(namespace)

        version = projection_version_for(run_id, content_hash)

        # 6. ASSERT (evaluated before the swap so a determinism defect never goes live).
        matched_previous = None if previous_hash is None else previous_hash == content_hash
        if matched_previous is False:
            raise ContractViolationError(
                f"Rebuilding run {run_id} produced content hash {content_hash!r}; the "
                f"previous build of the SAME run produced {previous_hash!r}. Identical "
                "inputs must produce identical artifacts, so this is a determinism defect "
                "and not a retryable error: something in the pipeline is not a function of "
                "its inputs (CONVENTIONS.md §11). The staged namespace is left in place "
                "for inspection and the live projection is untouched."
            )

        # 5. SWAP, then remove the build it superseded. The drop happens AFTER the
        # registry update, so a crash between them leaves a store that is larger than it
        # needs to be -- never one whose live namespace has been partly deleted.
        if not verify_only:
            superseded = self._live_namespace_or_none(run_id)
            self._swap(run_id, namespace, version, content_hash, node_count, edge_count)
            if superseded is not None and superseded != namespace:
                self._drop_namespace(superseded)

        return ProjectionReport(
            run_id=run_id,
            namespace=namespace,
            graph_projection_version=version,
            content_hash=content_hash,
            node_count=node_count,
            edge_count=edge_count,
            matched_previous_build=matched_previous,
            enforcement="constraints" if enterprise else "post-write checks",
        )

    def drop_run(self, run_id: str) -> int:
        """Remove one run's inferred elements and return how many were removed.

        Observed structure is untouched, and not because this method is careful: observed
        edges carry no `run_id`, so they cannot match the pattern. Batched, because one
        transaction deleting every edge of a large run would exceed the heap the compose
        file pins.
        """
        removed = 0
        with self._driver.session() as session:
            while True:
                record = session.run(
                    cypher.DROP_RUN_INFERENCES, run_id=run_id, batch_size=DELETE_BATCH_SIZE
                ).single()
                batch = 0 if record is None else record["removed"]
                removed += batch
                if batch == 0:
                    return removed

    # ------------------------------------------------------------------
    # Projection steps
    # ------------------------------------------------------------------

    def _supports_existence_constraints(self) -> bool:
        """Return whether this server can create property existence constraints.

        DEF-0004. Asked of the SERVER rather than configured, because the answer is a fact
        about the deployment and a configuration flag would be one more thing that can
        disagree with reality. `dbms.components()` is available on both editions.

        An unreadable answer is treated as Community -- the weaker assumption. Guessing
        Enterprise and being wrong reproduces the original defect, which is an abort in the
        middle of step 2; guessing Community and being wrong costs a slower check that
        still enforces the invariant.
        """
        try:
            with self._driver.session() as session:
                record = session.run(
                    "CALL dbms.components() YIELD edition RETURN edition LIMIT 1"
                ).single()
        except Neo4jError:
            return False
        if record is None:
            return False
        return str(record["edition"]).lower() == "enterprise"

    def _apply_schema(self, *, existence_constraints: bool) -> None:
        with self._driver.session() as session:
            for statement in schema.schema_statements(existence_constraints=existence_constraints):
                session.run(statement)

    def _verify_existence_invariants(self, namespace: str) -> None:
        """Check, after the write, what Enterprise would have made unrepresentable.

        Runs only on Community. Every violation found aborts the rebuild BEFORE the swap,
        so the guarantee a reader depends on -- an inferred edge always has a run, an
        observed edge never does -- holds for anything that actually serves traffic. What
        is lost relative to a constraint is that a violation is detected rather than
        prevented, and detected once per build rather than at every write.
        """
        violations = []
        with self._driver.session() as session:
            for description, query in schema.existence_invariant_queries():
                record = session.run(query, namespace=namespace).single()
                count = 0 if record is None else record["violations"]
                if count:
                    violations.append(f"{description}: {count}")
        if violations:
            raise ContractViolationError(
                "The staged projection violates invariants that Neo4j Enterprise would "
                "have enforced as constraints, and that this server (Community Edition) "
                "cannot: "
                + "; ".join(violations)
                + ". The rebuild is aborted before the swap, so the previous projection "
                "keeps serving. See DEF-0004."
            )

    def _project_entities(self, dataset_version: str, namespace: str) -> int:
        written = 0
        for batch in _batched(self._repository.entities_for_dataset(dataset_version)):
            rows = [
                {
                    "entity_id": entity.entity_id,
                    "entity_type": entity.entity_type,
                    "natural_key": entity.natural_key,
                    "provenance_class": entity.provenance_class.value,
                    "dataset_version": dataset_version,
                    "namespace": namespace,
                }
                for entity in batch
            ]
            written += self._write(cypher.MERGE_ENTITIES, rows, namespace)
        return written

    def _project_events(self, dataset_version: str, namespace: str) -> int:
        written = 0
        for batch in _batched(self._repository.events_for_dataset(dataset_version)):
            rows = [
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "t_earliest": _instant(event.occurred_at.t_earliest),
                    "t_latest": _instant(event.occurred_at.t_latest),
                    "time_precision": event.occurred_at.precision.value,
                    "time_provenance": event.occurred_at.provenance.value,
                    "provenance_class": event.provenance_class.value,
                    "is_actionable": event.is_actionable,
                    # The scalar is carried for DISPLAY and for ordering a result set. It
                    # is derived and non-authoritative, so it travels with the name of the
                    # function that produced it; a rollup whose function is unnamed is the
                    # unexplained number prd.md §49 forbids (ADR-0009). The decomposition
                    # itself stays in PostgreSQL: the projection is for traversal, and a
                    # judgement is not reconstructed from a traversal.
                    "confidence_scalar": event.confidence.scalar,
                    "confidence_aggregation": event.confidence.aggregation,
                    "source_record_ref": event.source_record_ref,
                    "dataset_version": dataset_version,
                    "namespace": namespace,
                }
                for event in batch
            ]
            written += self._write(cypher.MERGE_EVENTS, rows, namespace)
        return written

    def _project_states(self, dataset_version: str, namespace: str) -> int:
        written = 0
        for batch in _batched(self._repository.states_for_dataset(dataset_version)):
            rows = [
                {
                    "state_id": state.state_id,
                    "entity_id": state.entity_id,
                    "state_name": state.state_name,
                    "valid_from": _instant(state.held_over.t_earliest),
                    "valid_to": _instant(state.held_over.t_latest),
                    "valid_precision": state.held_over.precision.value,
                    "provenance_class": state.provenance_class.value,
                    "dataset_version": dataset_version,
                    "namespace": namespace,
                }
                for state in batch
            ]
            written += self._write(cypher.MERGE_STATES, rows, namespace)
        return written

    def _project_time_buckets(self, dataset_version: str, namespace: str) -> int:
        """Project the §47 `Time` label as deterministic day buckets (ADR-0034).

        The bucket is `date(t_earliest)`, computed here from the event's own bounds and
        from nothing else. That makes it a pure function of the event table: same events,
        same buckets, and a rebuild reproduces them exactly. An event with UNKNOWN
        precision is deliberately left unbucketed -- placing it in a bucket would assert a
        day the source never recorded, which is imputation under another name
        (`CONVENTIONS.md` §10).
        """
        buckets: dict[date, list[str]] = {}
        for event in self._repository.events_for_dataset(dataset_version):
            if event.occurred_at.precision.value == "UNKNOWN":
                continue
            buckets.setdefault(event.occurred_at.t_earliest.date(), []).append(event.event_id)
        rows = [
            {
                "bucket_start": bucket.isoformat(),
                "granularity": "DAY",
                "event_ids": sorted(event_ids),
                "dataset_version": dataset_version,
                "namespace": namespace,
            }
            for bucket, event_ids in sorted(buckets.items())
        ]
        if not rows:
            return 0
        self._write(cypher.CREATE_TIME_BUCKETS, rows, namespace)
        return len(rows)

    def _project_precedes(self, dataset_version: str, namespace: str) -> int:
        """Write PRECEDES from the canonical event sequence within each entity's timeline.

        Temporal ORDER, never causation. The edge exists because one event sequenced
        before another for the same participant, and `GLOSSARY.md` §2.1 is explicit that
        adjacency on a timeline is sequence and not a causal claim. Module 8 writes this
        family; only module 10 writes CAUSES, and the two never meet in this file.
        """
        by_entity: dict[str, list[Any]] = {}
        for event in self._repository.events_for_dataset(dataset_version):
            for entity_id in (*event.source_entity_ids, *event.target_entity_ids):
                by_entity.setdefault(entity_id, []).append(event)
        rows = []
        for entity_id, events in sorted(by_entity.items()):
            ordered = sorted(events, key=lambda item: (*item.occurred_at.sort_key(), item.event_id))
            for earlier, later in pairwise(ordered):
                rows.append(
                    {
                        "source_event_id": earlier.event_id,
                        "target_event_id": later.event_id,
                        "entity_id": entity_id,
                        "dataset_version": dataset_version,
                        "namespace": namespace,
                    }
                )
        written = 0
        for batch in _batched(iter(rows)):
            written += self._write(cypher.MERGE_PRECEDES, list(batch), namespace)
        return written

    def _project_relationships(self, dataset_version: str, namespace: str) -> int:
        statements = {
            "BELONGS_TO": cypher.MERGE_BELONGS_TO,
            "LOCATED_AT": cypher.MERGE_LOCATED_AT,
            "PART_OF": cypher.MERGE_PART_OF,
        }
        grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in statements}
        located_entities: set[str] = set()
        for relationship in self._repository.relationships_for_dataset(dataset_version):
            if relationship.relationship_type not in statements:
                raise ContractViolationError(
                    f"Relationship {relationship.relationship_id} has type "
                    f"{relationship.relationship_type!r}, which this projection has no "
                    "statement for. A structural type the graph cannot express is a "
                    "contract change, not something to skip quietly."
                )
            grouped[relationship.relationship_type].append(
                {
                    "relationship_id": relationship.relationship_id,
                    "source_entity_id": relationship.source_entity_id,
                    "target_entity_id": relationship.target_entity_id,
                    "valid_from": _instant(relationship.valid_over.t_earliest),
                    "valid_to": _instant(relationship.valid_over.t_latest),
                    "provenance_class": relationship.provenance_class.value,
                    "dataset_version": dataset_version,
                    "namespace": namespace,
                }
            )
            if relationship.relationship_type == "LOCATED_AT":
                located_entities.add(relationship.target_entity_id)

        written = 0
        for relationship_type, rows in grouped.items():
            for batch in _batched(iter(rows)):
                written += self._write(statements[relationship_type], list(batch), namespace)

        # The §47 `Location` label, applied to the entities something is located AT. The
        # label is derived from the observed LOCATED_AT edges rather than from an ontology
        # type name, so no domain vocabulary enters this file (LAW-DOMAIN) and the label
        # remains a function of the facts (ADR-0034).
        if located_entities:
            self._run(
                cypher.LABEL_LOCATIONS,
                {"entity_ids": sorted(located_entities), "namespace": namespace},
            )
        return written

    def _project_transitions(self, dataset_version: str, namespace: str) -> int:
        rows = [
            {
                "transition_id": transition.transition_id,
                "from_state_id": transition.from_state_id,
                "to_state_id": transition.to_state_id,
                "causing_event_id": transition.causing_event_id,
                "provenance_class": transition.provenance_class.value,
                "dataset_version": dataset_version,
                "namespace": namespace,
            }
            for transition in self._repository.transitions_for_dataset(dataset_version)
        ]
        written = 0
        for batch in _batched(iter(rows)):
            written += self._write(cypher.MERGE_TRANSITIONS_TO, list(batch), namespace)
        return written

    def _project_causal_edges(self, run_id: str, namespace: str) -> int:
        """Write the inferred family, one relationship type per edge kind.

        The mapping from the five payload kinds to the §47 inferred vocabulary is the one
        place those two taxonomies meet, and it is written out rather than derived so the
        correspondence is reviewable: prd.md §26 names five kinds and §47 names six
        inferred relationship types, and they are not the same list.
        """
        by_type: dict[str, list[dict[str, Any]]] = {}
        for edge in self._repository.causal_edges_for_run(run_id):
            relationship_type = _RELATIONSHIP_TYPE_FOR_EDGE_KIND[edge.edge_kind.value]
            by_type.setdefault(relationship_type, []).append(
                {
                    "causal_edge_id": edge.causal_edge_id,
                    "source_event_id": edge.source_event_id,
                    "target_event_id": edge.target_event_id,
                    "run_id": edge.run_id,
                    "edge_kind": edge.edge_kind.value,
                    "provenance_class": edge.provenance_class.value,
                    "confidence_scalar": edge.confidence.scalar,
                    "confidence_aggregation": edge.confidence.aggregation,
                    "propagation_weight": edge.propagation_weight,
                    "temporal_verdict": edge.temporal_verdict.value,
                    "temporally_unverifiable": edge.temporally_unverifiable,
                    "evidence_item_ids": sorted(item.evidence_item_id for item in edge.evidence),
                    "rule_ids": sorted(
                        item.verification for item in edge.evidence if item.kind.value == "RULE"
                    ),
                    "namespace": namespace,
                }
            )
        written = 0
        for relationship_type, rows in by_type.items():
            statement = cypher.MERGE_CAUSAL_EDGES.format(relationship_type=relationship_type)
            for batch in _batched(iter(rows)):
                written += self._write(statement, list(batch), namespace)
        return written

    # ------------------------------------------------------------------
    # Verification and the swap
    # ------------------------------------------------------------------

    def _verify_against_facts(self, run_id: str, dataset_version: str, namespace: str) -> None:
        """Compare the projection's counts against the counts computed from the facts.

        This is the step that catches "a node with no backing PostgreSQL fact", which
        ADR-0001 calls a defect. It runs BEFORE the swap, so a projection that fails it
        never serves anybody.
        """
        expected = self._repository.fact_counts(dataset_version, run_id)
        actual = self.element_counts(run_id, namespace)
        mismatches = []
        for label, key in (
            ("Entity", "entity"),
            ("Event", "event"),
            ("State", "state"),
        ):
            if actual.get(label, 0) != expected[key]:
                mismatches.append(
                    f"{label}: projection {actual.get(label, 0)}, facts {expected[key]}"
                )
        projected_edges = sum(
            actual.get(relationship_type, 0)
            for relationship_type in schema.INFERRED_RELATIONSHIP_TYPES
        )
        if projected_edges != expected["causal_edge"]:
            mismatches.append(
                f"inferred edges: projection {projected_edges}, facts {expected['causal_edge']}"
            )
        if mismatches:
            raise ContractViolationError(
                f"Projection for run {run_id} does not match the facts it was built from: "
                + "; ".join(mismatches)
                + ". The rebuild is aborted before the swap, so the previous projection "
                "keeps serving. A projected element with no backing fact is a defect "
                "(ADR-0001), never something to reconcile."
            )

    def _swap(
        self,
        run_id: str,
        namespace: str,
        version: str,
        content_hash: str,
        node_count: int,
        edge_count: int,
    ) -> None:
        """Make the staged build live, in one transaction against the registry."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE graph_projection SET status = 'superseded', superseded_at = now() "
                "WHERE run_id = %s AND status = 'live'",
                (run_id,),
            )
            cursor.execute(
                "INSERT INTO graph_projection (run_id, graph_projection_version, namespace, "
                "content_hash, node_count, edge_count, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'live')",
                (run_id, version, namespace, content_hash, node_count, edge_count),
            )
            cursor.execute(
                "UPDATE run SET graph_projection_version = %s WHERE run_id = %s",
                (version, run_id),
            )
            connection.commit()

    def _previous_content_hash(self, run_id: str) -> str | None:
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT content_hash FROM graph_projection WHERE run_id = %s "
                "AND status IN ('live', 'superseded') ORDER BY built_at DESC LIMIT 1",
                (run_id,),
            )
            record = cursor.fetchone()
        return None if record is None else str(record[0])

    def _drop_namespace(self, namespace: str) -> int:
        """Remove a superseded build's elements, relationships first.

        Neo4j refuses to delete a node that still has relationships, and `DETACH DELETE`
        would reach across into another namespace's edges if one ever pointed here. Two
        explicit statements say exactly what is removed.
        """
        removed = 0
        with self._driver.session() as session:
            for statement in (
                cypher.DROP_NAMESPACE_RELATIONSHIPS,
                cypher.DROP_NAMESPACE_NODES,
            ):
                while True:
                    record = session.run(
                        statement, namespace=namespace, batch_size=DELETE_BATCH_SIZE
                    ).single()
                    batch = 0 if record is None else record["removed"]
                    removed += batch
                    if batch == 0:
                        break
        return removed

    def _live_namespace_or_none(self, run_id: str) -> str | None:
        """Return the live namespace for a run, or None when there is not one yet."""
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT namespace FROM graph_projection WHERE run_id = %s AND status = 'live'",
                (run_id,),
            )
            record = cursor.fetchone()
        return None if record is None else str(record[0])

    def _live_namespace(self, run_id: str) -> str:
        """Return the live namespace, or refuse. The refusal is the point.

        A caller that gets no namespace back would otherwise read the whole store, which
        includes staged and superseded builds -- an older graph served as if it were the
        current one, which `docs/architecture.md` §3.2 forbids by name.
        """
        namespace = self._live_namespace_or_none(run_id)
        if namespace is None:
            raise ProjectionStaleError(
                f"No live projection for run {run_id}. The store is not asked which "
                "version it holds -- PostgreSQL is (ADR-0001) -- and it says there is "
                f"none. Build one with `make rebuild-graph RUN_ID={run_id}`."
            )
        return namespace

    def _next_namespace(self, run_id: str) -> str:
        with self._factory.connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM graph_projection WHERE run_id = %s", (run_id,))
            record = cursor.fetchone()
        sequence = 0 if record is None else int(record[0])
        return f"{run_id.replace(':', '_')}_{sequence:04d}"

    # ------------------------------------------------------------------
    # Driver plumbing
    # ------------------------------------------------------------------

    def _write(self, statement: str, rows: list[dict[str, Any]], namespace: str) -> int:
        if not rows:
            return 0
        record = self._run(statement, {"rows": rows, "namespace": namespace})
        return 0 if record is None else int(record.get("written", 0))

    def _run(self, statement: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
        with self._driver.session() as session:
            result = session.run(statement, **parameters).single()
            return None if result is None else dict(result)


#: prd.md §26's five payload kinds mapped onto prd.md §47's inferred vocabulary. Written
#: out rather than derived: the two lists are different lengths and were written for
#: different purposes, so the correspondence is a decision (ADR-0034) and deserves to be
#: reviewable in one place. `BLOCKS` and `RECOMMENDS` have no edge kind behind them today
#: -- `RECOMMENDS` lands with module 14 -- and their absence here is recorded rather than
#: papered over with a default.
_RELATIONSHIP_TYPE_FOR_EDGE_KIND: Final[dict[str, str]] = {
    "DIRECT": "CAUSES",
    "CONDITIONAL": "CAUSES",
    "CONTRIBUTING": "AFFECTS",
    "AMPLIFYING": "AMPLIFIES",
    "INHIBITING": "REDUCES",
}


def _instant(moment: datetime) -> str:
    """Render an instant as ISO-8601 UTC for the Cypher `datetime()` constructor."""
    return moment.isoformat()


def _batched(source: Iterator[Any]) -> Iterator[Sequence[Any]]:
    """Yield the source in write-sized batches, preserving its canonical sequence."""
    batch: list[Any] = []
    for item in source:
        batch.append(item)
        if len(batch) >= WRITE_BATCH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch
