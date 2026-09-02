"""`CausalEdge` -- a proposed causal relation between two events (prd.md §25, §26).

The five edge kinds of prd.md §26 are modelled as five payload types under one
discriminated union, not as one edge carrying a string label. The difference matters: a
`CONDITIONAL` edge without its condition, or an `AMPLIFYING` edge without its magnitude,
is not a slightly incomplete edge -- it is an unusable one, and a string label lets it be
constructed anyway and fail somewhere downstream where the cause is no longer visible.
Under a union, the required data is required by the type.

LAW-TIME is enforced here, at construction, not by a checker someone must remember to run.
See `CausalEdge.between`.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_text,
    digest,
)
from causalog.core.provenance import ProvenanceClass
from causalog.core.temporal import TemporalVerdict, is_unverifiable, verdict
from causalog.core.types.confidence import ConfidenceVector
from causalog.core.types.event import Event
from causalog.core.types.evidence import EvidenceItem

__all__ = [
    "AmplifyingCause",
    "CausalEdge",
    "CausalEdgeKind",
    "CausalEdgePayload",
    "ConditionalCause",
    "ContributingCause",
    "DirectCause",
    "InhibitingCause",
]


class CausalEdgeKind(str, Enum):
    """The closed edge taxonomy of prd.md §26.

    Closed because `edge_kind` is part of the edge's content-addressed identifier and of
    the canonical edge sort key (`CONVENTIONS.md` §9, §11): an unmodelled kind would
    produce identifiers no rerun could reproduce.
    """

    DIRECT = "DIRECT"
    """A produces B with no intermediary in the modelled graph."""

    CONDITIONAL = "CONDITIONAL"
    """A produces B only when a stated condition holds."""

    CONTRIBUTING = "CONTRIBUTING"
    """A is one of several joint causes, none of which is sufficient alone."""

    AMPLIFYING = "AMPLIFYING"
    """A increases the magnitude of B without being the origin of B."""

    INHIBITING = "INHIBITING"
    """A reduces propagation through B. An inhibitor is a positive, recorded event."""


class DirectCause(BaseModel):
    """The `DIRECT` payload: deliberately empty.

    The absence of extra data is itself the claim -- no condition qualifies it, no group
    shares it, no magnitude modifies it. It exists as a type rather than as `None` so that
    every branch of the union is reached the same way and adding a field later is a
    schema change rather than a change of shape.

    Not "proven" and not "the only cause" (`GLOSSARY.md`): directness is a statement about
    the modelled graph having no intermediary, not about certainty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_kind: Literal[CausalEdgeKind.DIRECT] = CausalEdgeKind.DIRECT


class ConditionalCause(BaseModel):
    """The `CONDITIONAL` payload: A produces B only when `condition_expression` holds.

    Not a probability (`GLOSSARY.md`). The condition is explicit and checkable, and
    `condition_holds` records the result of checking it for *this* pair, so a reader can
    see both the qualification and its evaluation without re-running the pipeline.

    Invariants:
      * `condition_expression` is non-empty and is the exact expression that was
        evaluated, in whatever the rule pack's own syntax is -- a paraphrase is not
        re-checkable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_kind: Literal[CausalEdgeKind.CONDITIONAL] = CausalEdgeKind.CONDITIONAL
    condition_expression: str
    condition_holds: bool

    @model_validator(mode="after")
    def _check_invariants(self) -> ConditionalCause:
        """Enforce the documented invariants at construction."""
        if not self.condition_expression.strip():
            raise ValueError(
                "ConditionalCause.condition_expression is empty; a conditional edge whose "
                "condition nobody can read is an unqualified edge wearing a label."
            )
        return self


class ContributingCause(BaseModel):
    """The `CONTRIBUTING` payload: one member of a joint cause group.

    Contributors are **conjunctive, not competing** (`GLOSSARY.md`): the group jointly
    produces the outcome and no member is sufficient alone. This is why the payload
    carries a group identifier rather than a rank -- presenting contributors as a ranked
    list would invite a reader to act on the top one, which is precisely the reading the
    joint-cause model exists to prevent.

    Invariants:
      * `joint_cause_group_id` is non-empty. Every member of one group carries the same
        value, which is what lets the group be reassembled from the edges alone.
      * `co_cause_event_ids` is non-empty and sorted, and does not name this edge's own
        source event -- an event is not its own co-cause.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_kind: Literal[CausalEdgeKind.CONTRIBUTING] = CausalEdgeKind.CONTRIBUTING
    joint_cause_group_id: str
    co_cause_event_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _check_invariants(self) -> ContributingCause:
        """Enforce the documented invariants at construction."""
        if not self.joint_cause_group_id.strip():
            raise ValueError(
                "ContributingCause.joint_cause_group_id is empty; without it the joint "
                "cause group cannot be reassembled and each contributor reads as a "
                "sufficient cause on its own."
            )
        if not self.co_cause_event_ids:
            raise ValueError(
                "ContributingCause.co_cause_event_ids is empty; a contributing cause with "
                "no co-causes is a direct cause and should say so."
            )
        if list(self.co_cause_event_ids) != sorted(self.co_cause_event_ids):
            raise ValueError(
                "ContributingCause.co_cause_event_ids must be sorted (CONVENTIONS.md §11)."
            )
        return self


