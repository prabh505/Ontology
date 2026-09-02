"""The prd.md §55 load budget, measured rather than asserted.

"Dataset loading < 30 seconds" for the reference dataset. This file measures it, prints the
throughput, and fails when the budget is missed.

THE SHAPE IS TAKEN FROM THE REAL FILE, NOT GUESSED. The constants below were measured from
`datasets/raw/DataCoSupplyChainDataset.csv` (SHA-256
994b3c8d24049cc46bf20e8161fedece9a9b95376cc0dc929921d76cf6b9bc0d): 180 519 data rows,
65 752 distinct orders, 20 652 distinct customers, 118 distinct products.
`test_the_measured_shape_still_matches_the_real_file` re-reads the file and fails if those
numbers drift, so the synthetic fixture cannot quietly stop resembling the thing it stands
in for. That test skips when the file is absent -- it is git-ignored and pinned by hash,
never committed -- and the benchmark itself does not need it.

WHY SYNTHETIC AND NOT THE CSV ITSELF. Turning DataCo rows into `Event` values is the job of
modules 1-4 (Data Adapter, Schema Mapper, Entity Extractor, Event Generator), none of which
exist. Doing it here would mean inventing the column-to-concept mapping in a persistence
test -- the mapping is ontology data (ADR-0002), and a second copy of it living in a test
is exactly the drift the ontology layer was built to prevent. What this benchmark measures
is the thing this layer owns: how long it takes to get 180 519 validated artifacts into the
system of record.

OQ-018, stated in the output rather than hidden. prd.md §55 does not say whether "dataset
loading" means the source rows or the events derived from them. ADR-0029 records that the
DataCo pack declares ONE observed event type and twenty derived ones, so the two readings
differ by a factor of about twenty-one. This test reports both figures and asserts the
budget against the observed-row reading, which is the smaller claim.

Marked `slow`: excluded from `make test-fast`, run by `make bench` and by CI.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

import pytest

from tests import persistence_support
from tests.fixtures import facts

pytestmark = pytest.mark.slow

#: Measured from the pinned source file. See the module docstring.
DATACO_ROWS = 180_519
DATACO_ORDERS = 65_752
DATACO_CUSTOMERS = 20_652
DATACO_PRODUCTS = 118

#: prd.md §55: "Dataset loading < 30 seconds".
LOAD_BUDGET_SECONDS = 30.0

#: ADR-0029: the DataCo pack declares one OBSERVED event type and twenty DERIVED ones.
#: Used only to report the second reading of OQ-018, never to relax the assertion.
DERIVED_EVENT_TYPES_PER_ROW = 21

DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "datasets" / "raw" / "DataCoSupplyChainDataset.csv"
)


def _synthetic_dataset() -> None:
    """Build the three artifact streams at DataCo's measured shape, and time the building.

    The artifacts are MATERIALISED HERE, outside the timed region, and the construction
    cost is reported separately. That split is the honest one, and it is not a way to make
    the number smaller:

      * Constructing an `Event` is content addressing plus full validation -- a SHA-256
        over a canonical payload and every invariant in `docs/contracts.md` §5. That work
        belongs to modules 1-4 (Data Adapter, Schema Mapper, Entity Extractor, Event
        Generator), none of which exist. Charging it to the persistence layer would
        measure this fixture factory, which is not what module 4 will do and not what the
        §55 budget is about.
      * Charging it to NOBODY would be worse, so it is measured and printed beside the
        load, and the total is printed too. When modules 1-4 land, the end-to-end figure
        is the one prd.md §55 is finally judged against, and this test already reports it.

    Materialising also costs the streaming property the loader has and this fixture does
    not need: the loader still consumes iterators and still bounds its own memory by
    `COPY_CHUNK_ROWS`, which is asserted by the loader's design rather than by this test.
    """
    started = time.monotonic()
    citations = [facts.evidence_record(f"row:{index}") for index in range(DATACO_ROWS)]
    entities = [
        facts.entity(f"C{index}", "PARTICIPANT", citation=citations[index])
        for index in range(DATACO_CUSTOMERS)
    ]
    entities += [
        facts.entity(f"G{index}", "GROUPING", citation=citations[index])
        for index in range(DATACO_ORDERS)
    ]
    entities += [
        facts.entity(f"K{index}", "KIND", citation=citations[index])
        for index in range(DATACO_PRODUCTS)
    ]
    events = [
        facts.event("STAGE_ONE", facts.interval(index % 1_000), citation=citations[index])
        for index in range(DATACO_ROWS)
    ]
    return citations, entities, events, time.monotonic() - started


@pytest.fixture
def bulk_writer() -> None:
    """Yield a bulk writer over a freshly migrated, empty schema."""
    from causalog.persistence.postgres.bulk_loader import PostgresBulkFactWriter

    generator = persistence_support.migrated_database()
    factory = next(generator)
    persistence_support.register_dataset(factory, facts.DATASET_VERSION, facts.ONTOLOGY_HASH)
    yield PostgresBulkFactWriter(factory), factory
    for _ in generator:
        pass


def test_a_dataset_sized_load_meets_the_prd_55_budget(
    bulk_writer: tuple[Any, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    writer, factory = bulk_writer
    citations, entities, events, construction_seconds = _synthetic_dataset()

    started = time.monotonic()
    report = writer.load_dataset(
        dataset_version=facts.DATASET_VERSION,
        ontology_hash=facts.ONTOLOGY_HASH,
        entities=iter(entities),
        events=iter(events),
        evidence_records=iter(citations),
    )
    elapsed = time.monotonic() - started

    throughput = report.event_count / max(elapsed, 1e-9)
    with capsys.disabled():
        print(
            f"\n  prd.md §55 dataset load"
            f"\n    rows (observed events)   {report.event_count:>10,}"
            f"\n    entities                 {report.entity_count:>10,}"
            f"\n    citations                {report.evidence_record_count:>10,}"
            f"\n"
            f"\n    PERSISTENCE (this layer, budgeted below)"
            f"\n      elapsed                {elapsed:>10.2f}s   budget {LOAD_BUDGET_SECONDS:.0f}s"
            f"\n      throughput             {throughput:>10,.0f} events/s"
            f"\n"
            f"\n    ARTIFACT CONSTRUCTION (modules 1-4, not built; this fixture stands in)"
            f"\n      elapsed                {construction_seconds:>10.2f}s"
            f"\n      end-to-end total       {construction_seconds + elapsed:>10.2f}s"
            f"\n"
            f"\n  OQ-018 -- prd.md §55 does not say which reading 'dataset loading' means:"
            f"\n    observed rows only       {DATACO_ROWS:>10,}  measured above"
            f"\n    with derived event types {DATACO_ROWS * DERIVED_EVENT_TYPES_PER_ROW:>10,}"
            f"  (ADR-0029: 1 observed + 20 derived)"
            f"\n    projected at this rate   "
            f"{elapsed * DERIVED_EVENT_TYPES_PER_ROW:>10.1f}s"
            f"\n"
        )

    assert report.event_count == DATACO_ROWS
    assert report.entity_count == DATACO_CUSTOMERS + DATACO_ORDERS + DATACO_PRODUCTS
    assert elapsed < LOAD_BUDGET_SECONDS, (
        f"The persistence load took {elapsed:.2f}s against the {LOAD_BUDGET_SECONDS:.0f}s "
        "prd.md §55 budget.\n\n"
        "This assertion is deliberately left able to fail, and it currently DOES fail on "
        "the development machine this was written on (PostgreSQL 16 is the deployment "
        "target; the measurement above was taken against a local PostgreSQL 14 with "
        "default server configuration). The number is a measurement of a product "
        "requirement, so the honest responses are to make the load path faster or to "
        "change the requirement -- never to raise LOAD_BUDGET_SECONDS until the test goes "
        "green, which would convert a known miss into an unknown one.\n\n"
        "What has already been tried, with measurements, is recorded in PROGRESS.md: "
        "COPY instead of INSERT, one transaction, UNLOGGED staging, synchronous_commit "
        "off, work_mem and maintenance_work_mem raised for the load transaction, and the "
        "removal of a speculative GiST index that cost about a tenth of the budget. What "
        "has NOT been tried is the deployment configuration, because this project has no "
        "reachable container runtime today."
    )


def test_re_running_a_load_is_idempotent(bulk_writer: tuple[Any, Any]) -> None:
    """A re-run after a failure must be safe.

    The bulk path promotes through `ON CONFLICT DO NOTHING`, so a load that failed halfway
    is re-run rather than reconciled. If a second run inserted duplicates instead, the
    remedy for a failed ingest would be "work out how far it got", which is exactly the
    position the single-transaction design exists to avoid.
    """
    writer, factory = bulk_writer
    citations = [facts.evidence_record(f"row:{index}") for index in range(200)]
    participants = [facts.entity(f"C{index}", citation=citations[index]) for index in range(50)]
    events = [
        facts.event("STAGE_ONE", facts.interval(index % 30), citation=citations[index])
        for index in range(200)
    ]

    first = writer.load_dataset(
        dataset_version=facts.DATASET_VERSION,
        ontology_hash=facts.ONTOLOGY_HASH,
        entities=iter(participants),
        events=iter(events),
        evidence_records=iter(citations),
    )
    writer.load_dataset(
        dataset_version=facts.DATASET_VERSION,
        ontology_hash=facts.ONTOLOGY_HASH,
        entities=iter(participants),
        events=iter(events),
        evidence_records=iter(citations),
    )

    with factory.connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM event")
        assert cursor.fetchone()[0] == first.event_count
        cursor.execute("SELECT count(*) FROM entity")
        assert cursor.fetchone()[0] == first.entity_count
        cursor.execute("SELECT count(*) FROM confidence_component")
        components = cursor.fetchone()[0]
    assert components == first.event_count, (
        "A second load duplicated confidence components. The vectors are keyed by a "
        "surrogate rather than by a content address, so they are the one part of the bulk "
        "path where a re-run could double up -- which is why this is asserted separately "
        "from the event count."
    )


def test_a_bulk_load_still_refuses_an_unevidenced_observation(bulk_writer: tuple[Any, Any]) -> None:
    """The fast path enforces the same law as the row path.

    A performance path that skipped LAW-EVIDENCE would make the law hold only for small
    datasets, which is the opposite of where it matters.
    """
    from causalog.core.errors import LawViolationError

    writer, _ = bulk_writer
    citation = facts.evidence_record("row:1")
    unevidenced = facts.event("STAGE_ONE", facts.interval(0), citation=citation).model_copy(
        update={"evidence_record_ids": ()}
    )
    with pytest.raises(LawViolationError, match="LAW-EVIDENCE"):
        writer.load_dataset(
            dataset_version=facts.DATASET_VERSION,
            ontology_hash=facts.ONTOLOGY_HASH,
            entities=iter(()),
            events=iter([unevidenced]),
            evidence_records=iter([citation]),
        )


def test_the_bulk_path_stores_exactly_what_the_row_path_stores(
    bulk_writer: tuple[Any, Any],
) -> None:
    """The fast path and the correctness path must produce identical rows.

    This test exists because they did not. The first version of the bulk loader wrote
    `confidence_component` and silently skipped `confidence_component_evidence` -- the
    LAW-EVIDENCE hook of `CONVENTIONS.md` §8, which is what makes a confidence number
    reconstructible from an audit record. The row path wrote it; the fast path did not; and
    nothing compared them, so the law held for small loads and quietly stopped holding for
    real ones. That is exactly backwards, and it is the shape of defect a performance path
    invites.

    Comparing the two stores table by table, rather than spot-checking the one column that
    was wrong, is what makes the NEXT divergence fail here too.
    """
    from causalog.persistence.postgres.fact_repository import PostgresFactRepository

    writer, factory = bulk_writer

    citations = [facts.evidence_record(f"row:{index}") for index in range(25)]
    participants = [facts.entity(f"C{index}", citation=citations[index]) for index in range(5)]
    events = [
        facts.event(
            "STAGE_ONE",
            facts.interval(index),
            citation=citations[index],
            participants=(participants[index % 5],),
        )
        for index in range(25)
    ]

    counted = (
        "evidence_record",
        "entity",
        "entity_attribute",
        "entity_evidence",
        "event",
        "event_entity",
        "event_changed_attribute",
        "event_metadata",
        "event_evidence",
        "confidence_vector",
        "confidence_component",
        "confidence_component_evidence",
    )

    def counts() -> dict[str, int]:
        with factory.connect() as connection, connection.cursor() as cursor:
            result = {}
            for table in counted:
                cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
                result[table] = cursor.fetchone()[0]
            return result

    writer.load_dataset(
        dataset_version=facts.DATASET_VERSION,
        ontology_hash=facts.ONTOLOGY_HASH,
        entities=iter(participants),
        events=iter(events),
        evidence_records=iter(citations),
    )
    via_bulk = counts()

    # Same artifacts, second database, through the row path.
    generator = persistence_support.migrated_database()
    row_factory = next(generator)
    try:
        persistence_support.register_dataset(
            row_factory, facts.DATASET_VERSION, facts.ONTOLOGY_HASH
        )
        row_repository = PostgresFactRepository(row_factory)
        row_repository.write_evidence_records(citations)
        row_repository.write_entities(participants, facts.ONTOLOGY_HASH)
        row_repository.write_events(events, facts.ONTOLOGY_HASH)
        with row_factory.connect() as connection, connection.cursor() as cursor:
            via_rows = {}
            for table in counted:
                cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608
                via_rows[table] = cursor.fetchone()[0]
    finally:
        for _ in generator:
            pass

    assert via_bulk == via_rows, (
        "The bulk path and the row path stored different things:\n"
        + "\n".join(
            f"  {table:<32} bulk {via_bulk[table]:>6}   rows {via_rows[table]:>6}"
            for table in counted
            if via_bulk[table] != via_rows[table]
        )
        + "\n\nA performance path that stores less than the correctness path makes the "
        "difference invisible at exactly the scale where it matters."
    )
    assert via_bulk["confidence_component_evidence"] > 0, (
        "Neither path stored the LAW-EVIDENCE hook, so comparing them proves nothing. "
        "The fixture must produce components that cite evidence."
    )


@pytest.mark.skipif(
    not DATASET_PATH.exists(),
    reason=(
        "datasets/raw/DataCoSupplyChainDataset.csv is absent. It is git-ignored and pinned "
        "by hash, never committed (datasets/README.md), so this check runs only where the "
        "file has been placed. The benchmark above does not need it."
    ),
)
def test_the_measured_shape_still_matches_the_real_file() -> None:
    """The synthetic fixture's shape is pinned to the real dataset, not to a memory.

    Without this, the constants above are a claim about a file nobody re-reads, and the
    benchmark slowly stops standing in for the thing it names. The file is latin-1, not
    UTF-8 -- it carries Spanish place names such as 'Rajastan' with an accented a -- and
    reading it as UTF-8 raises on the first one.
    """
    orders, customers, products = set(), set(), set()
    rows = 0
    with DATASET_PATH.open("r", encoding="latin-1", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            orders.add(row["Order Id"])
            customers.add(row["Customer Id"])
            products.add(row["Product Card Id"])

    assert rows == DATACO_ROWS, f"row count drifted: file has {rows}, fixture assumes {DATACO_ROWS}"
    assert len(orders) == DATACO_ORDERS
    assert len(customers) == DATACO_CUSTOMERS
    assert len(products) == DATACO_PRODUCTS
