"""What an act is worth, obtained by asking module 13 and never by working it out here.

ADR-0074. Module 13 already simulates a hypothetical, validates its premise against the
ontology, propagates it correctly per edge kind, and assesses how far the answer can be
believed. A second estimator in this package would be a second opinion about the same
question, and the two would agree on the day they were written and on no day after that.

So: this module BUILDS a typed intervention, HANDS it to `counterfactual_engine.simulate`,
and READS the result. It performs no arithmetic on a returned magnitude. That is asserted
two ways -- structurally, by a law test that finds `simulate` imported and finds no second
estimator; and numerically, by a consistency test that poses one hypothetical through both
modules and requires the same figure out of each.

THE HEADLINE FIGURE IS MODULE 13'S OWN
----------------------------------------
`_headline` selects the same delta module 13's sensitivity sweep selects, by the same key.
It is duplicated rather than imported because it is a private detail of that module, and
the duplication is held honest by the consistency test rather than by comment: if module 13
changes what it calls the headline, the test that compares the two figures fails.

TWO QUANTITIES, NAMED SEPARATELY, NEVER BLENDED
------------------------------------------------
* **Benefit** is what the hypothetical is worth: module 13's headline difference, published
  as a RANGE. It answers "how much better would this have been".
* **Attributed consequence** is what the node transmits into: module 12's
  `prevented_by_removing`, under the pack's declared combination operator. It answers "how
  much of the whole is downstream of this node".

They are close relatives and they are not the same number -- one is a simulated difference,
the other an apportioned share of an observed total -- so they occupy separate fields with
separate units and nothing here adds them. ADR-0008's never-blend ruling, two levels down.

WHY BENEFIT IS A RANGE AND NEVER A POINT (ADR-0075)
----------------------------------------------------
R-23: a simulated figure is MORE persuasive than an inferred one because it is concrete, and
prd.md §52's own example prints "approximately 11 hours". A single number in a unit invites
a trust the inputs cannot support. The low and high come from module 13's declared
sensitivity sweep -- perturbing the apportioned share, which is the one input most likely to
be wrong -- so the width of the range is a property of the pack's declared assumptions
rather than a decoration. Where the sweep could not run, the range is ABSENT and says why;
it is never published as a point pretending to be a range by setting low equal to high.

An `EXTRAPOLATION` verdict REPLACES the figure rather than sitting beside it (ADR-0070). A
number a reader can copy will be copied, and a warning above a table does not survive a
screenshot.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.propagation_analyzer import (
    PreventedConsequence,
    prevented_by_removing,
    share_of_whole,
)
from causalog.core.errors import ContractViolationError
from causalog.core.run import OutputEnvelope
from causalog.counterfactual_engine import (
    Assumption,
    EventDelta,
    Intervention,
    RemoveEvent,
    SimulationResult,
    ValidityVerdict,
    simulate,
)
from causalog.recommendation_engine.context import RecommendationContext

__all__ = [
    "BenefitEstimate",
    "BenefitRange",
    "estimate",
    "intervention_for",
]


class BenefitRange(BaseModel):
    """What the hypothetical is worth, as a bounded range or as a stated absence.

    Exactly one of two states, enforced by a validator rather than by documentation: either
    `low` and `high` and `unit` are all present, or `absent_because` is. A range half filled
    in is the shape that renders as a number in one template and as blank in another.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    low: float | None = None
    high: float | None = None
    #: The figure the sweep departed from, carried so a reader can see where in its own
    #: range the unperturbed answer sits. It is NOT the answer; the range is the answer.
    point_of_departure: float | None = None
    unit: str | None = None
    #: The occurrence whose difference is the headline, so the range is traceable to a node.
    headline_event_id: str | None = None
    #: Which perturbations produced the bounds, sorted. A range whose width nobody can
    #: attribute to a declared assumption is a decoration.
    perturbations: tuple[float, ...] = ()
    #: Set when `low` equals `high` because the consequence is ELIMINATED rather than
    #: reduced. See `_range_from`: there is no apportioned share to perturb, so the width is
    #: genuinely zero and the uncertainty lives entirely in whether the elimination happens
    #: -- which the confidence vector carries, not this range. Publishing the figure with
    #: this sentence attached is honest; publishing it bare would be the false precision
    #: ADR-0075 forbids.
    degenerate_because: str | None = None
    absent_because: str | None = None

    @model_validator(mode="after")
    def _check_one_state(self) -> BenefitRange:
        """Refuse a range that is neither a range nor a stated absence."""
        populated = self.low is not None and self.high is not None and self.unit is not None
        if populated == (self.absent_because is not None):
            raise ContractViolationError(
                "BenefitRange must be either fully populated or absent with a reason, and "
                "is currently both or neither. A half-filled range renders as a figure in "
                "one template and as a blank in another, and prd.md Principle 5 forbids "
                "showing a benefit whose standing a reader cannot see."
            )
        if populated and self.low is not None and self.high is not None:
            if self.low > self.high:
                raise ContractViolationError(
                    f"BenefitRange has low {self.low} above high {self.high}."
                )
            if self.low == self.high and self.degenerate_because is None:
                raise ContractViolationError(
                    "BenefitRange has equal bounds and does not say why its width is zero. "
                    "A range that collapsed silently is a point estimate wearing a range's "
                    "shape, which is exactly what ADR-0075 forbids: a reader cannot tell a "
                    "genuinely exact figure -- an elimination -- from a sweep that never ran."
                )
        if self.degenerate_because is not None and self.low != self.high:
            raise ContractViolationError("BenefitRange explains a zero width it does not have.")
        return self


