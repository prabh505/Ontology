"""What an act costs and what taking it risks -- read from a declaration, never derived.

This package's README carries one sentence that is not in any other module's: *"may never
infer a cost."* This file is where that stops being prose.

HOW THE TYPE ENFORCES IT
-------------------------
`CostBasis` and `RiskBasis` are closed two-member enums: `DECLARED_ASSUMED` and
`NOT_DECLARED`. There is no `DERIVED` member and no `ESTIMATED` member, so a future author
who computes a cost has nowhere to record that they did -- they must either add a member,
which is a reviewable change to a closed set, or lie in a field a law test reads. The
alternative design, a free-text `basis` string, would have made "inferred from the data" a
value somebody could pass on a Tuesday.

WHY THE ONLY DECLARED BASIS IS *ASSUMED*
-----------------------------------------
`ActionabilitySpec.provenance_class` is pinned to `ASSUMED` in the pack schema and the DSL
refuses any other value. R-15 records why: no observation in any dataset establishes what an
act costs an organisation, or what taking it risks. So a cost that IS declared is still
assumed, and the enum says so in its member name rather than in a footnote a renderer might
drop. Every recommendation prints its basis beside its cost, and it prints `ASSUMED` every
time a cost is present, because there is no other thing it could print.

THE ASYMMETRY BETWEEN COST AND RISK (ADR-0073)
------------------------------------------------
An actionable event type must declare a cost -- the pack schema refuses one that does not,
and `candidate.admissible_target` refuses it again, because an absent cost would rank a
candidate as FREE and place it above every candidate that declared honestly. An actionable
type MAY omit its operational risk. Absent risk is reported `NOT_DECLARED` and costs the
candidate its risk term in the scalarization; it is never read as `NEGLIGIBLE`. One absence
produces a wrong number and the other produces a true statement about the pack, which is why
they are treated differently.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.provenance import ProvenanceClass
from causalog.recommendation_engine.context import RecommendationContext, vocabulary_rank

__all__ = [
    "CostAssessment",
    "CostBasis",
    "RiskAssessment",
    "RiskBasis",
    "assess_cost",
    "assess_risk",
]


class CostBasis(str, Enum):
    """Where a cost figure came from. Closed at two members deliberately.

    See this module's docstring: the absence of a `DERIVED` member is the enforcement.
    """

    DECLARED_ASSUMED = "DECLARED_ASSUMED"
    """The pack declares a cost class. Its provenance is `ASSUMED` and can be nothing else."""

    NOT_DECLARED = "NOT_DECLARED"
    """The pack declares none. Reported; never replaced by a figure computed here."""


class RiskBasis(str, Enum):
    """Where an operational-risk figure came from. Closed at two members, as `CostBasis` is."""

    DECLARED_ASSUMED = "DECLARED_ASSUMED"
    """The pack declares a risk class (ADR-0073). `ASSUMED`, for the reason R-15 gives."""

    NOT_DECLARED = "NOT_DECLARED"
    """The pack declares none. The objective cannot run for this candidate and says so."""


class CostAssessment(BaseModel):
    """One candidate's implementation cost: the class, its rank, and where both came from.

    `rank` travels beside `class_id` because a consumer compares ranks and never reads a
    name -- so a pack may rename a class without changing any sequencing, and may not change
    a sequencing without changing a rank. `span` travels too, because a rank means nothing
    without the size of the vocabulary it was drawn from: rank 2 of 3 and rank 2 of 9 are
    completely different costs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    class_id: str | None = None
    rank: int | None = Field(default=None, ge=0)
    span: int = Field(ge=0)
    basis: CostBasis
    #: Always `ASSUMED` where a class is present. Carried explicitly so that a renderer
    #: cannot show a cost without its provenance, and LAW-PROVENANCE holds on this field.
    provenance_class: ProvenanceClass = ProvenanceClass.ASSUMED
    detail: str = Field(min_length=1)


class RiskAssessment(BaseModel):
    """One candidate's operational risk, on the same terms as its cost.

    The risk of TAKING the act, not the severity of the occurrence it acts on. Those are two
    vocabularies in the pack and they are never conflated here: a cheap act against a
    critical occurrence can be entirely safe to take.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    class_id: str | None = None
    rank: int | None = Field(default=None, ge=0)
    span: int = Field(ge=0)
    basis: RiskBasis
    provenance_class: ProvenanceClass = ProvenanceClass.ASSUMED
    detail: str = Field(min_length=1)


def assess_cost(class_id: str | None, context: RecommendationContext) -> CostAssessment:
    """Resolve a declared cost class to its rank, or report that none was declared."""
    span = len(context.cost_vocabulary)
    rank = vocabulary_rank(context.cost_vocabulary, class_id)
    if class_id is None or rank is None:
        return CostAssessment(
            span=span,
            basis=CostBasis.NOT_DECLARED,
            detail=(
                "the pack declares no cost class for this kind of occurrence. No cost is "
                "computed in its place: nothing in this system observes what an act costs, "
                "and a figure produced here would be an unfalsifiable judgement written "
                "into engine code."
            ),
        )
    return CostAssessment(
        class_id=class_id,
        rank=rank,
        span=span,
        basis=CostBasis.DECLARED_ASSUMED,
        detail=(
            f"declared '{class_id}', rank {rank} of a {span}-member vocabulary. Provenance "
            "is ASSUMED and can be nothing else: the pack schema pins it there, because no "
            "observation in any dataset establishes what an act costs (R-15)."
        ),
    )


def assess_risk(class_id: str | None, context: RecommendationContext) -> RiskAssessment:
    """Resolve a declared operational-risk class to its rank, or report that none was."""
    span = len(context.risk_vocabulary)
    rank = vocabulary_rank(context.risk_vocabulary, class_id)
    if class_id is None or rank is None:
        return RiskAssessment(
            span=span,
            basis=RiskBasis.NOT_DECLARED,
            detail=(
                "the pack declares no operational risk for this kind of occurrence "
                "(ADR-0073). This is NOT read as negligible risk. The objective cannot run "
                "for this candidate, and the scalarization charges it the whole risk weight "
                "rather than renormalizing the missing term away -- renormalizing would "
                "rank an undeclared candidate above one that declared a low risk honestly."
            ),
        )
    return RiskAssessment(
        class_id=class_id,
        rank=rank,
        span=span,
        basis=RiskBasis.DECLARED_ASSUMED,
        detail=(
            f"declared '{class_id}', rank {rank} of a {span}-member vocabulary. This is the "
            "risk of TAKING the act, not the severity of the occurrence acted on; the pack "
            "declares those as two vocabularies and this engine never conflates them. "
            "Provenance is ASSUMED, for the reason R-15 and R-25 both give."
        ),
    )
