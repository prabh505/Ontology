"""Base rates: the denominator without which a count means nothing.

"This pattern occurs in 84 process instances" is not a finding. Eighty-four out of ninety
is one claim, eighty-four out of eighty thousand is a different one, and eighty-four when
the effect type appears in every instance anyway is not a claim at all. Every count this module
scores against is therefore accompanied by what it was drawn from and by what independence
would have predicted.

WHAT IS COMPUTED HERE, AND WHY IT IS RECOMPUTED RATHER THAN PARSED
------------------------------------------------------------------
One 2x2 contingency table per sequenced event-type pair, over process instances:

    both          instances containing the cause type and then the effect type
    cause_only    instances containing the cause type but not that sequenced pair
    effect_only   instances containing the effect type but not that sequenced pair
    neither       the rest

Module 9's generators already count something very like this, and they put the counts into
`EvidenceItem.verification` as text so that a reader can recompute them. Reading that text
back would make module 10's scores depend on a string format nobody versioned, and the
first reworded sentence would silently change every score. So the table is recomputed here
from the same timelines, and the two are expected to agree -- which is itself a check a
reader can run.

TWO MEASURES, KEPT APART
------------------------
`support` answers *how often* -- the raw recurrence count, which module 9's historical
generator thresholds on. `lift` answers *more often than what* -- the ratio against
independence, which is the only one of the two that survives a common pattern. A pair that
appears in every instance has enormous support and lift 1.0, and this module's historical
component reads the second. Module 9 keeps the same two apart for the same reason
(`generators/historical_frequency.py`); this is that separation carried into the scoring.

NONE OF THIS IS CAUSATION
-------------------------
Lift is symmetric. Every direction in this system comes from `core.temporal.verdict` at
module 9's gate and from nowhere else. `ASSOCIATION_DISCLAIMER` is carried verbatim onto
every statistical explanation this module produces, exactly as module 9 carries it onto
every item it mints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, PrivateAttr

from causalog.causal_engine.candidate_cause_generator.generators.support import (
    events_of_timeline,
)
from causalog.core.types import Event, Timeline

__all__ = ["ContingencyTable", "PairBaseRates"]


class ContingencyTable(BaseModel):
    """The four instance counts behind one sequenced event-type pair.

    All four cells travel into every explanation, so a reader recomputes the ratio rather
    than trusting it. Two cells would be enough to compute lift and would leave the reader
    unable to check it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cause_event_type: str
    effect_event_type: str
    #: Instances exhibiting the cause type, then the effect type, in timeline sequence.
    both: int
    #: Instances holding the cause type without that sequenced pair.
    cause_only: int
    #: Instances holding the effect type without that sequenced pair.
    effect_only: int
    neither: int

    @property
    def instances(self) -> int:
        """Return the total instance count -- the denominator, stated rather than implied."""
        return self.both + self.cause_only + self.effect_only + self.neither

    @property
    def with_cause(self) -> int:
        """Return instances holding the cause type at all."""
        return self.both + self.cause_only

    @property
    def with_effect(self) -> int:
        """Return instances holding the effect type at all."""
        return self.both + self.effect_only

    @property
    def conditional_rate(self) -> float:
        """Return P(effect follows | cause present), or 0.0 when the cause never appears."""
        if self.with_cause == 0:
            return 0.0
        return self.both / self.with_cause

    @property
    def baseline_rate(self) -> float:
        """Return P(effect present) -- the base rate the conditional is compared against."""
        if self.instances == 0:
            return 0.0
        return self.with_effect / self.instances

    @property
    def lift(self) -> float | None:
        """Return `conditional_rate / baseline_rate`, or None when it is undefined.

        None when the effect type never occurs, or the cause type never occurs. Undefined
        is deliberately not folded into 1.0 or 0.0: a ratio nobody could compute is a
        missing component, and this module reports missing components rather than
        substituting a number for them.

        **Lift 1.0 means independence.** A pattern present in every single instance has
        `conditional_rate == baseline_rate == 1.0` and lift exactly 1.0 -- which is the
        whole reason this module scores lift and not support.
        """
        baseline = self.baseline_rate
        if baseline == 0.0 or self.with_cause == 0:
            return None
        return self.conditional_rate / baseline


class PairBaseRates(BaseModel):
    """Every sequenced type pair's contingency table, computed once for a whole run.

    Built once and shared by the historical and statistical scorers. Recomputing per edge
    would be quadratic in a graph with tens of thousands of edges over a few hundred type
    pairs, and -- worse -- would let the two scorers drift onto two different denominators.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    instances: int
    #: Every observed sequenced type pair's table, sorted by `(cause_type, effect_type)`.
    tables: tuple[ContingencyTable, ...]

    #: A lookup index over `tables`, built once on first use. Not a field: it is derived
    #: from `tables` and a second stored copy could disagree with it. Without it,
    #: `table_for` is a linear scan run once per edge, which is tens of millions of
    #: comparisons on a graph this module is expected to handle.
    _index: dict[tuple[str, str], ContingencyTable] | None = PrivateAttr(default=None)

    @classmethod
    def of(cls, timelines: tuple[Timeline, ...], events_by_id: dict[str, Event]) -> PairBaseRates:
        """Return the base rates over these process instances.

        Sequence within an instance is the timeline's own sequence, which is `Timeline`'s
        contract and is NOT a precedence claim -- `TimeInterval.sort_key` says so. Direction
        here is only about which pairs are counted together; whether either event actually
        preceded the other was decided by `verdict` at module 9's gate.
        """
        instance_types: list[frozenset[str]] = []
        instance_pairs: list[frozenset[tuple[str, str]]] = []
        for timeline in timelines:
            held = events_of_timeline(timeline, events_by_id)
            instance_types.append(frozenset(event.event_type for event in held))
            pairs: set[tuple[str, str]] = set()
            for index, cause in enumerate(held):
                for effect in held[index + 1 :]:
                    if cause.event_type != effect.event_type:
                        pairs.add((cause.event_type, effect.event_type))
            instance_pairs.append(frozenset(pairs))

        instances = len(instance_types)
        present: dict[str, int] = {}
        for types in instance_types:
            for event_type in types:
                present[event_type] = present.get(event_type, 0) + 1

        both_counts: dict[tuple[str, str], int] = {}
        for exhibited in instance_pairs:
            for pair in exhibited:
                both_counts[pair] = both_counts.get(pair, 0) + 1

        tables: list[ContingencyTable] = []
        for (cause_type, effect_type), both in sorted(both_counts.items()):
            with_cause = present.get(cause_type, 0)
            with_effect = present.get(effect_type, 0)
            cause_only = with_cause - both
            effect_only = with_effect - both
            tables.append(
                ContingencyTable(
                    cause_event_type=cause_type,
                    effect_event_type=effect_type,
                    both=both,
                    cause_only=cause_only,
                    effect_only=effect_only,
                    neither=instances - both - cause_only - effect_only,
                )
            )
        return cls(instances=instances, tables=tuple(tables))

    def table_for(self, cause_event_type: str, effect_event_type: str) -> ContingencyTable | None:
        """Return one pair's table, or None if the pair never co-occurred in sequence.

        None rather than an all-zero table. A pair nobody observed and a pair observed zero
        times are the same thing here, but a zero table would compute a lift of 0.0 and
        report a measurement; None makes the component missing, which is what it is.
        """
        if self._index is None:
            self._index = {
                (table.cause_event_type, table.effect_event_type): table for table in self.tables
            }
        return self._index.get((cause_event_type, effect_event_type))