class BenefitEstimate(BaseModel):
    """One act's worth, its downstream scope, and everything qualifying both.

    Every field on this type came out of module 12 or module 13. Nothing on it was computed
    here, which is what ADR-0074 requires and what the consistency test checks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_event_ids: tuple[str, ...] = Field(min_length=1)
    benefit: BenefitRange
    #: Module 12's apportioned share of the observed whole. A DIFFERENT quantity from
    #: `benefit`; see this module's docstring. `None` where nothing could be attributed.
    attributed_consequence: float | None = None
    attributed_unit: str | None = None
    attributed_share: float | None = None
    attributed_absent_because: str | None = None
    #: prd.md §32's affected-events measure, and §50's count of affected process subjects,
    #: expressed without either domain word: the consequences the act reaches, and the
    #: process instances they sit in.
    affected_event_ids: tuple[str, ...] = ()
    affected_instance_count: int = Field(default=0, ge=0)
    #: Module 13's verdict on how far the figure can be believed. `EXTRAPOLATION` means the
    #: range above is ABSENT rather than qualified.
    verdict: ValidityVerdict
    #: How many support envelopes module 13 actually built. ZERO carries a specific meaning
    #: that the verdict alone cannot: a removal has no continuous quantity to place inside or
    #: outside a witnessed range, so no envelope is ATTEMPTED and the resulting
    #: `NOT_ASSESSABLE` says "this question does not apply", not "this change is unsupported".
    #: An envelope that WAS built and returned `NOT_ASSESSABLE` is the second thing, and the
    #: two must not score alike -- see `rank.confidence_of`.
    support_envelope_count: int = Field(default=0, ge=0)
    #: Module 13's composed belief along the simulated chain, and the named function that
    #: composed it. `None` where no chain carried one.
    composed_belief: float | None = None
    composition: str | None = None
    #: Module 13's enumerated assumptions, carried whole. Each has a `falsified_by`, so none
    #: of them is a disclaimer.
    assumptions: tuple[Assumption, ...] = ()
    #: Every change module 13 refused, so a candidate that could not be simulated says why.
    rejected_detail: tuple[str, ...] = ()


def intervention_for(target_event_ids: tuple[str, ...], rationale: str) -> tuple[Intervention, ...]:
    """Build the typed removals that ask "what if these had not happened".

    `RemoveEvent` is the only kind this module proposes, and the restriction is deliberate
    rather than a stub. The other four kinds -- shifting an instant, inserting a step,
    changing an attribute, changing a participant's state -- all need a VALUE, and a value
    is a domain judgement: how much earlier, to what, from which state. Nothing in this
    engine can supply one, and a module that guessed would be inventing the premise of its
    own recommendation. A caller who knows the value poses that hypothetical through module
    13 directly, which is exactly what `scripts/simulate_counterfactuals.py` does.

    Removal needs no value. It asks the one question this graph can answer on its own.
    """
    # `Intervention.of` rather than the constructor: module 13 content-addresses a change,
    # so two runs proposing the same removal produce the same identifier and a rerun can
    # tell one change from another. An identifier chosen here would not follow from the
    # content, and module 13 refuses it -- correctly.
    return tuple(
        Intervention.of(RemoveEvent(target_event_id=event_id), rationale=rationale)
        for event_id in sorted(target_event_ids)
    )


def _headline(deltas: tuple[EventDelta, ...]) -> EventDelta | None:
    """Return the delta module 13's own sensitivity sweep treats as the headline.

    The same selection, by the same key, over the same population -- deltas carrying a
    magnitude on BOTH sides. See this module's docstring for why it is duplicated here and
    what holds the duplicate honest.
    """
    comparable = [
        delta
        for delta in deltas
        if delta.simulated_magnitude is not None and delta.base_magnitude is not None
    ]
    if not comparable:
        return None
    return max(comparable, key=lambda delta: ((delta.magnitude_difference or 0.0), delta.event_id))


def _largest_eliminated(deltas: tuple[EventDelta, ...]) -> EventDelta | None:
    """Return the biggest consequence the change removes outright, or `None` if none is.

    "Biggest" by base magnitude, with the identifier breaking ties, which is `_headline`'s
    rule over the other population. Only ONE is returned and they are never totalled here:
    two eliminated consequences may be measured in different units, and the properly
    combined figure is module 12's `prevented_by_removing`, which this module publishes in a
    separate field under the pack's own declared operator.
    """
    removed = [
        delta
        for delta in deltas
        if delta.present_in_base
        and not delta.present_in_simulated
        and delta.base_magnitude is not None
    ]
    if not removed:
        return None
    return max(removed, key=lambda delta: ((delta.base_magnitude or 0.0), delta.event_id))


def _range_from(result: SimulationResult) -> BenefitRange:
    """Read module 13's sweep as a range, or say why there is no range to read."""
    if result.validity.verdict is ValidityVerdict.EXTRAPOLATION:
        return BenefitRange(
            absent_because=(
                "module 13 returned EXTRAPOLATION: the change travels outside the range this "
                "run witnessed, by more than the tolerance the pack declares. ADR-0070 "
                "requires the verdict to REPLACE the figure rather than sit beside it, so "
                "there is no number here to carry forward. This is not a small benefit; it "
                "is a benefit the data cannot speak to."
            )
        )
    if result.world is None:
        return BenefitRange(
            absent_because=(
                "no change was admitted, so no world was built. The rejection ledger says "
                "which declaration refused the change. An unadmitted premise is not a "
                "benefit of zero -- zero would claim the act was simulated and found "
                "worthless."
            )
        )
    headline = _headline(result.world.diff.deltas)
    if headline is None:
        # No consequence was REDUCED. It may still have been ELIMINATED, which is the more
        # valuable outcome and the one a range cannot describe: module 13 keeps elimination
        # and reduction in separate fields and never sums them (ADR-0069), and its
        # sensitivity sweep perturbs an apportioned share that an elimination does not have.
        #
        # So an elimination publishes a DEGENERATE range -- the whole magnitude, low equal
        # to high -- with the reason its width is zero. The uncertainty has not been hidden;
        # it has moved to where it belongs, into whether the elimination happens at all,
        # which `composed_belief` and the support envelope carry into the confidence vector.
        #
        # Without this branch module 14 could never recommend breaking a direct cause, which
        # is the single most valuable act this engine can identify.
        eliminated = _largest_eliminated(result.world.diff.deltas)
        if eliminated is not None and eliminated.base_magnitude is not None:
            return BenefitRange(
                low=eliminated.base_magnitude,
                high=eliminated.base_magnitude,
                point_of_departure=eliminated.base_magnitude,
                unit=eliminated.unit,
                headline_event_id=eliminated.event_id,
                degenerate_because=(
                    "the consequence is ELIMINATED rather than reduced, so the benefit is "
                    "its whole magnitude and there is no apportioned share to perturb. The "
                    "width is genuinely zero GIVEN THIS GRAPH; the uncertainty is in whether "
                    "the elimination happens, and that is carried by the confidence vector "
                    "beside this figure rather than by widening it here."
                ),
            )
        return BenefitRange(
            absent_because=(
                f"the change reached {result.world.diff.reached_count} occurrence(s) and no "
                "consequence carried a magnitude on both sides of it, so there is nothing "
                "to express as a quantity. That is a statement about which measurements "
                "this graph could attribute, not a finding that the act is worthless."
            )
        )
    outcomes = [
        finding.outcome for finding in result.validity.sensitivity if finding.outcome is not None
    ]
    if not outcomes:
        return BenefitRange(
            absent_because=(
                "the pack declares no sensitivity perturbations, or the sweep could not "
                "run, so no range can be bounded. ADR-0075 forbids publishing the "
                "unperturbed figure as a point: a single number in a unit invites a trust "
                "these inputs do not support (R-23). Declare "
                "`counterfactual_simulation.sensitivity_perturbations` to obtain a range."
            )
        )
    departure = headline.magnitude_difference
    bounds = sorted([*outcomes, *([departure] if departure is not None else [])])
    # A swept range CAN collapse, and the commonest way is the least interesting: the
    # departure figure is zero, and scaling zero by any multiplier leaves zero. That is a
    # real answer -- this graph says the act is worth nothing -- and it must be reported as
    # one rather than crashing on the zero-width guard or being padded into a fake interval.
    collapsed: str | None = None
    if bounds[0] == bounds[-1]:
        collapsed = (
            f"every declared perturbation returned {bounds[0]}, so the sweep produced no "
            "width. This is most often because the figure being perturbed is zero and "
            "scaling zero leaves zero: the change reached the consequence and moved it by "
            "nothing. It is a measured answer about this graph, not a missing one, and it "
            "ranks accordingly rather than being withheld."
        )
    return BenefitRange(
        low=bounds[0],
        high=bounds[-1],
        point_of_departure=departure,
        unit=headline.unit,
        headline_event_id=headline.event_id,
        degenerate_because=collapsed,
        perturbations=tuple(sorted(finding.multiplier for finding in result.validity.sensitivity)),
    )


