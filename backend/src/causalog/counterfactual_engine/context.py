"""Everything module 13 reads, supplied by value, never fetched.

The shape modules 9 through 12 and the Causal Graph Builder established, for the same two
reasons: forbidden edge F4 means no reasoning package may reach a store, and a context
assembled by the caller is a context a test can build by hand.

**Module 12's context is carried whole rather than unpacked**, exactly as module 11 carries
it. A hypothetical asks re-reachability questions of the same graph the propagation walked,
under the same bounds, so the two must not be able to disagree about which graph or which
depth. One context means one answer.

WHAT THIS PACKAGE MAY NOT REACH
--------------------------------
`ontology_runtime` (forbidden edge F3), so every declaration arrives already flattened as
`causalog.core.ontology_view` values produced by `extraction.ontology_adapters`. The store
(F4), so the derived cache arrives as the `core.ports.persistence.DerivedCache` protocol and
`None` means recompute -- flushing it changes latency and never an answer.

**No domain vocabulary appears below.**
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from causalog.causal_engine.causal_graph_builder.graph import (
    JointCauseGroup,
    PromotedGraph,
)
from causalog.causal_engine.confidence_scorer import CausalGraph
from causalog.causal_engine.propagation_analyzer import PropagationContext
from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import (
    IdentifierPrefix,
    canonical_payload,
    canonical_sequence,
    canonical_text,
    digest,
)
from causalog.core.ontology_view import LifecycleView, MutabilityView, ProcessDefinitionView
from causalog.core.precedence import DerivedPrecedenceIndex
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import Entity, Event
from causalog.core.types.causal_edge import CausalEdgePayload
from causalog.rule_engine import CounterfactualSimulationSpec

__all__ = [
    "SimulationContext",
    "SimulationLink",
    "base_world_address",
    "stated_links",
    "unpromoted_links",
]


class SimulationLink:
    """One directed link a hypothetical can travel, carrying its PAYLOAD.

    Module 12's `GraphLink` deliberately omits the payload and states in its own docstring
    that the kind is "never branched on by value here". Module 13 must branch on it — a
    contributing link and a direct one make different claims about what a removal does — so
    it carries its own link shape rather than widening module 12's, which would licence that
    module to do what it deliberately does not.

    A small immutable holder rather than a model: it never leaves the package, and the
    artifacts that do leave carry identifiers instead.
    """

    __slots__ = (
        "joint_cause_group_id",
        "link_scalar",
        "payload",
        "provenance_class",
        "source_event_id",
        "target_event_id",
        "weight",
    )

    def __init__(
        self,
        *,
        source_event_id: str,
        target_event_id: str,
        payload: CausalEdgePayload,
        link_scalar: float,
        weight: float,
        provenance_class: ProvenanceClass,
        joint_cause_group_id: str | None = None,
    ) -> None:
        """Record one directed link, with everything a hypothetical needs from it."""
        self.source_event_id = source_event_id
        self.target_event_id = target_event_id
        self.payload = payload
        self.link_scalar = link_scalar
        self.weight = weight
        self.provenance_class = provenance_class
        self.joint_cause_group_id = joint_cause_group_id

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key — never a score (`CONVENTIONS.md` §11)."""
        return (self.source_event_id, self.target_event_id, self.payload.edge_kind.value)


def stated_links(graph: PromotedGraph) -> tuple[SimulationLink, ...]:
    """Return the engine's stated claims as travellable links.

    Every link carries the `PropagationWeight` the Causal Graph Builder attributed, so the
    share a hypothetical apportions is the share that module computed rather than a second
    opinion. An empty promoted graph yields an empty set, which is a finding the report
    states and never an error.
    """
    return tuple(
        SimulationLink(
            source_event_id=promoted.edge.source_event_id,
            target_event_id=promoted.edge.target_event_id,
            payload=promoted.edge.payload,
            link_scalar=promoted.edge.confidence.scalar,
            weight=promoted.weight.weight,
            provenance_class=promoted.edge.provenance_class,
            joint_cause_group_id=promoted.joint_cause_group_id,
        )
        for promoted in graph.edges
    )


