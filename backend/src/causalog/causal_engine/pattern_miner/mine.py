"""Patterns across a whole run, for the reader who does not want an incident.

prd.md §10 names five users and one of them, Executive Leadership, "needs strategic patterns
rather than individual incidents". Modules 11 and 12 both answer questions about ONE outcome.
Nothing in prd.md §36 answers a question about the run, and this package is that answer.

**It is deliberately not one of the sixteen modules.** The Causal Graph Builder set the
precedent (OQ-025, ADR-0054): where §36 names no owner for work the PRD plainly requires, the
work lands as a named package beside the modules rather than being smuggled into one of
their remits. Module 11's contract is "rank causes by consequence prevented" and module 12's
is "measure how an effect spreads from a seed"; cross-run mining is neither, and widening
either contract to hold it would make `docs/architecture.md` §2 wrong about what those
modules do.

EVERYTHING HERE RUNS OVER THE EVENT-TYPE PROJECTION, NEVER OVER INSTANCES

The same altitude `causal_graph_builder.cycles` chose, for the same reason stated there: a
claim about instances is unique by construction, so a recurrence counter running at that
level could only ever return one. "This shape keeps happening" is a statement about kinds of
event. The cost is stated rather than discovered: a motif reported here may be carried by
one pathological instance repeating, which is why every motif reports the number of distinct
process instances it spans beside its raw count -- one type firing forty times inside a
single instance is a local pathology and the same count across forty instances is systemic,
and a single number cannot tell them apart.

THREE FINDINGS, NEVER RANKED AGAINST EACH OTHER

`motifs` -- recurring cause-type-to-effect-type shapes above the declared support.
`bottlenecks` -- types that sit on many claims, by degree and by carried consequence.
`hubs_by_consequence` -- the types appearing in the most high-consequence chains.

They answer three different questions and there is no combined "importance" figure, for the
reason ADR-0008 gives about root causes one level down: the weighting between "happens often"
and "costs a lot when it happens" would be an unexplainable constant.
"""

from __future__ import annotations

from causalog.causal_engine.pattern_miner.report import (
    Bottleneck,
    Motif,
    StructuralPatternReport,
    build_report,
)
from causalog.causal_engine.propagation_analyzer import PropagationContext
from causalog.causal_engine.propagation_analyzer.view import GraphStanding
from causalog.core.run import OutputEnvelope
from causalog.rule_engine import PatternMiningSpec

__all__ = ["bottlenecks_of", "mine_patterns", "motifs_of"]


def _type_projection(
    context: PropagationContext,
) -> tuple[dict[tuple[str, str], set[tuple[str, str]]], dict[tuple[str, str], set[str]]]:
    """Project every claim onto its endpoint TYPES, keeping what carried each projection.

    Returns the instance-level pairs behind each type pair, and the process instances they
    span. Both are kept rather than counted immediately, because a count discards exactly
    the information needed to tell a repeated pathology from a systemic one.
    """
    events = context.events_by_id()
    instances = context.instances_by_event_id()
    carried: dict[tuple[str, str], set[tuple[str, str]]] = {}
    spanned: dict[tuple[str, str], set[str]] = {}
    for source_id, source in sorted(events.items()):
        for link in context.view.links_from(source_id):
            target = events.get(link.target_event_id)
            if target is None:
                continue
            key = (source.event_type, target.event_type)
            carried.setdefault(key, set()).add((source_id, link.target_event_id))
            spanned.setdefault(key, set()).update(instances.get(source_id, ()))
            spanned.setdefault(key, set()).update(instances.get(link.target_event_id, ()))
    return carried, spanned


