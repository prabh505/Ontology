"""The two standings a graph can be traversed under, and the one adapter for each.

A traversal is arithmetic over adjacency. It does not care whether the engine stands behind
the links it walks -- which is exactly why the standing has to be carried explicitly, and
carried by the type rather than by a convention.

**`STATED`** walks the promoted graph. Every link is one the engine asserts: it cleared the
band its pack declares for its kind, LAW-TIME was verified at promotion by two independent
mechanisms, and it carries `INFERRED`. A finding produced here is the engine's finding.

**`UNPROMOTED_DIAGNOSTIC`** walks the scored graph -- module 10's output, before the
promotion decision. Nothing here was asserted. On the committed bounded run the stated view
is EMPTY (not one of 9,492 claims promoted, 79.3% of them stopped by the temporal verdict
rather than by any threshold), so a strict traversal answers every question with silence,
and silence is a true answer that teaches a reader nothing about whether the machinery
works. This standing exists so the same code can be run over the same events and produce a
visible, checkable, and explicitly disowned result.

WHAT KEEPS THE SECOND FROM CONTAMINATING THE FIRST, structurally rather than by discipline:

1. `standing` is a REQUIRED field on every artifact these two modules produce. There is no
   default, so an artifact cannot be built without someone stating which graph it came from.
2. `diagnostic_view` is the only construction site of `UNPROMOTED_DIAGNOSTIC` anywhere in
   the engine, asserted over the AST by `tests/law/test_ranking_never_collapses.py`.
3. Every artifact validates that a diagnostic standing never carries `INFERRED`. A
   diagnostic finding cannot be laundered into an assertion by editing a provenance field.
4. `DIAGNOSTIC_NOT_STATED_NOTICE` is a property rather than a field on every such artifact,
   so a revision cannot soften it and it does not enter any content address.

**What a diagnostic result may be used for:** reading, and deciding what to fix in the
inputs. **What it may not be used for:** anything downstream. It is not an input to
counterfactual simulation or to intervention ranking, and both of those modules should
refuse one when they are built.

**No domain vocabulary appears below.** Nothing here reads a type name.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from causalog.causal_engine.causal_graph_builder.graph import PromotedGraph
from causalog.causal_engine.confidence_scorer import CausalGraph
from causalog.core.errors import ContractViolationError
from causalog.core.provenance import ProvenanceClass

__all__ = [
    "DIAGNOSTIC_NOT_STATED_NOTICE",
    "GraphLink",
    "GraphStanding",
    "GraphView",
    "diagnostic_view",
    "stated_view",
]

#: Fixed text, printed above every diagnostic table and carried as a property rather than a
#: field so that no revision can reword it and no content address depends on it.
DIAGNOSTIC_NOT_STATED_NOTICE = (
    "THIS IS NOT THE ENGINE'S VIEW. Every link below was considered and NOT asserted -- it "
    "did not clear the band its pack declares, or its precedence could not be established, or "
    "too little was measured on it to say. The traversal is real, the arithmetic is real, "
    "and the conclusion is disowned. It is published so that a reader can see what the "
    "machinery does and can check it, and so that the reason the stated view is empty is "
    "visible as a property of the inputs rather than as an absence of output. Nothing here "
    "may be cited as a cause, and nothing here is an input to simulation or to "
    "recommendation."
)


class GraphStanding(str, Enum):
    """Whether the engine stands behind the links a traversal walked."""

    STATED = "STATED"
    """The promoted graph. Every link is asserted, carries `INFERRED`, and cleared the band
    its pack declares for its kind."""

    UNPROMOTED_DIAGNOSTIC = "UNPROMOTED_DIAGNOSTIC"
    """The scored graph before promotion. No link is asserted. Findings are disowned by the
    type that carries them and are refused by everything downstream."""


class GraphLink(Protocol):
    """One directed link a traversal can walk, whatever graph it came from.

    Deliberately the smallest surface a traversal needs, so that a promoted edge and a
    merely-scored one are walkable by one implementation without either learning about the
    other. Anything richer -- lineage, bands, demotion reasons -- is fetched by identifier
    from the artifact that holds it, not carried here.
    """

    @property
    def source_event_id(self) -> str:  # pragma: no cover -- protocol declaration
        """The cause end."""
        ...

    @property
    def target_event_id(self) -> str:  # pragma: no cover -- protocol declaration
        """The effect end."""
        ...

    @property
    def edge_kind(self) -> str:  # pragma: no cover -- protocol declaration
        """The claim's kind, as a string; never branched on by value here."""
        ...

    @property
    def link_scalar(self) -> float:  # pragma: no cover -- protocol declaration
        """The link's own confidence, for path composition."""
        ...

    @property
    def weight(self) -> float:  # pragma: no cover -- protocol declaration
        """This link's apportioned share of its target's magnitude, in `[0.0, 1.0]`."""
        ...

    @property
    def provenance_class(self) -> ProvenanceClass:  # pragma: no cover -- protocol
        """The link's provenance, carried through into every derived figure."""
        ...


class _Link:
    """One walkable link, as a small immutable holder rather than a model.

    It never leaves the traversal; the artifacts that do leave carry identifiers instead.
    """

    __slots__ = (
        "edge_kind",
        "link_scalar",
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
        edge_kind: str,
        link_scalar: float,
        weight: float,
        provenance_class: ProvenanceClass,
    ) -> None:
        """Record one directed link."""
        self.source_event_id = source_event_id
        self.target_event_id = target_event_id
        self.edge_kind = edge_kind
        self.link_scalar = link_scalar
        self.weight = weight
        self.provenance_class = provenance_class

    def sort_key(self) -> tuple[str, str, str]:
        """Return the canonical sequence key -- never a score."""
        return (self.source_event_id, self.target_event_id, self.edge_kind)


