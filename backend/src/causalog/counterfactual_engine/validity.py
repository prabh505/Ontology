r"""How far a hypothetical pushes the system past anything the data witnessed (ADR-0070).

A counterfactual returns a number, and a number is persuasive in a way a hedge is not.
prd.md §52's own worked example is the failure mode written into the document: an observed
fact, a statistical association and a simulated figure in one paragraph, with "likely" and
"approximately" carrying the whole epistemic load. This file is the answer to that, and it
is an EXTENSION of the PRD rather than a reading of it -- the document uses the words
validity, extrapolation and sensitivity exactly zero times, and Principle 5's assumption
enumeration binds recommendations, not counterfactuals (ADR-0065, OQ-029).

FOUR THINGS TRAVEL WITH EVERY OUTCOME, AS FIELDS RATHER THAN AS PROSE
----------------------------------------------------------------------
1. **Belief, and it can only be weaker.** Composed from the links the change actually
   travelled, under a named `core.composition` function recorded on the artifact, with the
   path length beside it and never blended into it (ADR-0060, one layer up). The product is
   reported in its own column and never mixed with the minimum.
2. **A support envelope.** For every quantity the change moved: the range this run actually
   witnessed, the value the change asks for, and the distance between them against the
   pack's declared tolerance.
3. **An extrapolation verdict, returned INSTEAD of a clean number.** Not beside one. A
   figure a reader can quote without its warning is a figure that will be quoted without its
   warning, and the whole point of the envelope is to stop that.
4. **An enumerated assumption list**, each naming what is assumed, why it is needed, and
   what would falsify it.

THE DECLARED BOUND AND THE WITNESSED RANGE ARE DIFFERENT THINGS
----------------------------------------------------------------
`validate.py` checks a proposed value against the ontology's `admissible_range` -- what the
DOMAIN says is possible. This file measures what the RUN witnessed. A value can be entirely
possible and entirely outside anything the data contains, and that is precisely the case an
extrapolation verdict exists to name. Collapsing the two would hide it, which is why
ADR-0067 keeps them in separate places.

WHAT NONE OF THIS IS
---------------------
**It is not calibration.** A support envelope says the change stays inside the range the
data witnessed; it does not say the answer is right. This is OQ-024's argument one layer up
and it is WORSE here, because a simulated figure reads like a measurement of a thing that
did not happen. A decomposed, envelope-checked, sensitivity-swept number is more persuasive
than a bare one, and persuasiveness is not accuracy. Recorded as R-23, and stated in fixed
text on every assessment rather than in a footnote.

**No domain vocabulary appears below.** Nothing here reads a type name.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.composition import DEFAULT_COMPOSER, PATH_COMPOSERS, compose
from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import FLOAT_QUANTIZATION_PLACES
from causalog.core.perturbation import scale_reading
from causalog.core.temporal import Precision
from causalog.counterfactual_engine.context import SimulationContext
from causalog.counterfactual_engine.intervention import (
    ChangeAttribute,
    Intervention,
    ShiftTiming,
)
from causalog.counterfactual_engine.propagate import CONDITION_TEST_NOTICE, Propagation

__all__ = [
    "NOT_CALIBRATED_NOTICE",
    "Assumption",
    "SensitivityFinding",
    "SupportEnvelope",
    "ValidityAssessment",
    "ValidityVerdict",
    "assess",
    "standing_assumptions",
]

#: Fixed text, printed above every assessment, held as a module constant so that no run can
#: soften it. The first thing a reader of a simulated figure must be told.
NOT_CALIBRATED_NOTICE: Final[str] = (
    "NOTHING BELOW IS CALIBRATED. A support envelope says a change stays inside the range "
    "this run witnessed; it does not say the answer is right. Calibration would mean "
    "outcomes stated at a given belief are right that often, and measuring it needs "
    "labelled causal ground truth -- pairs where somebody independently established what "
    "actually caused what. This dataset carries none, so no reliability curve can be drawn "
    "and no error rate can be quoted. A decomposed, envelope-checked, sensitivity-swept "
    "figure is MORE persuasive than a bare one and is not more accurate, and that is the "
    "specific way this artifact could do harm."
)


class ValidityVerdict(str, Enum):
    """How far a change travels beyond what the run witnessed."""

    WITHIN_SUPPORT = "WITHIN_SUPPORT"
    """The value the change asks for lies inside the range this run witnessed."""

    AT_EDGE_OF_SUPPORT = "AT_EDGE_OF_SUPPORT"
    """Outside the witnessed range, and inside the pack's declared tolerance around it."""

    EXTRAPOLATION = "EXTRAPOLATION"
    """Beyond the tolerance. The outcome is returned as this verdict INSTEAD of a figure."""

    NOT_ASSESSABLE = "NOT_ASSESSABLE"
    """Nothing comparable was witnessed, so support cannot be judged either way.

    Distinct from `EXTRAPOLATION`, and the distinction matters: that one says the change
    leaves the data behind, this one says the data never spoke to the question. Collapsing
    them would let an unmeasured run read as a measured one.
    """


