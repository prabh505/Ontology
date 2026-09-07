"""The artifacts module 12 produces: a consequence tree, its attribution, and its bounds.

Three rules shape every type below, and all three come from prd.md or from a prior ADR
rather than from taste.

**Depth and breadth are separate measures and are never averaged.** prd.md §30 lists them
as two of the seven things propagation includes. One number combining them would be a figure
with no unit that rises for two unrelated reasons, and a reader could not tell a deep narrow
chain from a shallow wide one -- which are different problems with different fixes.

**A magnitude belongs to a node, never to a route.** A consequence reachable two ways is one
consequence. `core.attribution` states the argument in full; the type-level expression of it
is that `ConsequenceSet` is keyed by event identifier and that nothing here holds a
per-route magnitude for anything to be summed over.

**A bound that was reached is truncation, and truncation is reported.** A traversal that
stopped at its depth or node cap has not measured propagation; it has measured the first
part of it. `PropagationTree.truncations` is non-empty in exactly that case, and the report
prints it above the numbers rather than below them.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.causal_graph_builder.graph import (
    ATTRIBUTION_NOT_MEASUREMENT_NOTICE,
)
from causalog.causal_engine.propagation_analyzer.view import (
    DIAGNOSTIC_NOT_STATED_NOTICE,
    GraphStanding,
)
from causalog.core.errors import ContractViolationError, LawViolationError
from causalog.core.provenance import ProvenanceClass

__all__ = [
    "ATTRIBUTION_NOT_MEASUREMENT_NOTICE",
    "MAX_PROPAGATION_DEPTH",
    "ConsequenceSet",
    "MagnitudeShare",
    "PathConfidence",
    "PropagationNode",
    "PropagationTree",
    "TruncationReason",
    "TruncationRecord",
]

#: The absolute ceiling on traversal depth, whatever a pack declares. Not a policy and not a
#: default: it is the point past which a walk over a graph that should be acyclic is
#: evidence that it is not, and continuing would be looping rather than measuring. A pack's
#: `maximum_depth` is the operative bound and must be at or below this; a pack that declares
#: nothing gets no traversal at all rather than getting this number.
MAX_PROPAGATION_DEPTH: int = 64

# Imported from `causal_graph_builder.graph` rather than restated. An earlier draft of this
# module wrote its own copy of the sentence "so that it is fixed here too", and the two
# copies had already drifted by the time the test comparing them was written -- a reader
# would have seen a softer caveat depending on which report they opened, which is the
# LAW-EVIDENCE defect one level up from a bare float. One sentence, one definition.
#
# The same argument the Five Laws' byte-identical copy check makes, applied to a caveat: two
# copies of a warning is one warning and one liability.


class TruncationReason(str, Enum):
    """Why a traversal stopped before it ran out of graph."""

    DEPTH_BOUND = "DEPTH_BOUND"
    """The declared `maximum_depth` was reached. Consequences beyond it exist and were not
    measured."""

    NODE_CAP = "NODE_CAP"
    """The declared `traversal_node_cap` was reached. Which consequences were left out
    depends on the canonical visit sequence and is therefore reproducible, but it is still
    an arbitrary subset of a larger truth."""

    CIRCUIT = "CIRCUIT"
    """A link led back to a node already on this route. prd.md §31 makes a loop a
    REQUIREMENT rather than a defect: the walk terminates, the circuit is recorded, and the
    traversal continues elsewhere."""


class TruncationRecord(BaseModel):
    """One place the traversal stopped early, with what was on the frontier when it did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: TruncationReason
    at_event_id: str = Field(min_length=1)
    depth: int = Field(ge=0)
    #: The consequences that were reachable and not walked, sorted. Empty for a CIRCUIT,
    #: whose whole point is that the onward node was already visited.
    unwalked_event_ids: tuple[str, ...] = ()
    detail: str = Field(min_length=1)

    def sort_key(self) -> tuple[str, int, str]:
        """Return the canonical sequence key."""
        return (self.at_event_id, self.depth, self.reason.value)