@runtime_checkable
class GraphView(Protocol):
    """Adjacency in both directions, plus the standing the links were drawn under.

    Both indices return CANONICALLY SEQUENCED tuples. `PromotedGraph` ships
    `edges_by_target` and no `edges_by_source`, because nothing before module 12 needed to
    walk forwards; an unsequenced index built here would break determinism silently rather
    than loudly, so the sequence is part of this protocol's contract and is asserted.
    """

    @property
    def standing(self) -> GraphStanding:  # pragma: no cover -- protocol declaration
        """Whether the engine stands behind these links."""
        ...

    @property
    def run_id(self) -> str:  # pragma: no cover -- protocol declaration
        """The run the links are scoped to (ADR-0013)."""
        ...

    def links_from(self, event_id: str) -> tuple[GraphLink, ...]:  # pragma: no cover
        """Return the links leading away from one cause, canonically sequenced."""
        ...

    def links_into(self, event_id: str) -> tuple[GraphLink, ...]:  # pragma: no cover
        """Return the links arriving at one effect, canonically sequenced."""
        ...

    def link_count(self) -> int:  # pragma: no cover -- protocol declaration
        """How many links the view holds. Zero is a finding, never an error."""
        ...


class _IndexedView:
    """A `GraphView` over a prepared adjacency pair. Built by the two adapters below."""

    __slots__ = ("_by_source", "_by_target", "_count", "_run_id", "_standing")

    def __init__(self, links: tuple[_Link, ...], standing: GraphStanding, run_id: str) -> None:
        """Index one link set in both directions, sequencing every bucket canonically."""
        by_source: dict[str, list[_Link]] = {}
        by_target: dict[str, list[_Link]] = {}
        for link in links:
            by_source.setdefault(link.source_event_id, []).append(link)
            by_target.setdefault(link.target_event_id, []).append(link)
        self._by_source = {
            key: tuple(sorted(bucket, key=lambda item: item.sort_key()))
            for key, bucket in sorted(by_source.items())
        }
        self._by_target = {
            key: tuple(sorted(bucket, key=lambda item: item.sort_key()))
            for key, bucket in sorted(by_target.items())
        }
        self._standing = standing
        self._run_id = run_id
        self._count = len(links)

    @property
    def standing(self) -> GraphStanding:
        """Whether the engine stands behind these links."""
        return self._standing

    @property
    def run_id(self) -> str:
        """The run the links are scoped to."""
        return self._run_id

    def links_from(self, event_id: str) -> tuple[GraphLink, ...]:
        """Return the links leading away from one cause, canonically sequenced."""
        return self._by_source.get(event_id, ())

    def links_into(self, event_id: str) -> tuple[GraphLink, ...]:
        """Return the links arriving at one effect, canonically sequenced."""
        return self._by_target.get(event_id, ())

    def link_count(self) -> int:
        """How many links the view holds."""
        return self._count


def stated_view(graph: PromotedGraph) -> GraphView:
    """Return a traversable view of the engine's stated claims.

    Every link carries the `PropagationWeight` the Causal Graph Builder attributed to it,
    so the share of a consequence's magnitude that this module apportions is the same share
    that module computed rather than a second opinion. An empty promoted graph yields an
    empty view, which is a finding the report states and never an error.
    """
    links = tuple(
        _Link(
            source_event_id=promoted.edge.source_event_id,
            target_event_id=promoted.edge.target_event_id,
            edge_kind=promoted.edge.payload.edge_kind.value,
            link_scalar=promoted.edge.confidence.scalar,
            weight=promoted.weight.weight,
            provenance_class=promoted.edge.provenance_class,
        )
        for promoted in graph.edges
    )
    return _IndexedView(links, GraphStanding.STATED, graph.run_id)


def diagnostic_view(graph: CausalGraph) -> GraphView:
    """Return a traversable view of claims that were scored and NOT asserted.

    **The only construction site of `UNPROMOTED_DIAGNOSTIC` in the engine**, asserted over
    the AST by `tests/law/test_ranking_never_collapses.py`. Read this module's docstring
    before using it: everything it produces is disowned by the artifact that carries it.

    Two differences from `stated_view` that are not incidental.

    *No weight is available.* A `PropagationWeight` is attributed at promotion, and nothing
    here was promoted. Rather than invent one, each link is given an equal share of its
    target among the links arriving there -- recorded as such, so a reader never mistakes it
    for the attributed share the stated path produces.

    *A promoted edge is refused.* If a caller hands this an already-promoted graph the
    result would carry `INFERRED` under a diagnostic standing, which every artifact here
    then refuses; catching it at the boundary names the caller's mistake instead of
    surfacing it three layers later as a validation error on a report.

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
            f"diagnostic_view received {len(promoted)} already-promoted edge(s), the first "
            f"being {promoted[0]}. A promoted claim belongs in the stated view; walking it "
            "under a diagnostic standing would produce a disowned finding about an "
            "asserted link, which is neither of the two things this module publishes."
        )
    arriving: dict[str, int] = {}
    for edge in graph.edges:
        arriving[edge.edge.target_event_id] = arriving.get(edge.edge.target_event_id, 0) + 1
    links = tuple(
        _Link(
            source_event_id=edge.edge.source_event_id,
            target_event_id=edge.edge.target_event_id,
            edge_kind=edge.edge.payload.edge_kind.value,
            link_scalar=edge.edge.confidence.scalar,
            weight=1.0 / arriving[edge.edge.target_event_id],
            provenance_class=edge.edge.provenance_class,
        )
        for edge in graph.edges
    )
    return _IndexedView(links, GraphStanding.UNPROMOTED_DIAGNOSTIC, graph.run_id)
