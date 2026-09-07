"""The LAW-TIME gate. Module 9 owns it, and it lives here alone.

Every proposal from every generator passes through `gate`. There is no second path, no
`skip` argument, and no way for a generator to reach `CandidateEdge` without it -- a
generator holds `Proposal`, and `Proposal` is not a candidate.

THREE OUTCOMES, NOT TWO
-----------------------
`GateOutcome` is deliberately three-valued, mirroring `TemporalVerdict` without collapsing
into it:

* **admitted, verifiable** -- the verdict is `CERTAIN` and both intervals were placed.
  Only these may ever carry `INFERRED`, and `CandidateEdge`'s own invariant enforces it.
* **admitted, temporally unverifiable** -- retained and flagged. `UNDETERMINED` means the
  data placed both events and could not separate them; unverifiable means the data never
  placed one of them. Both block promotion and they are DIFFERENT findings about the
  dataset, so they are counted separately and never summed (`docs/contracts.md` §3).
* **rejected** -- `VIOLATION`. Never constructed, always counted, never repaired.

`UNDETERMINED` IS NEVER DROPPED
-------------------------------
`CONTEXT.md` R-14 predicts that ambiguous pairs may dominate on a day-granular source and
says in as many words that this is "a finding about the dataset, never something to tune
away by loosening the test". This module keeps every one of them and reports the ratio. A
thin graph with an honest `UNDETERMINED` count is worth more than a full one built on
manufactured precedence.

REJECTIONS ARE DATA
-------------------
`RejectionTally` is returned, not logged. A count nobody can read in a test or in a report
is a count nobody notices changing, and the rejection profile is the module's primary
diagnostic on data quality.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.candidate_cause_generator.context import Proposal
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TemporalVerdict, verdict
from causalog.core.types import CandidateEdge

__all__ = [
    "GateOutcome",
    "RejectionReason",
    "RejectionTally",
    "gate",
    "gate_all",
]


class RejectionReason(str, Enum):
    """Why a proposal did not become a candidate. Closed, and counted per generator.

    Closed because the tally is reported per reason: an unmodelled reason would be
    invisible in the report, and the report is the only place a generator's behaviour is
    observable.
    """

    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"
    """LAW-TIME: the cause interval does not precede the effect interval."""

    SELF_EDGE = "SELF_EDGE"
    """The proposal named one event as its own cause. A generator defect, counted as one."""

    CONSTRAINT_SUPPRESSED = "CONSTRAINT_SUPPRESSED"
    """A `CONSTRAINT` rule prohibited the pair. Reported, never silently applied."""

    TRUNCATED_BY_CAP = "TRUNCATED_BY_CAP"
    """The per-effect cap was reached. Applied in `graph.py`; recorded here for one vocabulary."""

    GENERATOR_NOT_RUNNABLE = "GENERATOR_NOT_RUNNABLE"
    """A parameter the generator requires was not declared. Not the same as zero."""


class GateOutcome(BaseModel):
    """What the gate did with one proposal, and why.

    `candidate` is `None` exactly when `reason` is set, and vice versa. Both being set, or
    neither, is a defect in this module rather than a state a caller should handle.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generator_id: str
    #: The pair this outcome concerns, kept whatever the outcome was.
    #:
    #: A rejection sets `candidate` to None, and the candidate is where the two event ids
    #: used to live -- so before these fields existed, refusing a proposal destroyed the
    #: only record of WHICH effect it had been refused for. The counts survived and the
    #: instances did not, which left "what was rejected for this effect, and why?"
    #: answerable only per generator. Both ids are in hand at every construction site
    #: below, so they are required rather than optional: a site cannot forget them.
    cause_event_id: str = Field(min_length=1)
    effect_event_id: str = Field(min_length=1)
    candidate: CandidateEdge | None
    reason: RejectionReason | None

    @property
    def admitted(self) -> bool:
        """Return whether a candidate was created."""
        return self.candidate is not None

    @model_validator(mode="after")
    def _check_invariants(self) -> GateOutcome:
        """Refuse an outcome whose ids disagree with the candidate it carries.

        On the admission path the two ids duplicate what the candidate already holds. That
        duplication is worth having -- one shape for every outcome -- but two copies of a
        fact can disagree, so the copies are checked rather than trusted.
        """
        if self.candidate is None:
            return self
        if (
            self.candidate.source_event_id != self.cause_event_id
            or self.candidate.target_event_id != self.effect_event_id
        ):
            raise ValueError(
                "GateOutcome names a different pair from the candidate it carries: "
                f"({self.cause_event_id}, {self.effect_event_id}) against "
                f"({self.candidate.source_event_id}, {self.candidate.target_event_id})."
            )
        return self