class SupportEnvelope(BaseModel):
    """What the run witnessed for one quantity, against what the change asks of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intervention_id: str
    #: What was moved, in this engine's own terms -- never a domain name.
    quantity: str = Field(min_length=1)
    witnessed_low: float | None = None
    witnessed_high: float | None = None
    #: How many comparable observations the range was measured over. The denominator: a
    #: range over two observations is not a range, and a reader cannot tell without this.
    witnessed_count: int = Field(default=0, ge=0)
    requested_value: float | None = None
    #: How far outside the witnessed range the request sits, in the quantity's own units.
    #: `None` when it sits inside, or when nothing comparable was witnessed.
    distance_beyond: float | None = None
    tolerance: float | None = None
    verdict: ValidityVerdict
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[str, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.quantity, self.intervention_id)


class SensitivityFinding(BaseModel):
    """What the outcome becomes when one assumption is perturbed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assumption: str = Field(min_length=1)
    multiplier: float
    outcome: float | None = None
    #: True when the perturbation moves the answer across the line between "this consequence
    #: is reduced" and "this consequence is not meaningfully touched". An outcome that
    #: inverts under a perturbation the data cannot adjudicate is unstable, and is reported
    #: as unstable rather than as an answer.
    unstable: bool = False
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[float, str]:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return (self.multiplier, self.assumption)


