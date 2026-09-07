"""Is this cause structural, or did it happen once?

prd.md §10's Executive Leadership user "needs strategic patterns rather than individual
incidents", and the same distinction matters inside a single incident's ranking: a cause
that produces this outcome once is a thing that went wrong, and a cause that produces it in
a third of the run is a thing that is wrong. Both are true; they call for different
responses, and a ranking that could not tell them apart would recommend firefighting.

TWO NUMBERS, BECAUSE ONE HIDES THE DIFFERENCE THAT MATTERS. `occurrences` counts the claims
of this shape across the run. `instance_span` counts the distinct process instances those
claims fall in. One cause type firing forty times inside one instance and one firing once
in each of forty instances give the same first number and mean opposite things -- the first
is a local pathology and the second is systemic.

**Counting is a measurement; calling something structural is a judgement.** So the counts
are always produced and `structural` is `None` when the pack declares no support threshold
-- never `False`, which a reader would take as "we checked, and it is incidental".

The shape is measured over the **event-TYPE projection**, never over instances. That is the
same altitude `causal_graph_builder.cycles` chose for the same reason: recurrence is a claim
about kinds of thing, and at the instance level every claim is unique by construction, so a
counter running there could only ever return one.
"""

from __future__ import annotations

from causalog.causal_engine.propagation_analyzer import PropagationContext
from causalog.causal_engine.root_cause_analyzer.ranking import Recurrence

__all__ = ["recurrence_of"]


def recurrence_of(
    cause_event_id: str,
    outcome_event_id: str,
    context: PropagationContext,
    minimum_support: int | None,
) -> Recurrence:
    """Measure how often this cause TYPE is claimed to cause this outcome TYPE.

    Both ends are projected to their types before counting, so "this happened before" is a
    statement about kinds of event and not about these two instances, which by construction
    occur once each.

    A cause or outcome absent from the fact set yields a single occurrence spanning no
    instance, with the reason stated: it is the smallest honest answer, and reporting zero
    occurrences of a pair that demonstrably occurred once would contradict the chain above
    it.
    """
    events = context.events_by_id()
    cause = events.get(cause_event_id)
    outcome = events.get(outcome_event_id)
    if cause is None or outcome is None:
        return Recurrence(
            occurrences=1,
            instance_span=0,
            minimum_support=minimum_support,
            structural=None,
            detail=(
                "recurrence could not be measured: one end of this claim is not in the "
                "run's fact set, so its type could not be read. Reported as a single "
                "occurrence rather than as none, because the claim above demonstrably "
                "exists."
            ),
        )
    instances = context.instances_by_event_id()
    matches: set[tuple[str, str]] = set()
    spanned: set[str] = set()
    for source_id, source_event in events.items():
        if source_event.event_type != cause.event_type:
            continue
        for link in context.view.links_from(source_id):
            target = events.get(link.target_event_id)
            if target is None or target.event_type != outcome.event_type:
                continue
            matches.add((source_id, link.target_event_id))
            spanned.update(instances.get(source_id, ()))
            spanned.update(instances.get(link.target_event_id, ()))
    occurrences = max(len(matches), 1)
    span = len(spanned)
    if minimum_support is None:
        return Recurrence(
            occurrences=occurrences,
            instance_span=span,
            minimum_support=None,
            structural=None,
            detail=(
                f"this shape ({cause.event_type} -> {outcome.event_type}) is claimed "
                f"{occurrences} time(s) across {span} process instance(s). Whether that "
                "counts as structural is NOT stated: the pack declares no "
                "root_cause_analysis.recurrence_minimum_support, and how many repetitions "
                "make a pattern is a domain judgement rather than an engine constant "
                "(ADR-0049). The count is the measurement; the word is the judgement."
            ),
        )
    structural = occurrences >= minimum_support
    verdict = "STRUCTURAL" if structural else "INCIDENTAL"
    return Recurrence(
        occurrences=occurrences,
        instance_span=span,
        minimum_support=minimum_support,
        structural=structural,
        detail=(
            f"this shape ({cause.event_type} -> {outcome.event_type}) is claimed "
            f"{occurrences} time(s) across {span} process instance(s), against a declared "
            f"support threshold of {minimum_support}: {verdict}. The span is reported "
            "beside the count because one cause firing many times inside a single instance "
            "is a local pathology and the same count spread across many instances is a "
            "systemic one."
        ),
    )
