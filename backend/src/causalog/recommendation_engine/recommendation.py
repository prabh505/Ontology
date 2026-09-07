"""What an operator is told to do, and the guarantees that hold before it can be said.

prd.md Principle 5 is the whole of this file: a recommendation without its expected benefit,
its cost, its confidence, its supporting evidence and its assumptions **must not be shown**.
The obvious implementation is a check somewhere in the pipeline. This file does it with the
type instead, because a check has a call site and a call site can be skipped, refactored
past, or reached by a second path that nobody added the check to.

WHAT THE TYPE MAKES UNCONSTRUCTIBLE (ADR-0075)
-----------------------------------------------
* `evidence_item_ids` and `assumptions` both carry `min_length=1`. A `Recommendation` with
  no evidence or no assumptions **cannot be instantiated at all** -- not "is filtered out
  later". This is `SimulatedWorld.interventions`' `min_length=1` precedent, which made "a
  hypothetical with nothing hypothetical about it" unrepresentable rather than invalid.
* `confidence` is a `ConfidenceVector` with no default. LAW-EVIDENCE says a bare float is a
  defect, and `check_confidence_is_a_vector.py` enforces it; here there is additionally no
  value the field could take that is not a decomposed vector.
* `expected_benefit` is a `BenefitRange`, which is itself either fully populated or an
  explicit stated absence -- so "benefit present" and "benefit absent with a reason" are the
  only two states, and there is no third state where a figure appears without its standing.
* `implementation_cost` and `operational_risk` carry a `basis` from a two-member enum with
  no `DERIVED` member. See `cost.py`.
* `justification` is `min_length=1`. prd.md §32 asks for one line an operator can act on;
  an empty string would satisfy a nullable field and satisfy nobody reading the artifact.

`ProvenanceClass` is pinned to `SIMULATED` and a validator refuses anything else.
`SIMULATED` is the weakest member of `WEAKEST_FIRST`, which makes containment arithmetic:
a recommendation rests on a simulated benefit, so it is simulated, and it cannot launder
itself into an inference on the way to a screen.

THE WITHHELD LEDGER IS OF EQUAL STANDING
------------------------------------------
A candidate below the pack's `minimum_confidence_to_publish` becomes a
`WithheldRecommendation` rather than a low-scoring entry. A ranked list is read as a list of
things to do, and position in it outweighs any number printed beside it -- so the floor is a
GATE, not a term (module 10's ruling on gated components, one layer up). The ledger is
published with the list, because "nine candidates were withheld for want of belief" is a
finding about this dataset and is invisible in a list of one.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import ConfidenceVector
from causalog.counterfactual_engine import Assumption
from causalog.recommendation_engine.candidate import CandidateSource
from causalog.recommendation_engine.cost import CostAssessment, RiskAssessment
from causalog.recommendation_engine.cutset import SearchRegime
from causalog.recommendation_engine.estimate import BenefitRange
from causalog.recommendation_engine.portfolio import PortfolioBenefit

__all__ = ["Recommendation", "WithheldRecommendation", "WithholdingReason"]


class Recommendation(BaseModel):
    """One act, or one indivisible set of acts, an operator could be asked to take.

    prd.md §32's six fields and §50's seven are all present, under names that carry no
    domain vocabulary. §50's count of affected process subjects is `affected_instance_count`;
    its affected economic quantity is `affected_magnitude` under a NAMED measurement; and its
    estimated reduction is `expected_benefit`, in that measurement's own declared unit.

    §50's "impact score" is `desirability`, and it is deliberately not called a score: it is
    one traversal of a trade-off surface under one declared weighting, and the frontier
    membership beside it is what says whether anything actually beats this.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    #: Which graph this was derived over. A recommendation off an unpromoted graph is
    #: disowned by every artifact that carries it (ADR-0072).
    standing: str = Field(min_length=1)

    # -- prd.md §32: Node -------------------------------------------------------------
    #: Sorted, unique, at least one. A set is represented here rather than in a second type.
    node_event_ids: tuple[str, ...] = Field(min_length=1)
    node_event_types: tuple[str, ...] = Field(min_length=1)
    #: True when more than one node must be acted on together.
    is_set: bool = False
    #: Required whenever `is_set`. What makes the members indivisible.
    is_set_because: str | None = None
    #: Which generator(s) proposed this, so a reader can weigh it by origin.
    sources: tuple[CandidateSource, ...] = Field(min_length=1)
    description: str = Field(min_length=1)

    # -- prd.md §32: Expected Benefit / Expected Delay Reduction -----------------------
    expected_benefit: BenefitRange
    #: Present only for a multi-node recommendation: the joint figure against the naive sum.
    portfolio: PortfolioBenefit | None = None

    # -- prd.md §32: Estimated Cost, and §50: Operational Risk -------------------------
    implementation_cost: CostAssessment
    operational_risk: RiskAssessment

    # -- prd.md §32: Confidence, and LAW-EVIDENCE --------------------------------------
    confidence: ConfidenceVector

    # -- prd.md §32's affected events, and §50's affected subjects and economic total --
    affected_event_ids: tuple[str, ...] = ()
    affected_instance_count: int = Field(default=0, ge=0)
    #: The apportioned share of the observed whole this act sits upstream of, with the unit
    #: of the measurement it was read under. §50's "affected revenue" wherever the pack
    #: declares a measurement of that kind; absent otherwise, and never substituted for.
    affected_magnitude: float | None = None
    affected_magnitude_unit: str | None = None
    #: prd.md §32's "Propagation Reduced 82%" figure. `None` rather than zero when the whole
    #: is unmeasurable: a proportion of an unmeasured whole is not a proportion.
    affected_share: float | None = None

    # -- prd.md §50: Impact Score, and the frontier that qualifies it ------------------
    desirability: float | None = None
    #: Names the `core.scalarization` function that produced it, so a reader can recompute.
    scalarization: str | None = None
    #: The weights it was produced under, sorted. Carried on the artifact rather than only
    #: in the pack, so a ranking can never be read under a weighting that did not make it.
    objective_weights: tuple[tuple[str, float], ...] = ()
    #: True when nothing in this run's candidate set dominates this one on all four
    #: objectives. A stronger statement than a high desirability, and independent of weights.
    on_pareto_frontier: bool = False
    #: Set when the frontier could not judge it -- an unmeasured objective (`core
    #: .scalarization.pareto_front_v1` excludes such points rather than ranking them worst).
    frontier_absent_because: str | None = None

    # -- The cut-set claim -------------------------------------------------------------
    chains_broken: int = Field(default=0, ge=0)
    chains_considered: int = Field(default=0, ge=0)
    search_regime: SearchRegime = SearchRegime.EXACT
    not_minimal_because: str | None = None

    # -- LAW-EVIDENCE and Principle 5 --------------------------------------------------
    #: At least one. See this module's docstring: unconstructible without.
    evidence_item_ids: tuple[str, ...] = Field(min_length=1)
    #: At least one. Each carries `why_needed` and `falsified_by`, so none is a disclaimer.
    assumptions: tuple[Assumption, ...] = Field(min_length=1)
    #: Free-text hazards a reader should weigh that are not the declared operational risk --
    #: an extrapolated figure, a truncated sweep, a disowned graph. Sorted.
    risks: tuple[str, ...] = ()
    justification: str = Field(min_length=1)

    provenance_class: ProvenanceClass = ProvenanceClass.SIMULATED

    @model_validator(mode="after")
    def _check_invariants(self) -> Recommendation:
        """Enforce the guarantees a field declaration alone cannot express."""
        if self.provenance_class is not ProvenanceClass.SIMULATED:
            raise ContractViolationError(
                f"Recommendation carries provenance {self.provenance_class.value}. A "
                "recommendation rests on a simulated benefit and is SIMULATED; anything "
                "stronger would let a hypothetical launder itself into an inference on the "
                "way to a screen (LAW-PROVENANCE)."
            )
        nodes = list(self.node_event_ids)
        if nodes != sorted(set(nodes)):
            raise ContractViolationError(
                "Recommendation.node_event_ids is unsorted or repeats a node; two runs over "
                "one input must produce byte-identical artifacts (CONVENTIONS.md §11)."
            )
        if self.is_set != (len(nodes) > 1):
            raise ContractViolationError(
                f"Recommendation names {len(nodes)} node(s) with is_set={self.is_set}. The "
                "flag is what an operator reads to know whether partial execution buys "
                "anything, so it may not disagree with the membership beside it."
            )
        if self.is_set and not self.is_set_because:
            raise ContractViolationError(
                "Recommendation is a set and says nothing about why its members are "
                "indivisible. An operator shown three acts with no such statement will "
                "reasonably do one of them, and a partial execution of a joint cause buys "
                "nothing rather than buying a proportion (ADR-0069)."
            )
        if self.search_regime is not SearchRegime.EXACT and not self.not_minimal_because:
            raise ContractViolationError(
                f"Recommendation was found under {self.search_regime.value} and does not "
                "say what stopped its minimality being established. 'Minimal' is a claim, "
                "and an unproved claim must be labelled as one (ADR-0076)."
            )
        if self.affected_share is not None and self.affected_magnitude is None:
            raise ContractViolationError(
                "Recommendation carries a share of a whole it does not carry. A proportion "
                "of an unmeasured total is not a proportion."
            )
        return self

    def sort_key(self) -> tuple[float, int, str]:
        """Canonical sequence: most desirable first, then most chains broken, then by id.

        An absent desirability sorts LAST rather than at zero. A candidate whose benefit was
        never measured ranks nowhere, and placing it at zero would put it below candidates
        that were measured and found small -- a different claim (`core.ranking.Ranker`).
        """
        return (
            -(self.desirability if self.desirability is not None else -1.0),
            -self.chains_broken,
            self.recommendation_id,
        )