class Assumption(BaseModel):
    """One thing that must hold for a simulated figure to mean anything.

    `falsified_by` is required. An assumption nobody can test is a disclaimer, and a list of
    disclaimers is what this field exists to stop the artifact becoming.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    why_needed: str = Field(min_length=1)
    falsified_by: str = Field(min_length=1)

    def sort_key(self) -> str:
        """Return the canonical sequence key (`CONVENTIONS.md` §11)."""
        return self.name


class ValidityAssessment(BaseModel):
    """Everything a reader needs to decide whether to believe a simulated figure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The weakest verdict across every envelope. A hypothetical is only as supported as its
    #: least supported quantity, for the reason a chain is only as strong as its weakest
    #: link: averaging them would let one well-supported change carry an unsupported one.
    verdict: ValidityVerdict
    envelopes: tuple[SupportEnvelope, ...] = ()
    sensitivity: tuple[SensitivityFinding, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    #: Belief composed along the links the change travelled, under a named function.
    composed_belief: float | None = None
    composition: str | None = None
    #: Reported in its OWN column and never blended into `composed_belief` (ADR-0060).
    independent_product: float | None = None
    #: The number of links the composition ran over. A separate field, never folded into
    #: the belief: ADR-0008's never-blend ruling, one level down.
    path_length: int = Field(default=0, ge=0)
    #: Why no belief is carried, when none is. Never a zero.
    belief_absent_because: str | None = None

    @property
    def notice(self) -> str:
        """Return the fixed statement that none of this is calibration.

        A property rather than a field so no revision can soften it and it enters no
        content address.
        """
        return NOT_CALIBRATED_NOTICE

    @property
    def believable(self) -> bool:
        """Return whether the assessment supports quoting a figure at all.

        `EXTRAPOLATION` and `NOT_ASSESSABLE` both answer no, for different reasons the
        artifact states separately. This accessor exists so a renderer cannot accidentally
        print a number the verdict withheld.
        """
        return self.verdict in (
            ValidityVerdict.WITHIN_SUPPORT,
            ValidityVerdict.AT_EDGE_OF_SUPPORT,
        )


#: Weakest first, so a set of verdicts reduces by `min`.
_VERDICT_STRENGTH: Final[dict[ValidityVerdict, int]] = {
    ValidityVerdict.NOT_ASSESSABLE: 0,
    ValidityVerdict.EXTRAPOLATION: 1,
    ValidityVerdict.AT_EDGE_OF_SUPPORT: 2,
    ValidityVerdict.WITHIN_SUPPORT: 3,
}


def standing_assumptions(
    context: SimulationContext, propagation: Propagation
) -> tuple[Assumption, ...]:
    """Return the assumptions every simulated figure in this engine rests on.

    Principle 5's list, extended from recommendations to counterfactuals (ADR-0065). The
    first four hold for every run and are stated as fixed text; the last two are added only
    when the run actually depends on them, because an assumption list padded with
    inapplicable rows is one nobody reads.
    """
    standing = [
        Assumption(
            name="no_unobserved_confounder",
            statement=(
                "No unobserved common cause explains the links this change travelled. If "
                "one does, the change moves nothing in the world and this figure is an "
                "artifact of the graph's shape."
            ),
            why_needed=(
                "The links here were derived from rules, temporal structure and frequency "
                "rather than identified as causal effects (prd.md §16, OQ-007). Nothing in "
                "V1 adjusts for a confounder, and module 9's flags LOCATE observed common "
                "causes without resolving any of them."
            ),
            falsified_by=(
                "A domain expert naming a factor outside the ontology that produces both "
                "ends of any link in the chain."
            ),
        ),
        Assumption(
            name="graph_is_the_world",
            statement=(
                "Every route by which the changed occurrence reaches its consequences is in "
                "the stated graph. A route the graph omits carries none of this change."
            ),
            why_needed=(
                "Propagation is graph surgery. It can only travel links that exist, so "
                "recall bounds the answer and nothing in the system can report what was "
                "missed (R-13)."
            ),
            falsified_by="Any consequence a reader knows of that the graph does not reach.",
        ),
        Assumption(
            name="weights_are_apportionments",
            statement=(
                "The share attributed to each cause of a consequence is a reasonable split "
                "of that consequence among the causes the engine happens to hold for it."
            ),
            why_needed=(
                "Every reduced magnitude is that share applied to a measured total. "
                "ATTRIBUTION_NOT_MEASUREMENT_NOTICE states the limit: two weights are "
                "comparable to each other and neither is a quantity of anything in the "
                "world."
            ),
            falsified_by=(
                "A measurement of what each cause actually contributed, which would make "
                "the apportionment unnecessary rather than wrong."
            ),
        ),
        Assumption(
            name="the_rest_of_the_world_is_held_still",
            statement=(
                "Nothing outside the stated change behaves differently. Every occurrence "
                "the change does not reach happens exactly as it did."
            ),
            why_needed=(
                "A simulated world is the historical world with a surgery applied. There is "
                "no forward process model here and prd.md §6 excludes one."
            ),
            falsified_by=(
                "Any adaptive response to the change -- anything that would have been done "
                "differently once the changed occurrence happened differently."
            ),
        ),
    ]
    if propagation.rests_on_a_qualified_link:
        standing.append(
            Assumption(
                name="condition_test_is_adequate",
                statement=(
                    "A qualified link keeps transmitting unless its recorded expression "
                    "names something this change touched."
                ),
                why_needed=CONDITION_TEST_NOTICE,
                falsified_by=(
                    "A condition that should have stopped holding under this change and "
                    "whose recorded expression names nothing the change touched."
                ),
            )
        )
    if context.derived_precedence is None:
        standing.append(
            Assumption(
                name="no_instant_moved_downstream",
                statement=(
                    "No consequence's instant moved, because this run supplied no "
                    "measurement of which instants the source computed from which."
                ),
                why_needed=(
                    "The graph declares no transfer function for time. Without the "
                    "measurement, moving a downstream instant would be manufactured "
                    "precision (R-20), so nothing downstream was re-timed at all."
                ),
                falsified_by=(
                    "Supplying the derived-precedence measurement, which would re-time every "
                    "consequence the source computed from a moved instant."
                ),
            )
        )
    return tuple(sorted(standing, key=lambda item: item.sort_key()))


def _witnessed_gaps(
    context: SimulationContext, target_event_id: str
) -> tuple[tuple[float, ...], str, str]:
    """Return the gaps this run witnessed around the target's type, and which side.

    The reference a timing change is judged against. Asking "what if this had happened
    thirty minutes earlier" is inside support when the run contains instances where that gap
    really was thirty minutes different, and outside it when it does not -- which is a
    question about the data and not about the graph.

    **Measured before the occurrence where it has antecedents, and after it where it does
    not.** A root has nothing before it, and answering `NOT_ASSESSABLE` for every root would
    make the whole envelope unavailable for exactly the occurrences a hypothetical most
    often moves. The side that was measured travels in the return value and onto the
    envelope's `quantity`, because a gap before and a gap after are different quantities and
    a reader must not have to guess which one the range describes.

    Measured over TYPE pairs rather than over the one instance, because one instance
    witnesses one gap and a range over one observation is not a range.

    Returns:
        `(gaps, side, absent_because)`. `side` is `"before"` or `"after"`; `absent_because`
        is non-empty exactly when no gap was witnessed.
    """
    events = context.events_by_id()
    target = events.get(target_event_id)
    if target is None:
        return ((), "before", "the change names an occurrence this run does not hold")
    before_types = sorted(
        {
            events[link.source_event_id].event_type
            for link in context.links_into(target_event_id)
            if link.source_event_id in events
        }
    )
    after_types = sorted(
        {
            events[link.target_event_id].event_type
            for link in context.links_from(target_event_id)
            if link.target_event_id in events
        }
    )
    side = "before" if before_types else "after"
    neighbour_types = before_types or after_types
    if not neighbour_types:
        return (
            (),
            side,
            f"the stated graph holds neither an antecedent nor a consequence for "
            f"{target_event_id}, so there is no gap this run witnessed to judge a move "
            "against",
        )
    by_instance: dict[str, list[str]] = {}
    for identifier, instances in sorted(context.propagation.instances_by_event_id().items()):
        for instance in instances:
            by_instance.setdefault(instance, []).append(identifier)
    gaps: list[float] = []
    for instance in sorted(by_instance):
        held = [events[name] for name in sorted(by_instance[instance]) if name in events]
        same_type = [item for item in held if item.event_type == target.event_type]
        neighbours = [item for item in held if item.event_type in neighbour_types]
        for one in same_type:
            for other in neighbours:
                if one.occurred_at.precision is Precision.UNKNOWN:
                    continue
                if other.occurred_at.precision is Precision.UNKNOWN:
                    continue
                earlier, later = (other, one) if side == "before" else (one, other)
                seconds = (
                    later.occurred_at.t_earliest - earlier.occurred_at.t_earliest
                ).total_seconds()
                gaps.append(round(seconds, FLOAT_QUANTIZATION_PLACES))
    if not gaps:
        return (
            (),
            side,
            "no process instance in this run placed both ends of any neighbouring pair, so "
            "no gap was witnessed at all -- an absence of measurement, not a measurement of "
            "nothing",
        )
    return (tuple(sorted(gaps)), side, "")


def _witnessed_attribute(
    context: SimulationContext, event_type: str, attribute_name: str
) -> tuple[tuple[float, ...], tuple[str, ...]]:
    """Return the numeric and textual values this run witnessed for one attribute."""
    numeric: list[float] = []
    textual: list[str] = []
    for event in sorted(context.events_by_id().values(), key=lambda item: item.event_id):
        if event.event_type != event_type:
            continue
        held = dict(event.changed_attributes).get(attribute_name)
        if held is None:
            continue
        textual.append(held)
        try:
            numeric.append(round(float(held), FLOAT_QUANTIZATION_PLACES))
        except ValueError:
            continue
    return (tuple(sorted(numeric)), tuple(sorted(set(textual))))


def _verdict_for(
    requested: float, low: float, high: float, tolerance: float | None
) -> tuple[ValidityVerdict, float | None]:
    """Return the verdict for one request against a witnessed range, and how far beyond."""
    if low <= requested <= high:
        return (ValidityVerdict.WITHIN_SUPPORT, None)
    beyond = (requested - high) if requested > high else (low - requested)
    beyond = round(beyond, FLOAT_QUANTIZATION_PLACES)
    if tolerance is None:
        return (ValidityVerdict.EXTRAPOLATION, beyond)
    spread = high - low
    allowed = round(spread * tolerance, FLOAT_QUANTIZATION_PLACES)
    if beyond <= allowed:
        return (ValidityVerdict.AT_EDGE_OF_SUPPORT, beyond)
    return (ValidityVerdict.EXTRAPOLATION, beyond)


def _envelope_for_shift(
    intervention: Intervention, payload: ShiftTiming, context: SimulationContext
) -> SupportEnvelope:
    """Return the support envelope for one timing change."""
    tolerance = context.parameters.support_envelope_tolerance
    gaps, side, absent = _witnessed_gaps(context, payload.target_event_id)
    quantity = f"gap in seconds {side} {payload.target_event_id}"
    if not gaps:
        return SupportEnvelope(
            intervention_id=intervention.intervention_id,
            quantity=quantity,
            requested_value=payload.shift_seconds,
            tolerance=tolerance,
            verdict=ValidityVerdict.NOT_ASSESSABLE,
            detail=(
                f"support cannot be judged for this move: {absent}. That is different from "
                "the move leaving the data behind, and the two are kept apart so an "
                "unmeasured run cannot read as a measured one."
            ),
        )
    events = context.events_by_id()
    target = events[payload.target_event_id]
    if side == "before":
        neighbours = [
            events[link.source_event_id]
            for link in context.links_into(payload.target_event_id)
            if link.source_event_id in events
        ]
    else:
        neighbours = [
            events[link.target_event_id]
            for link in context.links_from(payload.target_event_id)
            if link.target_event_id in events
        ]
    current = min(
        (
            round(
                (
                    (target.occurred_at.t_earliest - neighbour.occurred_at.t_earliest)
                    if side == "before"
                    else (neighbour.occurred_at.t_earliest - target.occurred_at.t_earliest)
                ).total_seconds(),
                FLOAT_QUANTIZATION_PLACES,
            )
            for neighbour in neighbours
        ),
        default=0.0,
    )
    # Moving the occurrence LATER widens the gap before it and narrows the gap after it, so
    # the sign the request contributes depends on which side was measured. Getting this
    # backwards would report a supported move as an extrapolation and vice versa.
    requested = round(
        current + (payload.shift_seconds if side == "before" else -payload.shift_seconds),
        FLOAT_QUANTIZATION_PLACES,
    )
    verdict, beyond = _verdict_for(requested, gaps[0], gaps[-1], tolerance)
    return SupportEnvelope(
        intervention_id=intervention.intervention_id,
        quantity=quantity,
        witnessed_low=gaps[0],
        witnessed_high=gaps[-1],
        witnessed_count=len(gaps),
        requested_value=requested,
        distance_beyond=beyond,
        tolerance=tolerance,
        verdict=verdict,
        detail=(
            f"this run witnessed gaps {side} an occurrence of this kind from {gaps[0]} to "
            f"{gaps[-1]} second(s) over {len(gaps)} observation(s); the change asks for "
            f"{requested}. The witnessed range is what the DATA contains and is a different "
            "question from what the ontology declares possible, which validation already "
            "checked."
        ),
    )


def _envelope_for_attribute(
    intervention: Intervention, payload: ChangeAttribute, context: SimulationContext
) -> SupportEnvelope:
    """Return the support envelope for one attribute change."""
    tolerance = context.parameters.support_envelope_tolerance
    events = context.events_by_id()
    target = events.get(payload.target_event_id)
    quantity = (
        f"{target.event_type}.{payload.attribute_name}"
        if target is not None
        else payload.attribute_name
    )
    if target is None:
        return SupportEnvelope(
            intervention_id=intervention.intervention_id,
            quantity=quantity,
            tolerance=tolerance,
            verdict=ValidityVerdict.NOT_ASSESSABLE,
            detail="the change names an occurrence this run does not hold.",
        )
    numeric, textual = _witnessed_attribute(context, target.event_type, payload.attribute_name)
    try:
        requested = round(float(payload.new_value), FLOAT_QUANTIZATION_PLACES)
    except ValueError:
        witnessed = ", ".join(textual) if textual else "nothing"
        if not textual:
            return SupportEnvelope(
                intervention_id=intervention.intervention_id,
                quantity=quantity,
                tolerance=tolerance,
                verdict=ValidityVerdict.NOT_ASSESSABLE,
                detail=(
                    f"no occurrence of {target.event_type} in this run carries "
                    f"{payload.attribute_name} at all, so nothing was witnessed to compare "
                    "the requested value against."
                ),
            )
        seen = payload.new_value in textual
        return SupportEnvelope(
            intervention_id=intervention.intervention_id,
            quantity=quantity,
            witnessed_count=len(textual),
            tolerance=tolerance,
            verdict=(ValidityVerdict.WITHIN_SUPPORT if seen else ValidityVerdict.EXTRAPOLATION),
            detail=(
                f"this run witnessed {witnessed} for this attribute. The change asks for "
                f"{payload.new_value!r}, which "
                + ("occurs in the data." if seen else "NEVER occurs in it.")
                + " A value the ontology admits and the data never contains is possible and "
                "unsupported, which is the case this verdict exists to name."
            ),
        )
    if not numeric:
        return SupportEnvelope(
            intervention_id=intervention.intervention_id,
            quantity=quantity,
            requested_value=requested,
            tolerance=tolerance,
            verdict=ValidityVerdict.NOT_ASSESSABLE,
            detail=(
                f"no occurrence of {target.event_type} in this run carries a numeric "
                f"{payload.attribute_name}, so there is no witnessed range."
            ),
        )
    verdict, beyond = _verdict_for(requested, numeric[0], numeric[-1], tolerance)
    return SupportEnvelope(
        intervention_id=intervention.intervention_id,
        quantity=quantity,
        witnessed_low=numeric[0],
        witnessed_high=numeric[-1],
        witnessed_count=len(numeric),
        requested_value=requested,
        distance_beyond=beyond,
        tolerance=tolerance,
        verdict=verdict,
        detail=(
            f"this run witnessed {numeric[0]} to {numeric[-1]} over {len(numeric)} "
            f"occurrence(s); the change asks for {requested}."
        ),
    )


def _belief(
    propagation: Propagation, context: SimulationContext
) -> tuple[float | None, str | None, float | None, int, str | None]:
    """Return the composed belief along the links the change travelled.

    Composed under the function the pack names, which a caller can read off the artifact.
    The product is computed beside it and never blended into it (ADR-0060).
    """
    name = context.parameters.path_composition or DEFAULT_COMPOSER
    if name not in PATH_COMPOSERS:
        raise ContractViolationError(
            f"the pack names path_composition {name!r}, which is not registered in "
            f"core.composition. Registered: {', '.join(sorted(PATH_COMPOSERS))}. A pack "
            "chooses a named composition; it never supplies one."
        )
    touched = {delta.event_id for delta in propagation.deltas}
    scalars: list[float] = []
    for event_id in sorted(touched):
        for link in context.links_into(event_id):
            scalars.append(link.link_scalar)
    if not scalars:
        return (
            None,
            name,
            None,
            0,
            "the change travelled no stated link, so there is no chain of belief to compose. "
            "This is an absence and not a belief of zero.",
        )
    sequenced_scalars = sorted(scalars)
    return (
        compose(sequenced_scalars, name),
        name,
        compose(sequenced_scalars, "independent_product_v1"),
        len(sequenced_scalars),
        None,
    )


def _sensitivity(
    propagation: Propagation, context: SimulationContext
) -> tuple[SensitivityFinding, ...]:
    """Return what the headline outcome becomes under each declared perturbation."""
    perturbations = context.parameters.sensitivity_perturbations
    if not perturbations:
        return ()
    reduced = [
        delta
        for delta in propagation.deltas
        if delta.simulated_magnitude is not None and delta.base_magnitude is not None
    ]
    if not reduced:
        return (
            SensitivityFinding(
                assumption="apportioned_share",
                multiplier=perturbations[0],
                unstable=False,
                detail=(
                    "no consequence carried a magnitude on both sides, so there is no figure "
                    "to perturb. The sweep is reported as not runnable rather than as a "
                    "finding that the answer is stable."
                ),
            ),
        )
    headline = max(
        reduced,
        key=lambda delta: ((delta.magnitude_difference or 0.0), delta.event_id),
    )
    base_difference = headline.magnitude_difference or 0.0
    findings: list[SensitivityFinding] = []
    for multiplier in perturbations:
        perturbed = scale_reading(base_difference, multiplier)
        findings.append(
            SensitivityFinding(
                assumption="apportioned_share",
                multiplier=multiplier,
                outcome=perturbed,
                unstable=(base_difference > 0.0) != (perturbed > 0.0),
                detail=(
                    f"scaling the share attributed to the removed cause(s) by {multiplier} "
                    f"moves the headline difference on {headline.event_id} from "
                    f"{base_difference} to {perturbed}. The share is an apportionment rather "
                    "than a measurement, so this sweep is testing the one input most likely "
                    "to be wrong."
                ),
            )
        )
    return tuple(sorted(findings, key=lambda item: item.sort_key()))


def assess(
    admitted: tuple[Intervention, ...],
    propagation: Propagation,
    context: SimulationContext,
) -> ValidityAssessment:
    """Return the validity assessment for one hypothetical.

    Args:
        admitted: the changes that were simulated.
        propagation: what they did to the graph.
        context: the run's inputs.

    Returns:
        The envelopes, the sensitivity sweep, the assumptions, and the composed belief,
        under the weakest verdict any quantity earned.
    """
    envelopes: list[SupportEnvelope] = []
    for intervention in admitted:
        payload = intervention.payload
        if isinstance(payload, ShiftTiming):
            envelopes.append(_envelope_for_shift(intervention, payload, context))
        elif isinstance(payload, ChangeAttribute):
            envelopes.append(_envelope_for_attribute(intervention, payload, context))
    sequenced = tuple(sorted(envelopes, key=lambda item: item.sort_key()))
    verdict = (
        min((item.verdict for item in sequenced), key=lambda one: _VERDICT_STRENGTH[one])
        if sequenced
        else ValidityVerdict.NOT_ASSESSABLE
    )
    belief, composition, product, length, absent = _belief(propagation, context)
    return ValidityAssessment(
        verdict=verdict,
        envelopes=sequenced,
        sensitivity=_sensitivity(propagation, context),
        assumptions=standing_assumptions(context, propagation),
        composed_belief=belief,
        composition=composition,
        independent_product=product,
        path_length=length,
        belief_absent_because=absent,
    )
