"""LAW-PROVENANCE and prd.md §54, enforced by the database and observed to fire.

prd.md §54 requires immutable event history and that no inferred result overwrite an
observed fact. ADR-0004 requires that a correction emit a NEW event rather than mutate one.
Neither may be left to application discipline: the reasoning modules are not the only thing
that can hold a connection, and a `psql` session is one keystroke away from every fact in
the system.

So the enforcement is a trigger, and these tests **observe it RAISE**. That distinction is
the whole point of the file. Asserting that a row is unchanged after an UPDATE would pass
against a `DO INSTEAD NOTHING` rule -- which reports success for a write it discarded, and
is therefore indistinguishable to the caller from a write that landed. That was DEF-0003,
and migration 0014 fixed it; this file is the regression test that keeps it fixed.

Marked `law`: a failure here is CRITICAL (`CONVENTIONS.md` §14).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests import persistence_support
from tests.fixtures import facts

pytestmark = pytest.mark.law

#: Every table that holds a fact or an addressed artifact, paired with a column this test
#: can attempt to touch. The list is the point: a table added to the schema without an
#: append-only trigger shows up as an absence here, so a reviewer reads this list against
#: the migrations rather than trusting that every table got one.
#:
#: The column is a real one per table rather than a shared name, so the UPDATE reaches the
#: trigger instead of failing at parse time -- a test that failed on an undefined column
#: would look exactly like a test that caught the violation.
APPEND_ONLY_TABLES = (
    ("evidence_record", "source_locator"),
    ("entity", "provenance_class"),
    ("event", "provenance_class"),
    ("causal_edge", "provenance_class"),
    ("audit_log", "actor"),
    ("confidence_vector", "aggregation"),
    ("evidence_item", "description"),
    ("recommendation", "provenance_class"),
    ("counterfactual_scenario", "provenance_class"),
    # DEF-0006. Added 2026-08-29. Every one of these was UPDATEable and DELETEable in a
    # schema whose whole claim is that facts are append-only, and the list above is why
    # nobody noticed: it was hand-written, it was short, and reading it against the
    # migrations required already suspecting something was missing. The catalogue test
    # below replaces that reading with a query, so the next table cannot arrive unguarded.
    ("entity_evidence", "evidence_record_id"),
    ("confidence_component_evidence", "evidence_record_id"),
    ("causal_edge_evidence", "evidence_item_id"),
    ("causal_edge_co_cause", "co_cause_event_id"),
    ("causal_edge_fired_rule", "rule_id"),
    ("entity_lifecycle_state", "state_name"),
    ("entity_lifecycle_transition", "to_state_name"),
)

#: Tables that are deliberately NOT append-only, with the reason each is exempt. Anything
#: in `public` that is not guarded and not named here fails `test_every_fact_table_is_guarded`.
#: An exemption is a decision that must be written down; the failure mode this replaces is a
#: table that is unguarded because nobody looked.
MUTABLE_BY_DESIGN = {
    "schema_migration": "the migration ledger itself; `migrate --down` must delete from it",
    "dataset_version": "an input registry, written once per pinned dataset, not a fact",
    "ontology_version": "an input registry (ADR-0002), not a fact",
    "rule_pack_version": "an input registry, not a fact",
    "run": "the run registry; rows are inserted and never edited, but immutability here is "
    "not part of the LAW-PROVENANCE claim and adding a guard is a design change, not a fix",
    "graph_projection": "a DERIVED registry whose rows move along a status ladder "
    "(staged -> live -> superseded); its own trigger enforces that ladder. Guarded against "
    "TRUNCATE only, because losing it loses the determinism tripwire of rebuild step 6.",
}


@pytest.fixture
def factory() -> None:
    """Yield a connection factory over a freshly migrated schema."""
    yield from persistence_support.migrated_database()


def _seed(factory: Any) -> dict[str, str]:
    """Plant one row in every append-only table and return their keys."""
    persistence_support.register_dataset(factory, facts.DATASET_VERSION, facts.ONTOLOGY_HASH)
    from causalog.core.run import RunKey
    from causalog.persistence.postgres.fact_repository import PostgresFactRepository

    repository = PostgresFactRepository(factory)
    citation = facts.evidence_record("row:1")
    repository.write_evidence_records([citation])
    participant = facts.entity("P1", citation=citation)
    repository.write_entities([participant], facts.ONTOLOGY_HASH)
    early = facts.event(
        "STAGE_ONE", facts.interval(0), citation=citation, participants=(participant,)
    )
    late = facts.event(
        "STAGE_TWO", facts.interval(10), citation=citation, participants=(participant,)
    )
    repository.write_events([early, late], facts.ONTOLOGY_HASH)

    run_id = repository.register_run(
        RunKey(
            dataset_version=facts.DATASET_VERSION,
            ontology_hash=facts.ONTOLOGY_HASH,
            rule_pack_version="1.0.0",
            engine_version="0.1.0",
            seed=0,
        )
    )
    edge = facts.causal_edge(early, late, run_id)
    repository.write_causal_edges([edge])

    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO audit_log (run_id, auditable_event, action, target, target_kind, "
            "actor, payload) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                run_id,
                "CAUSAL_EDGE_INFERRED",
                "CAUSAL_EDGE_INFERRED",
                edge.causal_edge_id,
                "CAUSAL_EDGE",
                "test",
                "{}",
            ),
        )
        cursor.execute(
            "INSERT INTO recommendation (recommendation_id, run_id, provenance_class, "
            "payload, canonical_schema_version) VALUES (%s, %s, %s, %s, %s)",
            ("rec:0000000000000001", run_id, "INFERRED", "{}", "1.0.0"),
        )
        cursor.execute(
            "INSERT INTO counterfactual_scenario (simulated_world_id, run_id, base_graph_id, "
            "provenance_class, assumption_statement, payload, canonical_schema_version) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                "sim:0000000000000001",
                run_id,
                "gph:1",
                "SIMULATED",
                "no unobserved confounders",
                "{}",
                "1.0.0",
            ),
        )
        # The three edge junction tables. `write_causal_edges` fills `causal_edge_evidence`
        # from the edge's evidence, but a `DirectCause` payload carries neither co-causes
        # nor fired rules, so those two are planted here. Without rows, a BEFORE ROW trigger
        # never fires and `test_delete_raises` would pass against a table with no guard at
        # all -- the empty-table version of DEF-0001.
        cursor.execute(
            "INSERT INTO causal_edge_co_cause (causal_edge_id, co_cause_event_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (edge.causal_edge_id, late.event_id),
        )
        cursor.execute(
            "INSERT INTO causal_edge_fired_rule (causal_edge_id, rule_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (edge.causal_edge_id, "R-FIXTURE-0001"),
        )
        connection.commit()

    # Every table the matrix names must actually hold a row, or the operation never reaches
    # the trigger and the test reports a pass it did not earn.
    with factory.connect() as connection, connection.cursor() as cursor:
        for table, _ in APPEND_ONLY_TABLES:
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
            assert cursor.fetchone()[0] > 0, (
                f"The seed left {table} empty. An UPDATE or DELETE against an empty table "
                "raises nothing whether or not the guard exists, so the row-level tests "
                "would pass vacuously -- which is the failure shape this file exists to "
                "prevent."
            )
    return {"run_id": run_id, "event_id": early.event_id, "edge_id": edge.causal_edge_id}


@pytest.mark.parametrize(("table", "column"), APPEND_ONLY_TABLES)
def test_update_raises(factory: Any, table: str, column: str) -> None:
    """An UPDATE on any append-only table must RAISE, not silently do nothing."""
    import psycopg

    _seed(factory)
    with factory.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RestrictViolation) as raised:
            # A no-op assignment, deliberately: the refusal must not depend on the value
            # actually changing. "It only refuses real edits" would leave a writer able to
            # touch a row and learn nothing about whether the guard was there.
            cursor.execute(f"UPDATE {table} SET {column} = {column}")  # noqa: S608
        assert "LAW-PROVENANCE" in str(raised.value), (
            f"The refusal on {table} must NAME the law it enforces. An error that says "
            "only 'permission denied' sends the reader to the grants, not to ADR-0004."
        )
        connection.rollback()


@pytest.mark.parametrize(("table", "column"), APPEND_ONLY_TABLES)
def test_delete_raises(factory: Any, table: str, column: str) -> None:
    """A DELETE on any append-only table must RAISE. History is not editable."""
    import psycopg

    del column  # the delete needs no column; the parameter set is shared with the update
    _seed(factory)
    with factory.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RestrictViolation) as raised:
            cursor.execute(f"DELETE FROM {table}")  # noqa: S608
        assert "append-only" in str(raised.value)
        connection.rollback()


def test_the_refusal_is_raised_and_not_swallowed(factory: Any) -> None:
    """The DEF-0003 regression, stated as its own test because it is the subtle one.

    Before migration 0014, `audit_log` refused an UPDATE with
    `CREATE RULE ... DO INSTEAD NOTHING`, which reports SUCCESS for a write it discarded.
    A test that only asserted the row was unchanged would have passed against that rule --
    and the caller would have believed its edit landed. This asserts the shape of the
    failure, not only its effect.
    """
    import psycopg

    _seed(factory)
    with factory.connect() as connection, connection.cursor() as cursor:
        try:
            cursor.execute("UPDATE audit_log SET actor = 'somebody else'")
        except psycopg.errors.RestrictViolation:
            connection.rollback()
        else:  # pragma: no cover -- reached only if the defect returns
            pytest.fail(
                "UPDATE on audit_log reported success. A rejected write that returns "
                "success is indistinguishable from an accepted one -- this is DEF-0003, "
                "and migration 0014 exists to make it impossible."
            )

    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM audit_log WHERE actor = 'somebody else'")
        assert cursor.fetchone()[0] == 0


def test_an_inferred_artifact_cannot_exist_without_a_run(factory: Any) -> None:
    """`run_id NOT NULL` on every inferred artifact, enforced by the schema (ADR-0013).

    This is what makes "inference never overwrites observation" structural rather than
    procedural: an inference module writes only into run-scoped storage, so it is
    INCAPABLE of touching a dataset-scoped fact rather than merely forbidden from it.
    """
    import psycopg

    seeded = _seed(factory)
    for statement, parameters in (
        (
            "INSERT INTO causal_edge (causal_edge_id, run_id, source_event_id, "
            "target_event_id, edge_kind, confidence_vector_id, propagation_weight, "
            "provenance_class, temporal_verdict, temporally_unverifiable) "
            "VALUES ('edg:x', NULL, %s, %s, 'DIRECT', 1, 0.5, 'INFERRED', 'CERTAIN', false)",
            (seeded["event_id"], seeded["event_id"]),
        ),
        (
            "INSERT INTO recommendation (recommendation_id, run_id, provenance_class, "
            "payload, canonical_schema_version) VALUES ('rec:x', NULL, 'INFERRED', '{}', '1.0.0')",
            (),
        ),
        (
            "INSERT INTO counterfactual_scenario (simulated_world_id, run_id, base_graph_id, "
            "provenance_class, assumption_statement, payload, canonical_schema_version) "
            "VALUES ('sim:x', NULL, 'g', 'SIMULATED', 'a', '{}', '1.0.0')",
            (),
        ),
    ):
        with factory.connect() as connection, connection.cursor() as cursor:
            with pytest.raises(psycopg.errors.NotNullViolation):
                cursor.execute(statement, parameters)
            connection.rollback()


def test_a_causal_edge_may_not_carry_observed_provenance(factory: Any) -> None:
    """Causation is never read from a source record (docs/contracts.md §5)."""
    import psycopg

    seeded = _seed(factory)
    with factory.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                "INSERT INTO causal_edge (causal_edge_id, run_id, source_event_id, "
                "target_event_id, edge_kind, confidence_vector_id, propagation_weight, "
                "provenance_class, temporal_verdict, temporally_unverifiable) "
                "VALUES ('edg:y', %s, %s, %s, 'DIRECT', 1, 0.5, 'OBSERVED', 'CERTAIN', false)",
                (seeded["run_id"], seeded["event_id"], seeded["event_id"]),
            )
        connection.rollback()


def test_a_violating_temporal_verdict_has_no_admissible_row(factory: Any) -> None:
    """LAW-TIME in the schema: a VIOLATION edge is never created, so it cannot be stored."""
    import psycopg

    seeded = _seed(factory)
    with factory.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                "INSERT INTO causal_edge (causal_edge_id, run_id, source_event_id, "
                "target_event_id, edge_kind, confidence_vector_id, propagation_weight, "
                "provenance_class, temporal_verdict, temporally_unverifiable) "
                "VALUES ('edg:z', %s, %s, %s, 'DIRECT', 1, 0.5, 'INFERRED', 'VIOLATION', false)",
                (seeded["run_id"], seeded["event_id"], seeded["event_id"]),
            )
        connection.rollback()


def test_an_undetermined_edge_may_not_claim_inferred_provenance(factory: Any) -> None:
    """An unpromotable candidate cannot be laundered into an inference by a direct write."""
    import psycopg

    seeded = _seed(factory)
    with factory.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                "INSERT INTO causal_edge (causal_edge_id, run_id, source_event_id, "
                "target_event_id, edge_kind, confidence_vector_id, propagation_weight, "
                "provenance_class, temporal_verdict, temporally_unverifiable) "
                "VALUES ('edg:w', %s, %s, %s, 'DIRECT', 1, 0.5, 'INFERRED', 'UNDETERMINED', "
                "false)",
                (seeded["run_id"], seeded["event_id"], seeded["event_id"]),
            )
        connection.rollback()


# ---------------------------------------------------------------------------
# DEF-0005: TRUNCATE. The verb the guard did not cover.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("table", "column"), APPEND_ONLY_TABLES)
def test_truncate_raises(factory: Any, table: str, column: str) -> None:
    """TRUNCATE on any append-only table must RAISE.

    DEF-0005. `causalog_refuse_mutation` was attached BEFORE UPDATE OR DELETE, and TRUNCATE
    is neither, so it went straight past every guard in the schema. Observed directly:
    `UPDATE event ...` raised, `DELETE FROM event` raised, and `TRUNCATE event CASCADE`
    succeeded -- taking `event` and cascading into ten more tables including `causal_edge`
    and `state`.

    This is precisely the threat migration 0004 names for itself: a grant is the first line
    of defence, and the trigger exists because "a superuser connection, a migration, and a
    psql session all bypass a grant". TRUNCATE is the verb that reaches the facts down that
    path, and until migration 0016 nothing stopped it.

    A statement-level trigger, because TRUNCATE has no rows to fire per-row against -- which
    is also why the row-level guard could never have covered it.
    """
    import psycopg

    del column  # the truncate needs no column; the parameter set is shared

    _seed(factory)
    with factory.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RestrictViolation) as raised:
            cursor.execute(f"TRUNCATE {table} CASCADE")
        assert "LAW-PROVENANCE" in str(
            raised.value
        ), f"The refusal on {table} must NAME the law it enforces."
        connection.rollback()

    # The refusal must also have left the data alone. A guard that raises after the rows are
    # gone would satisfy the assertion above and lose the history anyway.
    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
        assert (
            cursor.fetchone()[0] > 0
        ), f"TRUNCATE on {table} raised, but the table is empty afterwards."


def test_truncating_a_parent_cannot_cascade_into_a_guarded_child(factory: Any) -> None:
    """The cascade path, which is how the defect actually destroyed ten tables.

    `TRUNCATE event CASCADE` never names `causal_edge` or `state`, and took both. Guarding
    each table individually is only sufficient if the guard fires before the cascade
    reaches the child, so that is asserted rather than assumed.
    """
    import psycopg

    cascade_targets = (
        "event",
        "causal_edge",
        "state",
        "event_evidence",
        "state_transition",
        "causal_edge_evidence",
        "event_entity",
    )

    _seed(factory)

    # Counts BEFORE, and the assertion is that they are unchanged -- not that they are
    # non-zero. `state_transition` is empty in this fixture, and "still empty" is a pass
    # while "was 3, now 0" is the failure. Asserting non-emptiness instead would make the
    # test depend on the seed happening to populate every table in the cascade.
    with factory.connect() as connection, connection.cursor() as cursor:
        before = {}
        for table in cascade_targets:
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
            before[table] = cursor.fetchone()[0]

    assert (
        before["event"] > 0 and before["causal_edge"] > 0
    ), "The two tables this test is really about must hold rows, or it proves nothing."

    with factory.connect() as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RestrictViolation):
            cursor.execute("TRUNCATE event CASCADE")
        connection.rollback()

    with factory.connect() as connection, connection.cursor() as cursor:
        for table in cascade_targets:
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
            assert (
                cursor.fetchone()[0] == before[table]
            ), f"A cascading TRUNCATE from `event` changed the row count of {table}."


# ---------------------------------------------------------------------------
# DEF-0006: coverage read from the catalogue, not from a hand-written list.
# ---------------------------------------------------------------------------


def test_every_fact_table_is_guarded(factory: Any) -> None:
    """Every table in `public` is either guarded or explicitly exempt.

    DEF-0006. Seven fact tables carried no append-only trigger at all -- `entity_evidence`,
    `confidence_component_evidence`, `causal_edge_evidence`, `causal_edge_co_cause`,
    `causal_edge_fired_rule`, `entity_lifecycle_state` and `entity_lifecycle_transition`.
    `DELETE FROM confidence_component_evidence` succeeded against a migrated database, and
    that is the table `CONVENTIONS.md` §8 requires so a confidence number can be
    reconstructed from an audit record alone.

    `APPEND_ONLY_TABLES` did not catch it. Its comment said the list was the point -- that a
    table added without a trigger "shows up as an absence here, so a reviewer reads this list
    against the migrations". Reading it against the migrations required already suspecting
    something was missing, and for seven tables across nine migrations nobody did. So the
    reading is now a query: the catalogue is the source of truth, and a new table is a
    FAILURE until somebody either guards it or writes down why it is exempt.
    """
    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT t.relname,
                   count(*) FILTER (WHERE g.tgtype & 16 > 0 OR g.tgtype & 8 > 0) AS row_guard,
                   count(*) FILTER (WHERE g.tgtype & 32 > 0)                     AS truncate_guard
            FROM pg_class t
            JOIN pg_namespace n ON n.oid = t.relnamespace
            LEFT JOIN pg_trigger g ON g.tgrelid = t.oid AND NOT g.tgisinternal
            WHERE n.nspname = 'public' AND t.relkind = 'r'
            GROUP BY t.relname
            ORDER BY t.relname
            """
        )
        rows = cursor.fetchall()

    unguarded = [
        name for name, row_guard, _ in rows if row_guard == 0 and name not in MUTABLE_BY_DESIGN
    ]
    assert not unguarded, (
        f"These tables accept UPDATE and DELETE and are not declared mutable by design: "
        f"{sorted(unguarded)}. Guard them in a migration, or add them to MUTABLE_BY_DESIGN "
        "with the reason. An unguarded fact table is DEF-0006."
    )

    untruncatable = [
        name
        for name, _, truncate_guard in rows
        if truncate_guard == 0 and (name not in MUTABLE_BY_DESIGN or name == "graph_projection")
    ]
    assert (
        not untruncatable
    ), f"These tables can be emptied by TRUNCATE: {sorted(untruncatable)}. This is DEF-0005."


def test_the_exemption_list_names_only_tables_that_exist(factory: Any) -> None:
    """An exemption for a table that is gone is an exemption nobody is reading.

    Without this, `MUTABLE_BY_DESIGN` accumulates dead entries, and a future table that
    happens to reuse a retired name inherits an exemption written about something else.
    """
    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
        existing = {row[0] for row in cursor.fetchall()}

    stale = set(MUTABLE_BY_DESIGN) - existing
    assert not stale, f"MUTABLE_BY_DESIGN names tables that do not exist: {sorted(stale)}"