class WithholdingReason(str, Enum):
    """Why a candidate that survived the actionability gate was still not published."""

    BELOW_CONFIDENCE_FLOOR = "BELOW_CONFIDENCE_FLOOR"
    """Below the pack's declared `minimum_confidence_to_publish`. A gate, not a term."""

    BENEFIT_NOT_MEASURABLE = "BENEFIT_NOT_MEASURABLE"
    """No figure could be produced, or an EXTRAPOLATION verdict replaced it (ADR-0070)."""

    NO_ASSUMPTIONS_ENUMERATED = "NO_ASSUMPTIONS_ENUMERATED"
    """Module 13 enumerated none, so Principle 5 cannot be satisfied. Should not occur."""

    NO_EVIDENCE = "NO_EVIDENCE"
    """No evidence record supports the claim. Principle 5 refuses it."""

    BEYOND_PUBLICATION_LIMIT = "BEYOND_PUBLICATION_LIMIT"
    """Ranked below the pack's `maximum_recommendations`. Withheld, not rejected."""

    POLICY_NOT_DECLARED = "POLICY_NOT_DECLARED"
    """The pack declares no floor, no weights or no scalarizer, so nothing could rank."""


class WithheldRecommendation(BaseModel):
    """A candidate that could have been published and was not, with what withheld it.

    Published alongside the ranked list and of equal standing to it (ADR-0055's
    rejection-ledger pattern). What was nearly recommended, and why it was not, is
    frequently a sharper statement about a dataset than what was.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_event_ids: tuple[str, ...] = Field(min_length=1)
    node_event_types: tuple[str, ...] = Field(min_length=1)
    reason: WithholdingReason
    #: The declaration or threshold this was measured against, named so it can be acted on.
    checked_against: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    #: The derived scalar of the candidate's vector, where one exists, so a reader can see
    #: how far below the floor it fell. Named `belief_scalar` rather than borrowing the word
    #: LAW-EVIDENCE reserves for the decomposed vector itself.
    belief_scalar: float | None = None
    #: What was measured before the candidate was withheld, carried so the ledger is
    #: INSPECTABLE rather than merely enumerated. A reader deciding whether a threshold is
    #: set correctly needs to see what it excluded, and "202 candidates fell below the floor"
    #: answers none of that. These are `None` only where the withholding happened before the
    #: figure existed -- a benefit that could not be measured has no range to show.
    #:
    #: This does NOT make a withheld entry a recommendation. It carries no confidence vector,
    #: no evidence chain, no assumptions and no justification, so it cannot be rendered as
    #: one or mistaken for one; `Recommendation`'s own `min_length=1` fields are what draw
    #: that line and they are absent here deliberately.
    expected_benefit: BenefitRange | None = None
    implementation_cost: CostAssessment | None = None
    operational_risk: RiskAssessment | None = None
    #: Which generator(s) proposed it, so a withheld entry can be weighed by origin too.
    sources: tuple[CandidateSource, ...] = ()
    #: Coverage, where a cut-set search measured it. A candidate withheld for want of belief
    #: may still be the one that breaks the most chains, and that is worth seeing.
    chains_broken: int = Field(default=0, ge=0)
    chains_considered: int = Field(default=0, ge=0)

    def sort_key(self) -> tuple[str, str]:
        """Canonical sequence: by reason, then by membership."""
        return (self.reason.value, ",".join(self.node_event_ids))
