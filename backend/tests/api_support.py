"""Shared fixtures for every suite that drives the HTTP surface.

A support module rather than a `conftest.py`, following `persistence_support.py` and
`extraction_harness.py`: the API fixtures are needed by `tests/api/` AND by
`tests/determinism/`, and a conftest is visible only below its own directory. Each of
those directories imports the fixtures it needs from here, so there is one definition
of the shared run rather than two that could drift apart.

One pipeline execution is run per session and shared. It takes several seconds -- module 9
is not a streaming module and the expansion is real work -- and every test here needs a
materialized run rather than a different one, so running it once is both faster and more
honest: the whole suite then describes ONE run, and two tests cannot disagree about it.

The dataset is synthetic. `CONVENTIONS.md` §14 asks for that by default, and here there is
no alternative: the DataCo source file is 95 MB and is not in the repository, so a suite
that depended on it would be a suite that only runs where somebody has downloaded it. The
real ontology pack, mapping and rule pack ARE used -- what is invented is only the rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from causalog.api.app import create_app
from causalog.core.ports.identity import Principal, Role
from causalog.ingestion.schema_mapper import load_mapping, mapping_hash
from causalog.ontology_runtime import load_pack
from causalog.orchestration.identity import SignedTokenAuthenticator, mint_token
from causalog.orchestration.jobs import new_execution_id, new_job_record, run_job
from causalog.orchestration.stages import PipelineRequest, PipelineState
from causalog.orchestration.wiring import Adapters
from causalog.persistence.memory.fakes import FixedClock

#: Long enough to satisfy the authenticator's floor, and obviously fake.
TEST_SECRET = "test-secret-that-is-long-enough-to-be-accepted"  # noqa: S105

#: Printed beside every measurement taken over the shared run, so a number is never read
#: as a measurement of the dataset. The committed bounded run is 150 rows of 180,519; this
#: is smaller still, and the gap is OQ-023's rather than any one test's.
SLICE_NOTICE = (
    "    NOTE: measured over a SYNTHETIC run of 40 rows. The committed bounded run is 150\n"
    "    rows of 180,519, so this is three orders of magnitude below the reference dataset\n"
    "    and is a measurement of an engine at this scale, not of the dataset (OQ-023)."
)

#: How many synthetic rows the shared run expands. Small enough that the suite stays quick,
#: large enough that module 9 proposes thousands of candidates and the empty-graph path is
#: exercised against real numbers rather than against zero.
ROWS = 40


def _synthetic_repository(root: Path) -> Path:
    """Build a repository-shaped directory: real packs, invented rows.

    The ontology, mapping and rule packs are symlinked from the repository rather than
    copied, so a pack edit is reflected here and this fixture cannot drift into testing a
    stale copy of the domain description.
    """
    repository = Path(__file__).resolve().parents[2]
    root.mkdir(parents=True, exist_ok=True)
    for name in ("ontology", "rule_engine"):
        link = root / name
        if not link.exists():
            link.symlink_to(repository / name, target_is_directory=True)

    pack = load_pack(repository / "ontology" / "packs" / "dataco" / "ontology.yaml")
    mapping = load_mapping(repository / "ontology" / "packs" / "dataco" / "mapping.yaml", pack.pack)
    pin_source = json.loads(
        (repository / "datasets" / "dataco.pin.json").read_text(encoding="utf-8")
    )["payload"]
    dataset_version = "dataco@synthetic0000000+map" + mapping_hash(mapping.mapping).split(":")[1]
    pin = dict(pin_source)
    pin["dataset_version"] = dataset_version
    pin["row_count"] = ROWS
    (root / "datasets").mkdir(exist_ok=True)
    (root / "datasets" / "dataco.pin.json").write_text(
        json.dumps(
            {"payload": pin, "schema_version": "1.0.0", "type": "DatasetPin"},
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    layer = root / "clean" / dataset_version
    layer.mkdir(parents=True, exist_ok=True)
    layer.joinpath("records.jsonl").write_text(_records(pin_source["header"]), encoding="utf-8")
    return root


def _records(header: list[str]) -> str:
    """Return a deterministic synthetic clean layer over the real column names.

    Deterministic by construction rather than by seeding: every value is a function of the
    row index. A seeded generator would be reproducible too, but only for as long as
    nobody changed the number of draws per row.
    """
    statuses = ("COMPLETE", "PENDING", "CLOSED")
    modes = ("Standard Class", "First Class", "Second Class")
    lines: list[str] = []
    for index in range(ROWS):
        values: dict[str, Any] = dict.fromkeys(header, "")
        values.update(
            {
                "Order Id": str(1000 + index // 2),
                "Order Item Id": str(5000 + index),
                "Order Customer Id": str(70 + (index % 7)),
                "Customer Id": str(70 + (index % 7)),
                "Order Status": statuses[index % 3],
                "Delivery Status": ("Shipping on time" if index % 2 else "Late delivery"),
                "Shipping Mode": modes[index % 3],
                "order date (DateOrders)": f"1/{1 + (index % 27)}/2017 10:{index % 60:02d}",
                "shipping date (DateOrders)": f"1/{2 + (index % 27)}/2017 11:{index % 60:02d}",
                "Days for shipping (real)": str(index % 6),
                "Days for shipment (scheduled)": "4",
                "Late_delivery_risk": str(index % 2),
                "Sales": f"{100 + index}.0",
                "Order Item Quantity": str(1 + index % 3),
                "Order Item Total": f"{90 + index}.0",
                "Order Profit Per Order": f"{index}.5",
                "Benefit per order": f"{index}.5",
                "Sales per customer": f"{100 + index}.0",
                "Product Card Id": str(300 + (index % 5)),
                "Order Item Cardprod Id": str(300 + (index % 5)),
                "Category Id": str(10 + (index % 4)),
                "Department Id": str(2 + (index % 3)),
                "Order Region": "Western Europe",
                "Market": "Europe",
            }
        )
        lines.append(
            json.dumps(
                {
                    "values": values,
                    "evidence_record_id": f"evd:{index:016d}",
                    "row_number": index + 1,
                },
                sort_keys=True,
            )
        )
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="session")
def clock() -> FixedClock:
    """A clock the suite controls. Time is a port so that this is possible (ADR-0014)."""
    return FixedClock()


@pytest.fixture(scope="session")
def executed_run(
    tmp_path_factory: pytest.TempPathFactory, clock: FixedClock
) -> tuple[PipelineState, str]:
    """Run the pipeline once and return its state and `run_id`."""
    root = _synthetic_repository(tmp_path_factory.mktemp("repository"))
    request = PipelineRequest(
        dataset_id="dataco",
        repository_root=root,
        rows=ROWS,
        seed=0,
        clean_layer_root=root / "clean",
        reports_root=root / "reports",
    )
    from causalog.persistence.memory.fakes import InMemoryJobStore

    store = InMemoryJobStore()
    execution_id = new_execution_id()
    store.create_job(
        new_job_record(
            execution_id=execution_id,
            dataset_id="dataco",
            requested_by="suite",
            correlation_id=None,
            idempotency_key=None,
            clock=clock,
        )
    )
    outcome = run_job(store=store, clock=clock, request=request, execution_id=execution_id)
    assert outcome.state.envelope is not None, (
        "The shared run produced no envelope, so every API test below would be testing "
        "the absent-run path instead of the path it names."
    )
    return outcome.state, outcome.state.envelope.run_id


@pytest.fixture
def adapters(clock: FixedClock) -> Adapters:
    """Fresh in-memory adapters per test, so audit entries never leak between tests."""
    return Adapters.in_memory(
        clock=clock,
        authenticator=SignedTokenAuthenticator(TEST_SECRET, clock),
        repository_root=Path(__file__).resolve().parents[2],
    )


@pytest.fixture
def client(
    adapters: Adapters, executed_run: tuple[PipelineState, str], clock: FixedClock
) -> Iterator[TestClient]:
    """A client over an app holding the shared run, with server exceptions surfaced as responses."""
    from causalog.orchestration.facade import EngineFacade

    facade = EngineFacade()
    facade.remember(executed_run[0], at=clock.now_utc())
    app = create_app(adapters=adapters, facade=facade)
    with TestClient(app, raise_server_exceptions=False) as started:
        yield started


@pytest.fixture
def run_id(executed_run: tuple[PipelineState, str]) -> str:
    """The shared run's identifier."""
    return executed_run[1]


@pytest.fixture
def token(clock: FixedClock) -> object:
    """Return a factory minting a bearer header for a role."""

    def make(role: Role, actor: str = "test-actor") -> dict[str, str]:
        principal = Principal(
            actor=actor,
            role=role,
            issued_at_epoch=0,
            expires_at_epoch=int(clock.now_utc().timestamp()) + 3600,
        )
        return {"Authorization": f"Bearer {mint_token(principal, secret=TEST_SECRET)}"}

    return make