def unpromoted_links(graph: CausalGraph) -> tuple[SimulationLink, ...]:
    """Return claims that were SCORED AND NOT ASSERTED as travellable links.

    The counterpart of `propagation_analyzer.diagnostic_view`, and it exists for the same
    reason: on the committed slice the stated graph is empty, so a strict run exercises none
    of the machinery. **Everything derived from these links is disowned**, and
    `simulate(..., accept_unpromoted=True)` is the only way to reach them — the default
    refuses (OQ-026, ADR-0072).

    Two differences from `stated_links`, neither incidental.

    *No attributed weight exists.* A `PropagationWeight` is attributed at promotion and
    nothing here was promoted. Rather than invent one, each link takes an equal share of its
    consequence among the links arriving there — the same choice `diagnostic_view` makes, so
    the two disowned views cannot disagree about a share.

    *A promoted edge is refused.* Handing this an already-promoted graph would produce
    `INFERRED` links under a disowned reading; catching it here names the caller's mistake
    instead of surfacing it later as a validation error.

    Raises:
        ContractViolationError: if any edge in `graph` carries `INFERRED`.
    """
    promoted = tuple(
        edge.edge.causal_edge_id
        for edge in graph.edges
        if edge.edge.provenance_class is ProvenanceClass.INFERRED
    )
    if promoted:
        raise ContractViolationError(
            f"unpromoted_links received {len(promoted)} already-promoted edge(s), the first "
            f"being {promoted[0]}. A promoted claim belongs in the stated set; travelling it "
            "under a disowned reading would produce a disowned finding about an asserted "
            "link, which is neither of the two things this module publishes."
        )
    arriving: dict[str, int] = {}
    for edge in graph.edges:
        arriving[edge.edge.target_event_id] = arriving.get(edge.edge.target_event_id, 0) + 1
    return tuple(
        SimulationLink(
            source_event_id=edge.edge.source_event_id,
            target_event_id=edge.edge.target_event_id,
            payload=edge.edge.payload,
            link_scalar=edge.edge.confidence.scalar,
            weight=1.0 / arriving[edge.edge.target_event_id],
            provenance_class=edge.edge.provenance_class,
            joint_cause_group_id=None,
        )
        for edge in graph.edges
    )


def base_world_address(links: tuple[SimulationLink, ...], run_id: str, standing: str) -> str:
    """Return the content address of the graph a hypothetical is simulated over.

    `CONVENTIONS.md` §9 addresses a simulated world as `sim:digest(base_graph_id |
    mutations)`, and until module 13 nothing needed the first half. A `run_id` will not
    serve as one: the stated graph and the scored graph are both scoped to a run and **one
    run holds both**, so addressing on the run alone would give the graph the engine states
    and the graph it declined to state a single identifier.

    Digesting the links separates them, and does so by content: two runs holding the same
    links address the same base world, which is what makes a simulated world reproducible.
    """
    return digest(
        IdentifierPrefix.CAUSAL_GRAPH,
        canonical_payload(
            canonical_text(run_id),
            canonical_text(standing),
            canonical_sequence(
                f"{link.source_event_id}>{link.target_event_id}" f":{link.payload.edge_kind.value}"
                for link in links
            ),
        ),
    )