class AmplifyingCause(BaseModel):
    """The `AMPLIFYING` payload: A increases the magnitude of a downstream effect.

    Not a cause of the effect's *existence*, only of its size (`GLOSSARY.md`). An
    amplifier removed from the graph makes the effect smaller; it does not make it absent.

    Invariants:
      * `magnitude_multiplier > 1.0`. A multiplier of exactly 1.0 amplifies nothing and
        should not have been recorded as an edge; below 1.0 it is an inhibitor and must be
        modelled as one, so that a consumer reading the kind alone is never misled about
        the direction of the effect.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_kind: Literal[CausalEdgeKind.AMPLIFYING] = CausalEdgeKind.AMPLIFYING
    magnitude_multiplier: float

    @model_validator(mode="after")
    def _check_invariants(self) -> AmplifyingCause:
        """Enforce the documented invariants at construction."""
        if not self.magnitude_multiplier > 1.0:
            raise ValueError(
                f"AmplifyingCause.magnitude_multiplier {self.magnitude_multiplier} must "
                "exceed 1.0; at or below 1.0 the edge is not amplifying and the kind "
                "would misdescribe the direction of the effect."
            )
        return self


class InhibitingCause(BaseModel):
    """The `INHIBITING` payload: A reduces propagation of a downstream effect.

    Not the absence of a cause -- an inhibitor is a positive, recorded event
    (`GLOSSARY.md`). Its magnitude is expressed on the same scale as an amplifier's so
    that propagation arithmetic never has to branch on the kind.

    Invariants:
      * `0.0 <= magnitude_multiplier < 1.0`. Zero is total suppression; 1.0 would inhibit
        nothing and belongs to no edge; above 1.0 it is an amplifier.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_kind: Literal[CausalEdgeKind.INHIBITING] = CausalEdgeKind.INHIBITING
    magnitude_multiplier: float

    @model_validator(mode="after")
    def _check_invariants(self) -> InhibitingCause:
        """Enforce the documented invariants at construction."""
        if not 0.0 <= self.magnitude_multiplier < 1.0:
            raise ValueError(
                f"InhibitingCause.magnitude_multiplier {self.magnitude_multiplier} must "
                "lie in [0.0, 1.0); at or above 1.0 the edge is not inhibiting."
            )
        return self


#: The discriminated union. `edge_kind` is the discriminator, so pydantic selects the
#: payload type from the data itself and a deserialized edge cannot land in the wrong
#: branch.
CausalEdgePayload = Annotated[
    DirectCause | ConditionalCause | ContributingCause | AmplifyingCause | InhibitingCause,
    Field(discriminator="edge_kind"),
]