def _attributed(
    target_event_ids: tuple[str, ...], context: RecommendationContext
) -> PreventedConsequence | None:
    """Ask module 12 what the graph says removing these nodes takes with it.

    Every outcome the caller named is asked separately and the largest attributed figure is
    returned -- never a total across outcomes, which would add quantities that may be in
    different units and may share consequences.
    """
    best: PreventedConsequence | None = None
    for outcome_event_id in sorted(context.outcome_event_ids):
        prevented = prevented_by_removing(outcome_event_id, target_event_ids, context.propagation)
        if prevented.prevented_total is None:
            if best is None:
                best = prevented
            continue
        larger = (
            best is None
            or best.prevented_total is None
            or prevented.prevented_total > best.prevented_total
        )
        if larger:
            best = prevented
    return best


def estimate(
    target_event_ids: tuple[str, ...],
    context: RecommendationContext,
    envelope: OutputEnvelope,
    *,
    accept_unpromoted: bool = False,
) -> BenefitEstimate:
    """Estimate what removing these nodes would be worth, by simulating it.

    Args:
        target_event_ids: the nodes to remove together. A joint cause group arrives whole,
            because removing one member of a joint cause does not prevent the effect
            (ADR-0069) and a partial removal would simulate an act nobody could take.
        context: this run's inputs.
        envelope: the run's output envelope, passed through to module 13.
        accept_unpromoted: forwarded to module 13 unchanged. This module never decides it.

    Raises:
        ContractViolationError: if no target is named. An estimate of nothing is not zero.
    """
    if not target_event_ids:
        raise ContractViolationError(
            "recommendation_engine.estimate was given no target. An estimate over an empty "
            "set is not a benefit of zero; there is no hypothetical to pose."
        )
    interventions = intervention_for(
        target_event_ids,
        rationale=(
            "proposed by the intervention optimizer as a candidate act; its worth is "
            "whatever module 13 says it is."
        ),
    )
    result = simulate(
        interventions, context.simulation, envelope, accept_unpromoted=accept_unpromoted
    )
    attributed = _attributed(target_event_ids, context)
    affected = result.world.diff.deltas if result.world is not None else ()
    by_instance = context.propagation.instances_by_event_id()
    instances = {
        instance_id for delta in affected for instance_id in by_instance.get(delta.event_id, ())
    }
    return BenefitEstimate(
        target_event_ids=tuple(sorted(target_event_ids)),
        benefit=_range_from(result),
        attributed_consequence=attributed.prevented_total if attributed else None,
        attributed_unit=attributed.unit if attributed else None,
        attributed_share=share_of_whole(attributed) if attributed else None,
        attributed_absent_because=attributed.absent_because if attributed else None,
        affected_event_ids=tuple(sorted(delta.event_id for delta in affected)),
        affected_instance_count=len(instances),
        verdict=result.validity.verdict,
        support_envelope_count=len(result.validity.envelopes),
        composed_belief=result.validity.composed_belief,
        composition=result.validity.composition,
        assumptions=result.validity.assumptions,
        rejected_detail=tuple(
            sorted(f"{item.reason.value}: {item.detail}" for item in result.admission.rejected)
        ),
    )