class PathConfidence(BaseModel):
    """Belief about one route, composed under a named function -- and its length beside it.

    `composed` and `path_length` are two fields and are never blended, which is ADR-0008's
    never-blend ruling applied one level down from the ruling itself. `product` is the
    length-sensitive alternative, computed and carried so a reader who wants it does not
    have to recompute it and so nobody is tempted to fold length into `composed` to get it.

    `link_scalars` is the whole input, retained because the composition is derived and
    discarding a derivation's inputs loses information a consumer may legitimately want to
    disagree with (`core.aggregation` rule 1, carried here).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    composed: float = Field(ge=0.0, le=1.0)
    #: Names a function in `causalog.core.composition.PATH_COMPOSERS`. A composed value
    #: whose function is unnamed is the unexplained number prd.md §49 forbids.
    composition: str = Field(min_length=1)
    #: The same links under `independent_product_v1`. Reported in its own column. NEVER
    #: blended with `composed`, and never substituted for it.
    product: float = Field(ge=0.0, le=1.0)
    path_length: int = Field(ge=1)
    link_scalars: tuple[float, ...] = Field(min_length=1)
    provenance_class: ProvenanceClass

    @model_validator(mode="after")
    def _check_length(self) -> PathConfidence:
        """Refuse a stated length that disagrees with the links it was composed from."""
        if len(self.link_scalars) != self.path_length:
            raise ContractViolationError(
                f"PathConfidence declares length {self.path_length} over "
                f"{len(self.link_scalars)} link scalar(s). The length is printed beside the "
                "composed value precisely so a reader can judge it, and a length that "
                "disagrees with its own inputs makes that judgement wrong."
            )
        return self


class MagnitudeShare(BaseModel):
    """One consequence's magnitude, or the stated reason there is none, plus its share.

    `unavailable_because` and `reading` are mutually exclusive and one of them is always
    present. There is deliberately no path by which an unmeasurable consequence contributes
    a zero: a quantity nobody measured and a quantity measured at nothing are different
    findings, and a total that mixed them would understate itself without saying so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    measurement_id: str | None = None
    unit: str | None = None
    #: The consequence's whole magnitude, before this route's share is taken.
    reading: float | None = None
    #: The share attributed to the route that reached it, in `[0.0, 1.0]`.
    weight: float = Field(ge=0.0, le=1.0)
    #: `reading * weight`, computed in `core.attribution`. None whenever `reading` is.
    attributed: float | None = None
    unavailable_because: str | None = None

    @property
    def notice(self) -> str:
        """Return the fixed attribution notice. A property, so a revision cannot soften it."""
        return ATTRIBUTION_NOT_MEASUREMENT_NOTICE

    @model_validator(mode="after")
    def _check_exclusivity(self) -> MagnitudeShare:
        """Refuse a share that is neither a reading nor a stated absence, or is both."""
        has_reading = self.reading is not None
        has_reason = self.unavailable_because is not None
        if has_reading == has_reason:
            raise ContractViolationError(
                f"MagnitudeShare for {self.event_id} must carry exactly one of a reading or "
                "a stated reason there is none. Carrying both is a contradiction; carrying "
                "neither is an absence nobody has to account for, which is how a zero gets "
                "into a total."
            )
        if has_reading and self.attributed is None:
            raise ContractViolationError(
                f"MagnitudeShare for {self.event_id} carries a reading and no attributed "
                "share. The share is what enters the total, and omitting it would leave the "
                "reading looking like the contribution."
            )
        return self


class PropagationNode(BaseModel):
    """One consequence, with how far it is, how it was reached, and what it is worth.

    `depth` is the length of the SHORTEST route from the seed. A node reachable at two
    depths is one node at the shorter of them, which is the same never-double-count rule
    `ConsequenceSet` enforces for magnitude, applied to distance.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    depth: int = Field(ge=1)
    #: Sorted identifiers of the consequences reached directly from this one, within the
    #: traversal's bounds. Empty at a leaf and empty at a truncation, which is why the
    #: truncation records exist separately.
    reached_event_ids: tuple[str, ...] = ()
    #: Belief about the shortest route from the seed to here.
    path_confidence: PathConfidence
    #: How many distinct routes reach this node. Reported because it is the structural fact
    #: a reader needs to understand why the magnitude is counted once; NEVER used to
    #: multiply anything.
    route_count: int = Field(ge=1)
    magnitude: MagnitudeShare
    #: The process instances that witnessed this consequence, sorted.
    process_instance_ids: tuple[str, ...] = ()
    #: The entities that participated in it, sorted.
    entity_ids: tuple[str, ...] = ()
    is_actionable: bool
    provenance_class: ProvenanceClass

    def sort_key(self) -> tuple[int, str]:
        """Return the canonical sequence key: depth, then identifier. Never a magnitude."""
        return (self.depth, self.event_id)


class ConsequenceSet(BaseModel):
    """The set of consequences downstream of a seed, and one combined magnitude over it.

    THE SET IS THE UNIT. Membership is keyed by event identifier and validated unique, so a
    consequence reachable by four routes appears once. That is the whole no-double-counting
    guarantee, held by a type rather than by care taken at a call site.

    `combined` is `None` whenever the pack declares no combination for the measurement, or
    no member carried a reading. Both are absences and neither is zero; `combination_absent_because`
    says which, in a sentence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Sorted, unique. The identifiers of every consequence in the set.
    event_ids: tuple[str, ...] = ()
    measurement_id: str | None = None
    unit: str | None = None
    #: The declared operator the members were combined under, e.g. `SUM`. Named on the
    #: artifact for the reason every other derived number here names its function.
    combination: str | None = None
    combined: float | None = None
    #: How many members offered a reading, against how many are in the set. A total over
    #: three of forty consequences is a different claim from a total over forty, and a
    #: reader who cannot see the denominator will read the first as the second.
    measured_member_count: int = Field(default=0, ge=0)
    combination_absent_because: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> ConsequenceSet:
        """Refuse an unsequenced or repeating set, and an absence with no stated reason."""
        listed = list(self.event_ids)
        if listed != sorted(listed):
            raise ContractViolationError(
                "ConsequenceSet.event_ids is unsequenced; the set is serialized into a "
                "report and two sequences produce two hashes for one run "
                "(CONVENTIONS.md §11)."
            )
        if len(set(listed)) != len(listed):
            raise ContractViolationError(
                "ConsequenceSet holds a repeated event identifier. The set is the unit of "
                "attribution precisely so that a consequence reachable by several routes "
                "contributes once; a repeat would double count it (prd.md §30)."
            )
        if self.measured_member_count > len(listed):
            raise ContractViolationError(
                f"ConsequenceSet reports {self.measured_member_count} measured member(s) "
                f"over a set of {len(listed)}. A denominator smaller than its numerator "
                "makes the coverage figure beside the total meaningless."
            )
        if self.combined is None and self.combination_absent_because is None:
            raise ContractViolationError(
                "ConsequenceSet has no combined magnitude and no stated reason. An "
                "unexplained absence is read as a zero by the next person to look at it."
            )
        return self


