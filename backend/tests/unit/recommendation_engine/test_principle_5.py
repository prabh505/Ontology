"""prd.md Principle 5, asserted as unconstructibility rather than as filtering.

"No recommendation without confidence, evidence and assumptions. Enforce at the type level
so it cannot be bypassed." A test that built a bad recommendation and checked it was
filtered out would prove the filter works on the path it was tested on. These tests prove
the object cannot exist, on every path there will ever be.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import ConfidenceVector
from causalog.core.types.confidence import ConfidenceComponent
from causalog.counterfactual_engine import Assumption
from causalog.recommendation_engine import (
    BenefitRange,
    CostAssessment,
    CostBasis,
    Recommendation,
    RiskAssessment,
    RiskBasis,
)


def _belief() -> ConfidenceVector:
    """Return a minimal decomposed vector. LAW-EVIDENCE admits nothing simpler."""
    return ConfidenceVector(
        components=(
            ConfidenceComponent(
                component_name="simulated_chain_belief",
                value=0.8,
                provenance_class=ProvenanceClass.SIMULATED,
                evidence_record_ids=("evd:fixture",),
            ),
        ),
        scalar=0.8,
        aggregation="minimum_v1",
        provenance_class=ProvenanceClass.SIMULATED,
    )


def _fields(**overrides: object) -> dict[str, object]:
    """Return a constructible recommendation's fields, with named parts replaced."""
    base: dict[str, object] = {
        "recommendation_id": "rec:fixture",
        "run_id": "run:fixture",
        "standing": "STATED",
        "node_event_ids": ("evt:a",),
        "node_event_types": ("STAGE_ORIGIN",),
        "sources": ("HIGH_LEVERAGE",),
        "description": "act on the occurrence",
        "expected_benefit": BenefitRange(absent_because="nothing measurable here"),
        "implementation_cost": CostAssessment(
            class_id="LOW", rank=1, span=3, basis=CostBasis.DECLARED_ASSUMED, detail="d"
        ),
        "operational_risk": RiskAssessment(span=4, basis=RiskBasis.NOT_DECLARED, detail="d"),
        "confidence": _belief(),
        "evidence_item_ids": ("evd:fixture",),
        "assumptions": (
            Assumption(
                name="apportioned_share",
                statement="the share is an apportionment",
                why_needed="the benefit rests on it",
                falsified_by="a measured share",
            ),
        ),
        "justification": "one line an operator can act on",
    }
    base.update(overrides)
    return base


def test_a_recommendation_without_evidence_cannot_be_constructed() -> None:
    """Not filtered later. Refused by the type, on every path."""
    with pytest.raises(ValidationError):
        Recommendation(**_fields(evidence_item_ids=()))  # type: ignore[arg-type]


def test_a_recommendation_without_assumptions_cannot_be_constructed() -> None:
    """The task's assumption-tracking completeness requirement, at the type level."""
    with pytest.raises(ValidationError):
        Recommendation(**_fields(assumptions=()))  # type: ignore[arg-type]


def test_a_recommendation_requires_a_decomposed_confidence_vector() -> None:
    """LAW-EVIDENCE: a bare float is a defect, and here it is not even a valid value."""
    with pytest.raises(ValidationError):
        Recommendation(**_fields(confidence=0.8))  # type: ignore[arg-type]


def test_a_recommendation_cannot_claim_a_provenance_stronger_than_simulated() -> None:
    """A hypothetical must not launder itself into an inference on the way to a screen."""
    with pytest.raises(ContractViolationError):
        Recommendation(**_fields(provenance_class=ProvenanceClass.INFERRED))


def test_a_multi_node_recommendation_must_say_why_its_members_are_indivisible() -> None:
    """An operator shown three acts with no such statement will do one of them."""
    with pytest.raises(ContractViolationError):
        Recommendation(
            **_fields(
                node_event_ids=("evt:a", "evt:b"),
                node_event_types=("STAGE_ORIGIN",),
                is_set=True,
            )
        )


def test_the_set_flag_may_not_disagree_with_the_membership_beside_it() -> None:
    """The flag is what an operator reads to know whether partial execution buys anything."""
    with pytest.raises(ContractViolationError):
        Recommendation(
            **_fields(node_event_ids=("evt:a", "evt:b"), node_event_types=("T",), is_set=False)
        )


def test_a_fully_supported_recommendation_constructs() -> None:
    """The positive case, so the tests above are proving refusal and not a broken fixture."""
    entry = Recommendation(**_fields())

    assert entry.provenance_class is ProvenanceClass.SIMULATED
    assert entry.assumptions[0].falsified_by
    assert entry.evidence_item_ids == ("evd:fixture",)


def test_a_benefit_range_is_either_populated_or_an_explicit_absence() -> None:
    """No third state where a figure appears without its standing."""
    with pytest.raises(ContractViolationError):
        BenefitRange(low=1.0)
    with pytest.raises(ContractViolationError):
        BenefitRange(low=1.0, high=2.0, unit="DAYS", absent_because="both at once")


def test_a_zero_width_range_must_say_why_its_width_is_zero() -> None:
    """ADR-0075: a collapsed range is a point estimate wearing a range's shape.

    A reader must be able to tell a genuinely exact figure -- an elimination -- from a
    sweep that never ran.
    """
    with pytest.raises(ContractViolationError):
        BenefitRange(low=5.0, high=5.0, unit="DAYS")

    allowed = BenefitRange(
        low=5.0, high=5.0, unit="DAYS", degenerate_because="the consequence is eliminated"
    )
    assert allowed.degenerate_because is not None


def test_no_cost_or_risk_basis_admits_a_derived_value() -> None:
    """The README's "may never infer a cost", as an absence in a closed set.

    An author who computes a cost has nowhere to record that they did. Adding a member is a
    reviewable change to a closed enum; the alternative -- a free-text basis -- would have
    made "inferred from the data" a value somebody could pass on a Tuesday.
    """
    assert {member.value for member in CostBasis} == {"DECLARED_ASSUMED", "NOT_DECLARED"}
    assert {member.value for member in RiskBasis} == {"DECLARED_ASSUMED", "NOT_DECLARED"}
