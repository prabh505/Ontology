"""Generator (f): the two event types co-occur more than independence predicts.

The measure is **lift**, over process instances:

    lift = P(effect_type present | cause_type present) / P(effect_type present)

computed from the 2x2 contingency table of instance counts. All four cells travel in the
evidence, so a reader recomputes the number rather than trusting it.

WHAT LIFT ESTABLISHES
---------------------
That, within one dataset version, instances containing the cause type contain the effect
type more often than instances in general do.

WHAT LIFT DOES NOT ESTABLISH -- stated here, and stated again in every evidence item
-------------------------------------------------------------------------------------
* **Not causation.** prd.md §59 names "correlation mistaken for causation" as a named risk
  and `CONTEXT.md` R-06 tracks it. Association is symmetric; causation is not.
* **Not direction.** Lift over an unordered pair is identical in both directions. Every
  candidate's direction here comes from `core.temporal.verdict` in `gate.py` and from
  nowhere else. Remove the gate and this generator has no orientation at all.
* **Not freedom from confounding.** A shared parent produces association between two
  effects that never touch. `confounding.py` FLAGS that structure where the candidate graph
  makes it visible; nothing at V1 resolves it (`CONTEXT.md` R-05, prd.md §59).
* **Not significance.** No p-value is computed, no null is tested, and no sampling
  distribution is assumed. Lift is a ratio of observed frequencies over a fixed, complete
  set of instances. Calling it significant would require assumptions nobody here has made.
* **Not stability.** The value is computed over the pinned dataset version. A different
  dataset version is a different number, which is why `dataset_version` scopes the run.

`ProvenanceClass.STATISTICAL` is carried on every item and is never promoted to `INFERRED`
(LAW-PROVENANCE, ADR-0003). That separation is the mechanism by which a reader can always
tell which of their candidates rests on a frequency ratio.
"""

from __future__ import annotations

from causalog.causal_engine.candidate_cause_generator.context import (
    GenerationContext,
    GeneratorStatus,
    Proposal,
)
from causalog.causal_engine.candidate_cause_generator.generators.support import (
    events_of_timeline,
    evidence_item,
)
from causalog.core.identifiers import format_float
from causalog.core.provenance import ProvenanceClass
from causalog.core.types import DirectCause, Event, EvidenceKind

__all__ = ["ASSOCIATION_DISCLAIMER", "StatisticalAssociationGenerator"]

#: Carried verbatim on every item this generator mints. A fixed string rather than a
#: generated one, so it cannot be softened per-candidate and so a reader who has seen it
#: once recognises it everywhere.
ASSOCIATION_DISCLAIMER = (
    "Lift measures co-occurrence against independence within one dataset version. It "
    "establishes NO causation, NO direction (lift is symmetric; this candidate's direction "
    "comes only from the LAW-TIME gate), NO freedom from confounding, and NO statistical "
    "significance -- no null is tested and no sampling distribution is assumed."
)


class StatisticalAssociationGenerator:
    """Propose pairs of event types whose instance-level lift clears the declared floor."""

    generator_id = "statistical_association"

    def status(self, context: GenerationContext) -> GeneratorStatus:
        """Runnable only when the pack declares both a lift floor and a weight."""
        parameters = context.parameters
        if parameters.minimum_lift is None or parameters.statistical_association_strength is None:
            return GeneratorStatus.NOT_RUNNABLE
        return GeneratorStatus.RAN

    def requirement(self) -> str:
        """Return what a pack must declare for this generator to run."""
        return (
            "candidate_generation.minimum_lift and "
            "candidate_generation.statistical_association_strength. A lift floor is a "
            "policy about which associations are worth surfacing, and it belongs beside "
            "the domain it applies to."
        )

    def propose(self, context: GenerationContext) -> tuple[Proposal, ...]:
        """Return one proposal per instance pair whose type pair clears the lift floor."""
        parameters = context.parameters
        floor = parameters.minimum_lift
        strength = parameters.statistical_association_strength
        if floor is None or strength is None:
            return ()
        events_by_id = context.events_by_id()

        per_timeline: list[tuple[str, tuple[Event, ...], frozenset[str]]] = []
        for timeline in context.timelines:
            held = events_of_timeline(timeline, events_by_id)
            per_timeline.append(
                (timeline.timeline_id, held, frozenset(event.event_type for event in held))
            )
        instances = len(per_timeline)
        if instances == 0:
            return ()

        present: dict[str, int] = {}
        for _, _, types in per_timeline:
            for event_type in types:
                present[event_type] = present.get(event_type, 0) + 1

        joint: dict[tuple[str, str], int] = {}
        for _, _, types in per_timeline:
            for cause_type in sorted(types):
                for effect_type in sorted(types):
                    if cause_type == effect_type:
                        continue
                    key = (cause_type, effect_type)
                    joint[key] = joint.get(key, 0) + 1

        associated: dict[tuple[str, str], tuple[float, int, int, int, int]] = {}
        for (cause_type, effect_type), both in sorted(joint.items()):
            with_cause = present[cause_type]
            with_effect = present[effect_type]
            # Ratio of two observed frequencies over a complete, fixed instance set --
            # engine bookkeeping over counts, not a domain metric read from the pack.
            observed_rate = both / with_cause
            baseline_rate = with_effect / instances
            if baseline_rate == 0.0:
                continue
            ratio = observed_rate / baseline_rate
            if ratio < floor:
                continue
            cause_not_effect = with_cause - both
            effect_not_cause = with_effect - both
            neither = instances - both - cause_not_effect - effect_not_cause
            associated[(cause_type, effect_type)] = (
                ratio,
                both,
                cause_not_effect,
                effect_not_cause,
                neither,
            )

        proposals: list[Proposal] = []
        for timeline_id, held, types in per_timeline:
            for (cause_type, effect_type), measured in sorted(associated.items()):
                if cause_type not in types or effect_type not in types:
                    continue
                ratio, both, cause_only, effect_only, neither = measured
                for index, cause in enumerate(held):
                    if cause.event_type != cause_type:
                        continue
                    for effect in held[index + 1 :]:
                        if effect.event_type != effect_type:
                            continue
                        proposals.append(
                            Proposal(
                                generator_id=self.generator_id,
                                cause_event=cause,
                                effect_event=effect,
                                payload=DirectCause(),
                                evidence=(
                                    evidence_item(
                                        kind=EvidenceKind.STATISTICAL_ASSOCIATION,
                                        description=(
                                            f"{cause_type} and {effect_type} co-occur "
                                            f"across process instances with lift "
                                            f"{format_float(ratio)}, above the declared "
                                            f"floor {format_float(floor)}. "
                                            + ASSOCIATION_DISCLAIMER
                                        ),
                                        verification=(
                                            "instance contingency over "
                                            f"{instances} timelines: both={both}, "
                                            f"cause_only={cause_only}, "
                                            f"effect_only={effect_only}, "
                                            f"neither={neither}; "
                                            f"lift = (both/(both+cause_only)) / "
                                            f"((both+effect_only)/{instances}) = "
                                            f"{format_float(ratio)}"
                                        ),
                                        supporting_ids=(
                                            cause.event_id,
                                            effect.event_id,
                                            timeline_id,
                                        ),
                                        strength=strength,
                                        provenance_class=ProvenanceClass.STATISTICAL,
                                    ),
                                ),
                            )
                        )
        return tuple(sorted(proposals, key=lambda item: item.sort_key()))