class RejectionTally(BaseModel):
    """Rejection counts by reason, for one generator or for a whole run.

    Every field is a plain integer count. Nothing here is averaged, weighted or ranked --
    it is bookkeeping, and its whole value is that a reader can add the numbers up and get
    the number of proposals back.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    temporal_violation: int = 0
    self_edge: int = 0
    constraint_suppressed: int = 0
    truncated_by_cap: int = 0
    generator_not_runnable: int = 0

    @property
    def total(self) -> int:
        """Return every rejection, summed."""
        return (
            self.temporal_violation
            + self.self_edge
            + self.constraint_suppressed
            + self.truncated_by_cap
            + self.generator_not_runnable
        )

    def with_one(self, reason: RejectionReason) -> RejectionTally:
        """Return a new tally with one more rejection of this reason.

        Returns a new value rather than mutating: the model is frozen, and a mutable
        counter shared between generators is how a per-generator count silently becomes a
        global one.
        """
        field = {
            RejectionReason.TEMPORAL_VIOLATION: "temporal_violation",
            RejectionReason.SELF_EDGE: "self_edge",
            RejectionReason.CONSTRAINT_SUPPRESSED: "constraint_suppressed",
            RejectionReason.TRUNCATED_BY_CAP: "truncated_by_cap",
            RejectionReason.GENERATOR_NOT_RUNNABLE: "generator_not_runnable",
        }[reason]
        return self.model_copy(update={field: getattr(self, field) + 1})

    def plus(self, other: RejectionTally) -> RejectionTally:
        """Return the element-wise sum of two tallies."""
        return RejectionTally(
            temporal_violation=self.temporal_violation + other.temporal_violation,
            self_edge=self.self_edge + other.self_edge,
            constraint_suppressed=self.constraint_suppressed + other.constraint_suppressed,
            truncated_by_cap=self.truncated_by_cap + other.truncated_by_cap,
            generator_not_runnable=self.generator_not_runnable + other.generator_not_runnable,
        )


def gate(proposal: Proposal, run_id: str) -> GateOutcome:
    """Apply LAW-TIME to one proposal and return what happened.

    The provenance class is decided here and never by a generator. An admitted candidate
    carries the WEAKEST class its evidence supports, computed as: `STATISTICAL` if any
    evidence item is statistical, otherwise `ASSUMED`. **Never `INFERRED`,** even when the
    verdict is `CERTAIN` -- promotion to `INFERRED` is a judgement, judgement is module
    10's, and a candidate that promoted itself would have made exactly the decision this
    module exists not to make. Never `OBSERVED`: causation is never read from a record
    (LAW-PROVENANCE, ADR-0020).

    A `VIOLATION` is caught by testing the verdict FIRST rather than by catching the
    `LawViolationError` that `CandidateEdge.between` would raise. Both work; testing first
    means a rejection is an ordinary counted outcome and an exception from `between` stays
    what it should be -- a signal that something bypassed this function.
    """
    if proposal.cause_event.event_id == proposal.effect_event.event_id:
        return GateOutcome(
            generator_id=proposal.generator_id,
            cause_event_id=proposal.cause_event.event_id,
            effect_event_id=proposal.effect_event.event_id,
            candidate=None,
            reason=RejectionReason.SELF_EDGE,
        )
    if (
        verdict(proposal.cause_event.occurred_at, proposal.effect_event.occurred_at)
        is TemporalVerdict.VIOLATION
    ):
        return GateOutcome(
            generator_id=proposal.generator_id,
            cause_event_id=proposal.cause_event.event_id,
            effect_event_id=proposal.effect_event.event_id,
            candidate=None,
            reason=RejectionReason.TEMPORAL_VIOLATION,
        )
    provenance_class = (
        ProvenanceClass.STATISTICAL
        if any(item.provenance_class is ProvenanceClass.STATISTICAL for item in proposal.evidence)
        else ProvenanceClass.ASSUMED
    )
    candidate = CandidateEdge.between(
        source_event=proposal.cause_event,
        target_event=proposal.effect_event,
        generator_id=proposal.generator_id,
        payload=proposal.payload,
        evidence=proposal.evidence,
        provenance_class=provenance_class,
        run_id=run_id,
    )
    return GateOutcome(
        generator_id=proposal.generator_id,
        cause_event_id=proposal.cause_event.event_id,
        effect_event_id=proposal.effect_event.event_id,
        candidate=candidate,
        reason=None,
    )


def gate_all(
    proposals: tuple[Proposal, ...],
    run_id: str,
    suppressed_pairs: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[GateOutcome, ...]:
    """Gate every proposal, in the sequence given, applying declared prohibitions first.

    `suppressed_pairs` are the `(cause_event_id, effect_event_id)` pairs a `CONSTRAINT`
    rule prohibited. They are refused here rather than filtered out silently upstream, so
    the suppression appears in the rejection tally under its own reason -- ADR-0044's
    requirement that "every suppression is reported" carried one layer forward.

    Raises:
        LawViolationError: never, in normal operation. `gate` tests the verdict before
            constructing, so a `LawViolationError` escaping here means a caller reached
            `CandidateEdge.between` around this function.
    """
    outcomes: list[GateOutcome] = []
    for proposal in proposals:
        pair = (proposal.cause_event.event_id, proposal.effect_event.event_id)
        if pair in suppressed_pairs:
            outcomes.append(
                GateOutcome(
                    generator_id=proposal.generator_id,
                    cause_event_id=pair[0],
                    effect_event_id=pair[1],
                    candidate=None,
                    reason=RejectionReason.CONSTRAINT_SUPPRESSED,
                )
            )
            continue
        outcomes.append(gate(proposal, run_id))
    return tuple(outcomes)