def motifs_of(
    context: PropagationContext, parameters: PatternMiningSpec
) -> tuple[tuple[Motif, ...], str | None]:
    """Return the recurring type-level shapes, and the reason there are none if there are.

    Only length-two motifs are enumerated at this schema version, and that is stated rather
    than left to be discovered from the output: enumeration over a dense type projection is
    exponential in the motif length, `motif_maximum_length` exists to bound it, and honestly
    reporting a bound this version does not yet use is better than silently implying that
    longer motifs were looked for and not found.
    """
    if parameters.motif_minimum_support is None:
        return (), (
            "the pack declares no pattern_mining.motif_minimum_support, so no motif is "
            "reported. How many repetitions make a pattern is a domain judgement -- two is "
            "a coincidence in one domain and a trend in another -- and a threshold written "
            "into the engine would be this engine's opinion about someone else's domain "
            "(ADR-0049). This is not a finding that there are no patterns."
        )
    carried, spanned = _type_projection(context)
    found = [
        Motif(
            cause_event_type=cause,
            effect_event_type=effect,
            occurrences=len(pairs),
            instance_span=len(spanned.get((cause, effect), set())),
            minimum_support=parameters.motif_minimum_support,
            detail=(
                f"{cause} -> {effect} is claimed {len(pairs)} time(s) across "
                f"{len(spanned.get((cause, effect), set()))} process instance(s). The span "
                "is beside the count because one shape repeating inside a single instance "
                "is a local pathology and the same count spread across many instances is a "
                "systemic one, and one number cannot tell them apart."
            ),
        )
        for (cause, effect), pairs in sorted(carried.items())
        if len(pairs) >= parameters.motif_minimum_support
    ]
    if not found:
        return (), (
            f"no type-level shape reaches the declared support of "
            f"{parameters.motif_minimum_support}. {len(carried)} distinct shape(s) were "
            "examined, so this is a measured absence rather than an unrun check."
        )
    return tuple(sorted(found, key=lambda motif: motif.sort_key())), None


def bottlenecks_of(
    context: PropagationContext, parameters: PatternMiningSpec
) -> tuple[tuple[Bottleneck, ...], str | None]:
    """Return the chronically busy types in the projection, by degree.

    Degree is counted in and out SEPARATELY and never summed. A type that many things cause
    and a type that causes many things are different structures with different responses --
    the first is where consequence collects and the second is where it originates -- and a
    single degree figure would rank them together while describing neither.
    """
    if parameters.bottleneck_minimum_degree is None:
        return (), (
            "the pack declares no pattern_mining.bottleneck_minimum_degree, so no "
            "bottleneck is reported. The degree at which a type becomes a hub depends on "
            "how many types the domain declares -- one edge in four is a hub among twenty "
            "types and noise among two hundred -- so the number is a pack declaration "
            "(ADR-0049)."
        )
    carried, spanned = _type_projection(context)
    incoming: dict[str, set[str]] = {}
    outgoing: dict[str, set[str]] = {}
    claims: dict[str, int] = {}
    for (cause, effect), pairs in carried.items():
        outgoing.setdefault(cause, set()).add(effect)
        incoming.setdefault(effect, set()).add(cause)
        claims[cause] = claims.get(cause, 0) + len(pairs)
        claims[effect] = claims.get(effect, 0) + len(pairs)
    found = [
        Bottleneck(
            event_type=event_type,
            in_degree=len(incoming.get(event_type, set())),
            out_degree=len(outgoing.get(event_type, set())),
            claims_touching=claims.get(event_type, 0),
            minimum_degree=parameters.bottleneck_minimum_degree,
            detail=(
                f"{event_type} is claimed to be caused by "
                f"{len(incoming.get(event_type, set()))} type(s) and to cause "
                f"{len(outgoing.get(event_type, set()))}. The two are reported separately "
                "and never summed: a type consequence collects at and a type consequence "
                "originates from are different structures needing different responses."
            ),
        )
        for event_type in sorted(set(incoming) | set(outgoing))
        if max(len(incoming.get(event_type, set())), len(outgoing.get(event_type, set())))
        >= parameters.bottleneck_minimum_degree
    ]
    if not found:
        return (), (
            f"no type reaches the declared degree of "
            f"{parameters.bottleneck_minimum_degree}. "
            f"{len(set(incoming) | set(outgoing))} type(s) were examined, so this is a "
            "measured absence rather than an unrun check."
        )
    return tuple(sorted(found, key=lambda item: item.sort_key())), None


def mine_patterns(
    context: PropagationContext, parameters: PatternMiningSpec, envelope: OutputEnvelope
) -> StructuralPatternReport:
    """Mine the whole run for structure, under the standing its graph view declares.

    Deterministic: two calls over one input produce byte-identical artifacts, including the
    rendered report. Every grouping is sorted and no dictionary is read in insertion
    sequence (`CONVENTIONS.md` §11).
    """
    motifs, motif_absence = motifs_of(context, parameters)
    bottlenecks, bottleneck_absence = bottlenecks_of(context, parameters)
    carried, _ = _type_projection(context)
    return build_report(
        envelope=envelope,
        standing=context.view.standing,
        motifs=motifs,
        motifs_absent_because=motif_absence,
        bottlenecks=bottlenecks,
        bottlenecks_absent_because=bottleneck_absence,
        shapes_examined=len(carried),
        links_examined=context.view.link_count(),
        maximum_motif_length_enumerated=2,
        declared_motif_maximum_length=parameters.motif_maximum_length,
        diagnostic=context.view.standing is not GraphStanding.STATED,
    )