class SimulationContext(BaseModel):
    """One run's inputs to counterfactual simulation.

    Fields, and why each is needed rather than derivable:

    * `propagation` -- module 12's context, carried whole. See the module docstring.
    * `links` -- the travellable links WITH their payloads, built by `stated_links` from a
      promoted graph or by `unpromoted_links` from a scored one. Module 12's `GraphLink`
      carries `edge_kind` as a string and states in its own docstring that it is "never
      branched on by value here"; module 13 must branch on it, because a contributing link
      and a direct one make different claims about what a removal does. Widening that
      protocol would licence module 12 to do what it deliberately does not. **The links must
      come from the same graph the view's standing describes** -- indexing the promoted graph
      while walking a scored view would report a hypothetical over an empty graph as one that
      reached nothing, which is a true-looking statement about the wrong world.
    * `joint_groups` -- the groups a contributing removal is applied over, as a unit. Empty
      for an unpromoted set, because nothing there was promoted all-or-nothing.
    * `lifecycles` / `processes` / `mutability` -- the three declarations a change is
      validated against (ADR-0066). An absent declaration refuses the change and is
      reported; it never admits one.
    * `derived_precedence` -- module 1's measurement of which instants the source COMPUTED
      rather than recorded. It is what lets a move propagate through time at all: an
      occurrence's instant shifts under a change only when this says the source derived it
      from the moved one. `None` means the measurement was not supplied, which is a
      different fact from a measurement that confirmed nothing, and the report says which.
    * `entities` -- needed by `CHANGE_ENTITY_STATE` to find the type whose lifecycle
      governs the transition.
    * `parameters` -- the pack's `counterfactual_simulation` block (ADR-0071). An absent
      declaration means the policy cannot run and is reported, never defaulted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    propagation: PropagationContext
    links: tuple[SimulationLink, ...] = ()
    joint_groups: tuple[JointCauseGroup, ...] = ()
    lifecycles: tuple[LifecycleView, ...] = ()
    processes: tuple[ProcessDefinitionView, ...] = ()
    mutability: tuple[MutabilityView, ...] = ()
    derived_precedence: DerivedPrecedenceIndex | None = None
    entities: tuple[Entity, ...] = ()
    parameters: CounterfactualSimulationSpec
    run_id: str = Field(min_length=1)

    _edges_by_target: dict[str, tuple[SimulationLink, ...]] | None = PrivateAttr(default=None)
    _edges_by_source: dict[str, tuple[SimulationLink, ...]] | None = PrivateAttr(default=None)
    _entities_by_id: dict[str, Entity] | None = PrivateAttr(default=None)
    _mutability_by_type: dict[str, MutabilityView] | None = PrivateAttr(default=None)
    _lifecycles_by_type: dict[str, LifecycleView] | None = PrivateAttr(default=None)

    def events_by_id(self) -> dict[str, Event]:
        """Return every occurrence by identifier, through module 12's own index.

        Delegated rather than rebuilt, so the two modules cannot hold two views of one run.
        """
        return self.propagation.events_by_id()

    def _index_edges(self) -> None:
        """Build both adjacency indices, each bucket canonically sequenced."""
        by_target: dict[str, list[SimulationLink]] = {}
        by_source: dict[str, list[SimulationLink]] = {}
        for link in self.links:
            by_target.setdefault(link.target_event_id, []).append(link)
            by_source.setdefault(link.source_event_id, []).append(link)
        self._edges_by_target = {
            name: tuple(sorted(bucket, key=lambda item: item.sort_key()))
            for name, bucket in sorted(by_target.items())
        }
        self._edges_by_source = {
            name: tuple(sorted(bucket, key=lambda item: item.sort_key()))
            for name, bucket in sorted(by_source.items())
        }

    def links_into(self, event_id: str) -> tuple[SimulationLink, ...]:
        """Return the promoted links arriving at one consequence, with their payloads."""
        if self._edges_by_target is None:
            self._index_edges()
        return (self._edges_by_target or {}).get(event_id, ())

    def links_from(self, event_id: str) -> tuple[SimulationLink, ...]:
        """Return the promoted links leading away from one antecedent, with their payloads."""
        if self._edges_by_source is None:
            self._index_edges()
        return (self._edges_by_source or {}).get(event_id, ())

    def entity(self, entity_id: str) -> Entity | None:
        """Return one participant by identifier, or None if the run does not hold it."""
        if self._entities_by_id is None:
            self._entities_by_id = {item.entity_id: item for item in self.entities}
        return self._entities_by_id.get(entity_id)

    def mutability_for(self, event_type: str) -> MutabilityView | None:
        """Return the changeable-attribute declaration for a kind of occurrence.

        `None` means the pack declares nothing for that type, which REFUSES every attribute
        change on it (ADR-0067). It is never read as permission.
        """
        if self._mutability_by_type is None:
            self._mutability_by_type = {view.event_type: view for view in self.mutability}
        return self._mutability_by_type.get(event_type)

    def lifecycle_for(self, entity_type: str) -> LifecycleView | None:
        """Return the declared state machine for a participant type, or None."""
        if self._lifecycles_by_type is None:
            self._lifecycles_by_type = {view.entity_type: view for view in self.lifecycles}
        return self._lifecycles_by_type.get(entity_type)

    def joint_group(self, group_id: str) -> JointCauseGroup | None:
        """Return one joint cause group, or None if the graph holds none by that name.

        A joint group is removed as a UNIT (ADR-0061, and `JointCauseGroup`'s own note names
        this module). Removing one member and reporting the consequence as prevented would
        overstate the change by the whole of the group's contribution.
        """
        for group in self.joint_groups:
            if group.joint_cause_group_id == group_id:
                return group
        return None
