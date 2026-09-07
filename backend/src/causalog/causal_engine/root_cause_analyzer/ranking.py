"""`RankedCause` -- five signals about one candidate, carried separately and never blended.

prd.md §29 defines a root cause as **the earliest ACTIONABLE event whose modification would
prevent the largest amount of downstream consequence**, and then immediately says that the
earliest and the actionable may be different events and that the system should distinguish
both. ADR-0008 turned that into a ruling this module is built around: earliness and
prevented consequence are not commensurable, any weighting between them would be an
unexplainable constant, and LAW-EVIDENCE forbids a number whose parts cannot be inspected.

So a `RankedCause` carries **five signals as five fields**:

1. `prevented` -- what the graph says stops occurring if this is removed (module 12's
   counterfactual-lite, correct on diamonds by re-reachability rather than by subtraction).
2. `is_actionable` -- read from `Event.is_actionable`, which ADR-0008 stamps at generation
   time so that this module never reads the ontology (forbidden edge F3). Refined, never
   overridden, by the declared cost and severity ranks beside it.
3. `earliness_rank` -- structural position in the chain. A tie-break and never a term.
4. `chain_confidence` -- belief about the route connecting it to the outcome, composed
   under a named function with its length beside it.
5. `recurrence` -- how often this cause-to-outcome shape appears across the run.

`sequencing_value` is the only place two of them meet, it is ADR-0008's literal criterion
(prevented times confidence), the function that computed it is named on the artifact, and it
is `None` whenever the prevented magnitude could not be measured. **It is not a score for
the cause.** A consumer that reads it as one has read the one number this module publishes
and ignored the five it publishes beside it, which is the failure ADR-0008 rejected option C
to prevent.

WHY THERE IS NO SINGLE "ROOT CAUSE SCORE" ANYWHERE IN THIS PACKAGE. Not an omission. The
number would have to weight a quantity against a position in a chain, and there is no
principled weight -- so any number produced would be a judgement disguised as arithmetic,
and it would move the headline answer without anybody being able to say why.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.propagation_analyzer import PathConfidence
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass
from causalog.core.types.confidence import ConfidenceVector

__all__ = ["ActionabilityStanding", "RankedCause", "Recurrence"]


class ActionabilityStanding(BaseModel):
    """What is known about acting on one cause, and how well the record agrees with itself.

    `is_actionable` comes from the EVENT and is authoritative (ADR-0008). `pack_declares`
    comes from the ontology views and is carried only so a disagreement can be REPORTED. A
    run whose events were generated under an earlier ontology is exactly where the two
    diverge, and a silent divergence would move the headline answer with nothing recording
    that it had.

    `cost_rank` and `severity_rank` refine a set the boolean has already selected. They
    never promote an unactionable event into the actionable set, and a missing rank leaves
    a cause in the set rather than dropping it -- an undeclared cost is an unknown cost, not
    a prohibitive one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_actionable: bool
    pack_declares: bool | None = None
    cost_class: str | None = None
    cost_rank: int | None = None
    severity_class: str | None = None
    severity_rank: int | None = None
    #: Set when the event's stamp and the current pack disagree. Never resolved here.
    disagreement: str | None = None

    @property
    def unvalidated(self) -> str:
        """Return the fixed caveat. A property, so no revision can soften it.

        `CONTEXT.md` R-15: a mis-declared flag silently changes the headline ranking and
        nothing in this system can detect it. Carrying the declaration further does not
        validate it.
        """
        return (
            "ACTIONABILITY IS DECLARED, NOT OBSERVED. It is ontology configuration carried "
            "with provenance ASSUMED. Nothing in this engine can check whether an event "
            "really was one somebody could have acted on, so a wrong declaration moves this "
            "ranking and leaves no trace (R-15). Read the flag as the pack's claim, not as "
            "a finding."
        )


