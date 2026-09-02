"""Module 3's stated failure modes, one test each (`CONVENTIONS.md` §3)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pytest

from causalog.core.errors import DataQualityError
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import Precision
from causalog.core.types.entity import Entity
from causalog.extraction.entity_extractor import ConflictPolicy, ExtractionResult
from extraction_harness import Harness, build_batches, envelope_for, harness_for
from fixtures.dataco.expansion import GROUND_TRUTH_DATASET_VERSION, rows


@pytest.fixture(scope="module")
def harness():
    return harness_for()


def _run(
    harness: Harness,
    raw_rows: Iterable[Mapping[str, str]],
    policy: ConflictPolicy = ConflictPolicy.FIRST_WINS,
) -> ExtractionResult:
    batches = build_batches(raw_rows, harness, GROUND_TRUTH_DATASET_VERSION)
    envelope = envelope_for(harness, GROUND_TRUTH_DATASET_VERSION)
    return harness.extract(batches, envelope, policy=policy)


def test_a_natural_key_composes_its_columns_in_declared_sequence(harness: Harness) -> None:
    """A composite key is the declared columns, separated, never concatenated.

    `MARKET_REGION` is keyed on two columns. Joining them without a separator would make
    `("AB", "C")` and `("A", "BC")` one participant, which content addressing exists to
    make impossible.
    """
    result = _run(harness, rows())
    regions = [item for item in result.entities if item.entity_type == "MARKET_REGION"]
    assert len(regions) == 1
    assert regions[0].natural_key == "Pacific Asia,Southeast Asia"
    assert regions[0].entity_id == Entity.address(
        harness.ontology_hash,
        "MARKET_REGION",
        "Pacific Asia,Southeast Asia",
    )


def test_identity_is_the_content_address_and_repeats_merge(harness: Harness) -> None:
    """Twenty records naming one region produce one entity, not twenty."""
    result = _run(harness, rows())
    per_type = {item.entity_type: 0 for item in result.entities}
    for item in result.entities:
        per_type[item.entity_type] += 1
    assert per_type["MARKET_REGION"] == 1
    tally = next(
        item for item in result.report.per_entity_type if item.entity_type == "MARKET_REGION"
    )
    assert tally.records_observed == 20
    assert tally.records_merged == 19


def test_an_entity_carries_the_declared_lifecycle_as_assumed_configuration(
    harness: Harness,
) -> None:
    result = _run(harness, rows())
    order = next(item for item in result.entities if item.entity_type == "ORDER")
    assert order.lifecycle.provenance_class is ProvenanceClass.ASSUMED
    assert "PENDING" in order.lifecycle.state_names
    assert list(order.lifecycle.state_names) == sorted(order.lifecycle.state_names)
    assert ("PENDING", "PENDING_PAYMENT") in order.lifecycle.legal_transitions


def test_an_entity_type_with_no_declared_lifecycle_still_gets_one(harness: Harness) -> None:
    """`Lifecycle` refuses empty `state_names`, so a type without one gets a single state.

    A lifecycle admitting everything would be indistinguishable from one nobody wrote.
    """
    result = _run(harness, rows())
    product = next(item for item in result.entities if item.entity_type == "PRODUCT")
    assert product.lifecycle.state_names == ("PRODUCT",)
    assert product.lifecycle.legal_transitions == ()


def test_every_entity_is_observed(harness: Harness) -> None:
    """`docs/architecture.md` §2: an entity the engine inferred is not an entity."""
    result = _run(harness, rows())
    assert {item.provenance_class for item in result.entities} == {ProvenanceClass.OBSERVED}


@pytest.mark.parametrize(
    ("policy", "expected"),
    [(ConflictPolicy.FIRST_WINS, "PR"), (ConflictPolicy.LAST_WINS, "NY")],
)
def test_each_conflict_policy_keeps_the_value_it_names(
    harness: Harness, policy: ConflictPolicy, expected: str
) -> None:
    result = _run(harness, rows(), policy=policy)
    customer = next(
        item
        for item in result.entities
        if item.entity_type == "CUSTOMER" and item.natural_key == "502"
    )
    assert dict(customer.attributes)["customer_state"] == expected


def test_reject_refuses_a_disagreement_outright(harness: Harness) -> None:
    with pytest.raises(DataQualityError, match="does not identify"):
        _run(harness, rows(), policy=ConflictPolicy.REJECT)


def test_a_conflict_is_reported_under_every_policy_that_tolerates_one(harness: Harness) -> None:
    """The policy decides which value is kept, never whether the disagreement is visible."""
    for policy in (ConflictPolicy.FIRST_WINS, ConflictPolicy.LAST_WINS):
        result = _run(harness, rows(), policy=policy)
        assert result.report.conflicts_total == 1
        assert result.report.conflicts[0].policy is policy


def test_a_composite_key_missing_any_part_yields_no_entity_and_is_counted(harness: Harness) -> None:
    """Absence of a key is not an error: a source references participants it never describes.

    `MARKET_REGION` is keyed on two columns, and one of them is blanked here. A partial key
    must yield NO entity rather than one identified by the half that survived, which would
    merge every record sharing that half into one participant. (Module 1 would quarantine
    these rows before they reached module 3; this asserts what module 3 does if one ever
    arrives, which is the failure mode `docs/architecture.md` §2 names.)
    """
    blanked = []
    for record in rows():
        copy = dict(record)
        copy["Order Region"] = ""
        blanked.append(copy)
    result = _run(harness, blanked)
    assert not [item for item in result.entities if item.entity_type == "MARKET_REGION"]
    region = next(
        item for item in result.report.per_entity_type if item.entity_type == "MARKET_REGION"
    )
    assert region.records_without_key == 20
    assert region.entities_created == 0


def test_attribute_history_records_a_version_only_where_the_value_changed(harness: Harness) -> None:
    """A record that repeated what was already known introduces nothing and adds no version."""
    result = _run(harness, rows())
    customer = next(
        item
        for item in result.entities
        if item.entity_type == "CUSTOMER" and item.natural_key == "502"
    )
    history = next(item for item in result.histories if item.entity_id == customer.entity_id)
    assert history.changed_attributes == ("customer_state",)
    versions = history.versions_of("customer_state")
    assert [item.value for item in versions] == ["PR", "PR"]
    assert [item.superseded for item in versions] == [True, False]
    # A customer named by two records has one version of every attribute that agreed.
    assert len(history.versions_of("customer_city")) == 1


def test_an_attribute_version_is_dated_by_the_declared_observed_at(harness: Harness) -> None:
    result = _run(harness, rows())
    order = next(
        item for item in result.entities if item.entity_type == "ORDER" and item.natural_key == "1"
    )
    history = next(item for item in result.histories if item.entity_id == order.entity_id)
    version = history.versions_of("order_status")[0]
    assert version.observed_at.precision is Precision.MINUTE
    assert version.observed_at.t_earliest.isoformat() == "2018-01-01T09:00:00+00:00"


def test_the_entity_address_excludes_attributes_so_enrichment_cannot_rename(
    harness: Harness,
) -> None:
    """`docs/contracts.md` §5: identity is what a participant IS, not what is recorded of it."""
    first = _run(harness, rows(), policy=ConflictPolicy.FIRST_WINS)
    last = _run(harness, rows(), policy=ConflictPolicy.LAST_WINS)
    assert (
        first.entity_ids() == last.entity_ids()
    ), "two policies resolved one attribute differently and must still name one participant"


def test_the_report_reconciles_created_plus_merged_against_records_observed(
    harness: Harness,
) -> None:
    result = _run(harness, rows())
    for item in result.report.per_entity_type:
        assert item.entities_created + item.records_merged == item.records_observed