class PropagationTree(BaseModel):
    """One seed's downstream consequences: the nodes, the set, and where it stopped.

    `standing` is required and has no default. An artifact that did not state which graph
    it walked would let a diagnostic finding be read as an assertion, which is the one
    failure this module is built to make impossible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    standing: GraphStanding
    seed_event_id: str = Field(min_length=1)
    #: Sorted by `(depth, event_id)`. Never by magnitude: ranking is module 11's.
    nodes: tuple[PropagationNode, ...] = ()
    consequences: ConsequenceSet
    truncations: tuple[TruncationRecord, ...] = ()
    #: The furthest depth actually reached. Separate from `breadth` and never averaged with
    #: it (prd.md §30).
    depth: int = Field(default=0, ge=0)
    #: The widest single level. The second of prd.md §30's two structural measures.
    breadth: int = Field(default=0, ge=0)
    provenance_class: ProvenanceClass
    #: Set when the traversal could not run at all, naming what it would have needed. Never
    #: reported as a propagation of zero.
    not_runnable_because: str | None = None

    @property
    def notice(self) -> str | None:
        """Return the disowning notice for a diagnostic tree, or None for a stated one.

        A property rather than a field: a stored artifact cannot soften it, and it does not
        enter any content address.
        """
        if self.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC:
            return DIAGNOSTIC_NOT_STATED_NOTICE
        return None

    @property
    def truncated(self) -> bool:
        """Return whether this traversal stopped before it ran out of graph."""
        return bool(self.truncations)

    @model_validator(mode="after")
    def _check_invariants(self) -> PropagationTree:
        """Refuse an unsequenced tree, a laundered standing, and numbers that disagree."""
        keys = [node.sort_key() for node in self.nodes]
        if keys != sorted(keys):
            raise ContractViolationError(
                "PropagationTree.nodes is unsequenced; sequencing is canonical and never by "
                "magnitude, because ranking is module 11's (CONVENTIONS.md §11)."
            )
        identifiers = [node.event_id for node in self.nodes]
        if len(set(identifiers)) != len(identifiers):
            raise ContractViolationError(
                "PropagationTree holds two nodes for one event. A consequence reachable by "
                "several routes is one consequence at the shortest of its depths."
            )
        if (
            self.standing is GraphStanding.UNPROMOTED_DIAGNOSTIC
            and self.provenance_class is ProvenanceClass.INFERRED
        ):
            raise LawViolationError(
                "PropagationTree carries INFERRED under an UNPROMOTED_DIAGNOSTIC standing. "
                "Nothing walked under that standing was asserted, so nothing derived from "
                "it may claim to be an inference (LAW-PROVENANCE)."
            )
        if self.nodes and self.depth != max(node.depth for node in self.nodes):
            raise ContractViolationError(
                f"PropagationTree declares depth {self.depth} over nodes reaching "
                f"{max(node.depth for node in self.nodes)}. The depth is prd.md §30's "
                "headline figure and a stated one that disagrees with the tree is worse "
                "than none."
            )
        if not self.nodes and self.depth != 0:
            raise ContractViolationError(
                f"PropagationTree declares depth {self.depth} with no nodes. An empty "
                "traversal has depth zero; anything else is a number with no referent."
            )
        set_members = set(self.consequences.event_ids)
        if set_members != set(identifiers):
            raise ContractViolationError(
                "PropagationTree's consequence set does not match its nodes. The set is "
                "what the magnitude is combined over, and a set that disagrees with the "
                "tree above it attributes a total to consequences the tree does not list."
            )
        return self