class Recurrence(BaseModel):
    """How often this cause-to-outcome shape appears, and whether that counts as structural.

    The COUNT is a measurement and is always present. The WORD "structural" is a judgement
    and needs a declared threshold, so `structural` is `None` when the pack sets none --
    never `False`, which would read as "we checked and it is incidental".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many distinct outcomes of the same type this cause type is claimed to cause.
    occurrences: int = Field(ge=1)
    #: How many distinct process instances those occurrences span. One cause type firing
    #: forty times inside one instance is a different finding from it firing once in forty.
    instance_span: int = Field(ge=0)
    minimum_support: int | None = None
    structural: bool | None = None
    detail: str = Field(min_length=1)


class RankedCause(BaseModel):
    """One candidate cause, with every signal about it carried separately.

    Invariants, enforced below and by `tests/law/test_ranking_never_collapses.py`:

    * `evidence_item_ids` is non-empty. LAW-EVIDENCE: a ranked result with no evidence
      chain is a bare assertion, and this module's whole output is assertions about which
      thing to change.
    * `confidence` is the whole `ConfidenceVector` of the weakest link on the chain, not a
      scalar. A ledger entry saying "this scored 0.24" and nothing else is the unexplained
      number prd.md §49 forbids.
    * `sequencing_value` is `None` whenever `prevented_magnitude` is. A candidate nobody
      could value is not sequenced at zero, which would place it below candidates that were
      measured and found small.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    #: Signal 1. What the graph says stops occurring if this is removed.
    prevented_event_ids: tuple[str, ...] = ()
    prevented_magnitude: float | None = None
    prevented_unit: str | None = None
    #: The whole-graph total the prevented figure is a part of, and the proportion. `None`
    #: rather than zero when either is unmeasurable: a proportion of an unmeasured whole is
    #: not a proportion. prd.md §32's "propagation reduced 82%" figure.
    whole_magnitude: float | None = None
    prevented_share: float | None = None
    prevented_absent_because: str | None = None
    #: Signal 2.
    actionability: ActionabilityStanding
    #: Signal 3. 1 is earliest. A TIE-BREAK, never a term (ADR-0008).
    earliness_rank: int = Field(ge=1)
    #: Signal 4.
    chain: PathConfidence
    confidence: ConfidenceVector
    #: Signal 5.
    recurrence: Recurrence
    #: The one place two signals meet: ADR-0008's prevented-times-confidence criterion.
    #: NOT a score for the cause -- see this module's docstring.
    sequencing_value: float | None = None
    #: Names the function in `causalog.core.ranking` that produced it.
    sequencing_function: str | None = None
    #: LAW-EVIDENCE. The chain of evidence behind the claim that this causes the outcome.
    evidence_item_ids: tuple[str, ...] = Field(min_length=1)
    #: The links from this cause to the outcome, cause-first, as `(source, target, kind)`.
    chain_links: tuple[tuple[str, str, str], ...] = Field(min_length=1)
    provenance_class: ProvenanceClass
    #: Set when the chain passes through a timeline gap or an unplaced instant. A chain with
    #: partial data is RANKED and FLAGGED, and the flag must survive into the explanation
    #: (`docs/architecture.md` §2, module 11's stated failure mode).
    partial_data_flag: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> RankedCause:
        """Refuse a ranked result that cannot account for itself."""
        if self.prevented_magnitude is None and self.sequencing_value is not None:
            raise ContractViolationError(
                f"RankedCause {self.event_id} has a sequencing value and no prevented "
                "magnitude. The value is prevented-times-confidence; without the first "
                "operand it is a number with no derivation, which is the unexplained "
                "figure prd.md §49 forbids."
            )
        if self.prevented_magnitude is None and self.prevented_absent_because is None:
            raise ContractViolationError(
                f"RankedCause {self.event_id} reports no prevented magnitude and no reason. "
                "An unexplained absence is read as a zero by the next person to look at it."
            )
        listed = list(self.evidence_item_ids)
        if listed != sorted(listed) or len(set(listed)) != len(listed):
            raise ContractViolationError(
                f"RankedCause {self.event_id} carries unsequenced or repeated evidence "
                "identifiers; the chain is rendered and hashed and two sequences produce "
                "two hashes for one result (CONVENTIONS.md §11)."
            )
        return self

    def sort_key(self) -> tuple[float, int, str]:
        """Return the sequence key: prevented-times-confidence, then earliness, then id.

        ADR-0008's ruling, expressed as a TUPLE rather than as a blended scalar. Earliness
        enters at position two, as a tie-break, and never as a weighted term -- a reader can
        read each element off separately and disagree with it separately.

        The first element is negated so a larger prevented consequence sequences first. An
        unmeasurable candidate takes `0.0` HERE and only here: it must land somewhere in a
        total sequence, and it lands last among the measured, with `prevented_magnitude`
        still `None` on the artifact so no reader mistakes the placement for a measurement.
        """
        return (
            -(self.sequencing_value if self.sequencing_value is not None else 0.0),
            self.earliness_rank,
            self.event_id,
        )
