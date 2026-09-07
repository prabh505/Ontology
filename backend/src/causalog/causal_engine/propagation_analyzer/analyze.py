"""Module 12's entry point: one seed in, one propagation tree and its report out.

The assembly step. Every judgement it makes has already been made somewhere else -- the
bounds in the pack, the traversal in `traverse`, the quantities in `attribute`, the removal
arithmetic in `counterfactual` -- and this module's whole job is to run them in sequence and
hand back an artifact whose numbers agree with each other.

**It creates no link and it ranks nothing.** Creating a link is the Causal Graph Builder's
and ranking is module 11's; the tree comes back sequenced by depth and identifier, which is
canonical and is deliberately not a sequencing by consequence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.causal_engine.propagation_analyzer.attribute import consequence_set, share_for
from causalog.causal_engine.propagation_analyzer.context import PropagationContext
from causalog.causal_engine.propagation_analyzer.graph import (
    ConsequenceSet,
    MagnitudeShare,
    PathConfidence,
    PropagationNode,
    PropagationTree,
)
from causalog.causal_engine.propagation_analyzer.report import PropagationReport, build_report
from causalog.causal_engine.propagation_analyzer.traverse import (
    DEPTH_NOT_DECLARED,
    Reached,
    walk,
)
from causalog.causal_engine.propagation_analyzer.view import GraphStanding
from causalog.core.composition import DEFAULT_COMPOSER, compose
from causalog.core.provenance import ProvenanceClass, combine
from causalog.core.run import OutputEnvelope
from causalog.core.types import Event

__all__ = ["PropagationResult", "analyze_propagation"]


class PropagationResult(BaseModel):
    """The module's whole output: the tree, and the report over it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree: PropagationTree
    report: PropagationReport


def _path_confidence(reached: Reached, context: PropagationContext) -> PathConfidence:
    """Compose belief about the shortest route to one consequence.

    Both figures are computed: the declared composition, and the product beside it. They are
    two fields on the artifact and are never blended -- see `PathConfidence`.
    """
    declared = context.parameters.path_confidence_composition or DEFAULT_COMPOSER
    scalars = reached.link_scalars
    return PathConfidence(
        composed=compose(scalars, declared),
        composition=declared,
        product=compose(scalars, "independent_product_v1"),
        path_length=len(scalars),
        link_scalars=scalars,
        provenance_class=ProvenanceClass.INFERRED
        if context.view.standing is GraphStanding.STATED
        else ProvenanceClass.STATISTICAL,
    )


def _node(reached: Reached, event: Event, context: PropagationContext) -> PropagationNode:
    """Assemble one settled consequence into the artifact shape."""
    magnitude = share_for(reached.event_id, reached.weight, context)
    return PropagationNode(
        event_id=reached.event_id,
        event_type=event.event_type,
        depth=reached.depth,
        reached_event_ids=tuple(sorted(reached.reached_ids)),
        path_confidence=_path_confidence(reached, context),
        route_count=reached.route_count,
        magnitude=magnitude,
        process_instance_ids=context.instances_by_event_id().get(reached.event_id, ()),
        entity_ids=tuple(sorted({*event.source_entity_ids, *event.target_entity_ids})),
        is_actionable=event.is_actionable,
        provenance_class=event.provenance_class,
    )


def _headline_set(
    nodes: tuple[PropagationNode, ...], context: PropagationContext
) -> ConsequenceSet:
    """Build the consequence set the tree reports, grouped so it has one unit.

    Consequences are grouped by the measurement declared for them and the LARGEST combinable
    group becomes the tree's headline. Never a sum across measurements: a currency figure and
    an elapsed-time figure added together produce a headline whose name nobody could write
    down. The set still lists every consequence, so the membership is complete even where
    the valuation is not.
    """
    every_id = tuple(sorted(node.event_id for node in nodes))
    if not nodes:
        return ConsequenceSet(
            event_ids=(),
            measured_member_count=0,
            combination_absent_because=(
                "the traversal reached no consequence, so there is nothing to combine. "
                "Whether that is because the graph is empty, because the seed has no "
                "onward link, or because no depth was declared is stated on the tree."
            ),
        )
    by_measurement: dict[str, list[MagnitudeShare]] = {}
    for node in nodes:
        if node.magnitude.measurement_id is not None:
            by_measurement.setdefault(node.magnitude.measurement_id, []).append(node.magnitude)
    built = [consequence_set(tuple(group), context) for _, group in sorted(by_measurement.items())]
    combinable = [item for item in built if item.combined is not None]
    if not combinable:
        reason = next(
            (item.combination_absent_because for item in built if item.combination_absent_because),
            "no consequence carried an evaluable magnitude; each one's reason is on its node.",
        )
        return ConsequenceSet(
            event_ids=every_id,
            measured_member_count=0,
            combination_absent_because=reason,
        )
    headline = max(combinable, key=lambda item: (item.combined or 0.0, item.measurement_id or ""))
    # Re-stated over the WHOLE membership rather than over the measured subset, so the set
    # lists every consequence the tree holds while the coverage figure says how many of them
    # the total actually rests on.
    return ConsequenceSet(
        event_ids=every_id,
        measurement_id=headline.measurement_id,
        unit=headline.unit,
        combination=headline.combination,
        combined=headline.combined,
        measured_member_count=headline.measured_member_count,
    )


def analyze_propagation(
    seed_event_id: str, context: PropagationContext, envelope: OutputEnvelope
) -> PropagationResult:
    """Measure everything downstream of one seed, under the standing its view declares.

    Deterministic: two calls over one input produce byte-identical artifacts, including the
    rendered report. Every grouping is sorted and no dictionary is read in insertion
    sequence (`CONVENTIONS.md` §11).

    An undeclared depth yields a tree with no nodes and `not_runnable_because` set. That is
    NOT a propagation of zero and the report says so above the numbers rather than below
    them.
    """
    settled, truncations = walk(seed_event_id, context)
    events = context.events_by_id()
    nodes = tuple(
        sorted(
            (
                _node(reached, events[reached.event_id], context)
                for reached in settled.values()
                if reached.event_id in events
            ),
            key=lambda node: node.sort_key(),
        )
    )
    depth = max((node.depth for node in nodes), default=0)
    breadth = max(
        (sum(1 for node in nodes if node.depth == level) for level in range(1, depth + 1)),
        default=0,
    )
    provenance = (
        combine(*(node.provenance_class for node in nodes)) if nodes else ProvenanceClass.ASSUMED
    )
    if context.view.standing is not GraphStanding.STATED:
        # A tree walked over links nobody asserted may not claim to be an inference,
        # whatever the events under it carry. The artifact refuses it too; refusing it here
        # names the standing as the cause rather than surfacing it as a validation error.
        provenance = combine(provenance, ProvenanceClass.STATISTICAL)
    tree = PropagationTree(
        run_id=context.run_id,
        standing=context.view.standing,
        seed_event_id=seed_event_id,
        nodes=nodes,
        consequences=_headline_set(nodes, context),
        truncations=truncations,
        depth=depth,
        breadth=breadth,
        provenance_class=provenance,
        not_runnable_because=(
            DEPTH_NOT_DECLARED if context.parameters.maximum_depth is None else None
        ),
    )
    return PropagationResult(tree=tree, report=build_report(tree, context, envelope))