class CausalEdge(BaseModel):
    """A proposed causal relation between two events, carrying why anyone believes it.

    Construct with `CausalEdge.between`, which is the only path that can evaluate LAW-TIME.
    Direct construction and `model_validate` remain available for deserialization and are
    guarded by the same invariants.

    **What that does and does not buy (DEF-0002).** The invariants below re-run on every
    path, so a stored `VIOLATION` verdict and a stored `OBSERVED` provenance are both
    refused on the way back in. They cannot verify the verdict itself: this artifact stores
    `source_event_id` and `target_event_id`, not the two intervals, so nothing inside it can
    recompute `verdict(...)`. An `UNDETERMINED` verdict rewritten to `CERTAIN` -- on the wire
    or by a direct `CausalEdge(...)` call that never touched an `Event` -- is therefore
    accepted, and may then carry `INFERRED`. `between` is the *sanctioned* constructor, not
    an enforceable one; pydantic cannot tell a direct call from the `model_validate` that
    deserialization requires. The boundary is pinned in
    `tests/law/test_law_time_survives_the_wire.py`, and closing it means putting the
    intervals or a verdict-bearing address into the artifact -- an ADR and an
    `engine_version` bump (`docs/contracts.md` section 8), not an edit.

    `edge_kind`, `rule_support`, and `statistical_support` are **derived properties**, not
    stored fields. prd.md §25 lists the latter two as edge data and prd.md §49 lists them
    as confidence components; storing both would be one number in two places, free to
    disagree. The confidence vector is the single home, and these read it.

    Invariants:
      * `temporal_verdict` is never `VIOLATION`. An edge whose cause cannot precede its
        effect is not stored with a warning flag; it does not exist (LAW-TIME,
        `CONVENTIONS.md` §7).
      * `provenance_class == INFERRED` requires `temporal_verdict == CERTAIN` and
        `temporally_unverifiable is False`. An inference standing on ambiguous or absent
        time is an inference standing on nothing (`CONVENTIONS.md` §10, ADR-0007).
      * `provenance_class` is never `OBSERVED`. Causation is never read from a source
        record; a source record can only ever supply a `PRECEDES`, and promoting that to a
        cause is the exact conflation LAW-PROVENANCE exists to prevent.
      * `evidence` is non-empty (LAW-EVIDENCE).
      * `source_event_id != target_event_id`. An event does not cause itself.
      * `propagation_weight` lies in `[0.0, 1.0]`.
      * `run_id` is present. Every inferred artifact is run-scoped (ADR-0013), which is
        what structurally prevents it from overwriting a dataset-scoped observed fact.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    causal_edge_id: str
    source_event_id: str
    target_event_id: str
    payload: CausalEdgePayload
    confidence: ConfidenceVector
    evidence: tuple[EvidenceItem, ...]
    propagation_weight: float
    provenance_class: ProvenanceClass
    temporal_verdict: TemporalVerdict
    temporally_unverifiable: bool
    run_id: str

    @property
    def edge_kind(self) -> CausalEdgeKind:
        """Return the edge kind, read from the payload so the two cannot disagree."""
        return self.payload.edge_kind

    @property
    def rule_support(self) -> float | None:
        """Return the `rule_support` confidence component value, or None if absent."""
        return self._component_value("rule_support")

    @property
    def statistical_support(self) -> float | None:
        """Return the `statistical_support` confidence component value, or None."""
        return self._component_value("statistical_support")

    def _component_value(self, component_name: str) -> float | None:
        """Return one named component's value from the confidence vector, or None."""
        for component in self.confidence.components:
            if component.component_name == component_name:
                return component.value
        return None

    @classmethod
    def address(
        cls,
        source_event_id: str,
        target_event_id: str,
        edge_kind: CausalEdgeKind,
    ) -> str:
        """Return the content-addressed identifier for an edge (`CONVENTIONS.md` §9).

        Payload recipe: `source_event_id | target_event_id | edge_type`. Two edges between
        the same pair of events differ only if their kinds differ, which is what makes a
        `DIRECT` and an `AMPLIFYING` edge over one pair two distinct artifacts rather than
        a collision.
        """
        return digest(
            IdentifierPrefix.CANDIDATE_EDGE,
            canonical_payload(
                canonical_text(source_event_id),
                canonical_text(target_event_id),
                canonical_text(edge_kind.value),
            ),
        )

    @classmethod
    def between(
        cls,
        *,
        source_event: Event,
        target_event: Event,
        payload: CausalEdgePayload,
        confidence: ConfidenceVector,
        evidence: tuple[EvidenceItem, ...],
        propagation_weight: float,
        provenance_class: ProvenanceClass,
        run_id: str,
    ) -> CausalEdge:
        """Build an edge between two events, enforcing LAW-TIME.

        This is the only constructor that sees both intervals, and therefore the only one
        that can evaluate LAW-TIME. It takes the `Event` objects rather than their
        identifiers for exactly that reason: an edge built from identifiers alone could not
        check the law, and a check that cannot run is indistinguishable from one that
        passes.

        The verdict and the unverifiability flag are computed here and stamped onto the
        edge; they are never supplied by the caller. A caller who could pass
        `temporal_verdict=CERTAIN` could launder a rejected edge into the graph.

        **There is no escape hatch and no `skip_law_time` argument.** A `VIOLATION` raises.
        The only accommodation for absent time is `temporally_unverifiable`, which is a
        distinct recorded state, not a silent pass: such an edge is retained, is visible in
        the run summary, and is barred from `INFERRED` promotion by the invariant below.

        `temporally_unverifiable` is deliberately separate from the verdict.
        `UNDETERMINED` means the data placed both events and could not separate them;
        `temporally_unverifiable` means the data never placed one of them. Both block
        promotion, but they are different findings about the dataset and collapsing them
        would hide which one the run actually hit.

        Raises:
            LawViolationError: if the cause cannot precede the effect. Logged `CRITICAL`;
                never repaired, never skipped, never downgraded to a flag.
        """
        temporal_verdict = verdict(source_event.occurred_at, target_event.occurred_at)
        if temporal_verdict is TemporalVerdict.VIOLATION:
            raise LawViolationError(
                "LAW-TIME: refusing to construct a causal edge from "
                f"{source_event.event_id} to {target_event.event_id}; the cause interval "
                "does not precede the effect interval "
                f"({source_event.occurred_at.t_earliest.isoformat()} >= "
                f"{target_event.occurred_at.t_latest.isoformat()}). A temporally invalid "
                "edge is rejected at construction and never created (CONVENTIONS.md §10)."
            )
        return cls(
            causal_edge_id=cls.address(
                source_event.event_id, target_event.event_id, payload.edge_kind
            ),
            source_event_id=source_event.event_id,
            target_event_id=target_event.event_id,
            payload=payload,
            confidence=confidence,
            evidence=evidence,
            propagation_weight=propagation_weight,
            provenance_class=provenance_class,
            temporal_verdict=temporal_verdict,
            temporally_unverifiable=(
                is_unverifiable(source_event.occurred_at)
                or is_unverifiable(target_event.occurred_at)
            ),
            run_id=run_id,
        )

    @model_validator(mode="after")
    def _check_invariants(self) -> CausalEdge:
        """Enforce the documented invariants on every construction path.

        This runs for `model_validate` too, which is the point: the guarantee has to hold
        for deserialized data, or a rejected edge could be reintroduced by writing it to
        disk and reading it back.
        """
        if self.temporal_verdict is TemporalVerdict.VIOLATION:
            raise LawViolationError(
                "LAW-TIME: a CausalEdge may never carry the VIOLATION verdict. Such an "
                "edge is rejected at construction and never created (CONVENTIONS.md §10)."
            )
        if self.source_event_id == self.target_event_id:
            raise ContractViolationError(
                f"CausalEdge source and target are both {self.source_event_id}; an event "
                "does not cause itself."
            )
        if self.provenance_class is ProvenanceClass.OBSERVED:
            raise LawViolationError(
                "CausalEdge may not carry OBSERVED provenance; causation is inferred, "
                "never read from a source record (LAW-PROVENANCE, ADR-0020)."
            )
        if self.provenance_class is ProvenanceClass.INFERRED and (
            self.temporal_verdict is not TemporalVerdict.CERTAIN or self.temporally_unverifiable
        ):
            raise LawViolationError(
                "CausalEdge with INFERRED provenance requires a CERTAIN temporal verdict "
                "and verifiable timestamps; an edge resting on ambiguous or absent time "
                "may be retained but may never be promoted (ADR-0007, CONVENTIONS.md §10)."
            )
        if not self.evidence:
            raise LawViolationError(
                "CausalEdge.evidence is empty; an assertion with no inspectable evidence "
                "is a defect (LAW-EVIDENCE)."
            )
        if not 0.0 <= self.propagation_weight <= 1.0:
            raise ContractViolationError(
                f"CausalEdge.propagation_weight {self.propagation_weight} lies outside "
                "[0.0, 1.0]."
            )
        if not self.run_id.strip():
            raise ContractViolationError(
                "CausalEdge.run_id is empty; every inferred artifact is run-scoped, which "
                "is what stops it overwriting an observed fact (ADR-0013)."
            )
        return self
