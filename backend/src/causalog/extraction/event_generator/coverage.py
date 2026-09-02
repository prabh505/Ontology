"""Process coverage: which expected events are missing, and whether they could ever exist.

A process definition is an EXPECTATION, never a constraint (`ontology_runtime.dsl`): a run
that departs from it produces a finding, not a rejected record. This module produces those
findings, and it draws one distinction the whole report turns on.

**Absent for this instance, or absent from the dataset.** An instance that terminated early
is missing its later steps because it never reached them -- a fact about that instance. A
step is missing from EVERY instance when no field in the source witnesses it at all -- a
fact about the source, and a bound on every conclusion drawn from it. Reporting both as
"missing" would bury the second inside the first, and the second is the one that limits
what the causal engine may claim.

What can be measured against an anchor, and what cannot
--------------------------------------------------------
A process is measured per ANCHOR entity, and a step can only be counted against an anchor
that the step's own event type names among its participants. Where it does not, the
measurement is blind: the events exist and this accumulator cannot see which instance they
belong to, because the relationship that would connect them is module 7's and does not exist
yet.

Such a step is reported as **NOT ATTRIBUTABLE**, never as missing. Reporting it as missing
would be the worst kind of wrong available here: a confident, quantified claim -- "100% of
instances lack this step" -- about a step that fired on almost every one of them. That is
exactly the shape of error this repository has already paid for twice (DEF-0001, and the
derivation audit in DEF-0004 that measured what its own binding had created).

Which sequence an instance is measured against
-----------------------------------------------
A process declares a canonical sequence and admissible variants. Measuring an instance that
terminated early against the happy path would report every later step as a separate gap.
Each anchor is therefore measured against **the declared sequence whose steps it best
matches** -- largest
intersection with what was observed, tie-broken by the shorter sequence and then by
identifier, so the choice is total and deterministic and never depends on declaration
sequence in the file.

That selection is a measurement convenience and nothing more. It does not assert that the
instance followed that variant, and no downstream module may read it as a claim about which
path an instance took.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from causalog.ontology_runtime.dsl import ProcessDefinitionSpec

__all__ = [
    "CANONICAL_VARIANT_ID",
    "ProcessCoverage",
    "ProcessCoverageAccumulator",
    "ProcessStepCoverage",
    "SequenceOption",
]

#: The label the canonical sequence is reported under, so it sits in one namespace with the
#: declared variant identifiers and a reader never has to ask which one "the default" was.
CANONICAL_VARIANT_ID = "CANONICAL"


@dataclass(frozen=True)
class SequenceOption:
    """One declared path through a process: the canonical sequence, or a variant."""

    variant_id: str
    steps: tuple[str, ...]

    @property
    def step_set(self) -> frozenset[str]:
        """Return the step set, for intersection with what was observed."""
        return frozenset(self.steps)


class ProcessStepCoverage(BaseModel):
    """How one expected step fared across every instance that expected it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    process_id: str
    event_type: str
    anchors_expecting: int = Field(ge=0)
    anchors_missing: int = Field(ge=0)
    attributable: bool = True
    """False when the step's event type names no participant of the anchor's type, so no
    event of it can be attributed to an instance. Both counts are then zero and mean
    NOTHING -- see the module docstring. Resolving this needs the structural relationship
    module 7 builds; until then the honest report is that the step is unmeasured here."""
    witnessable: bool
    """False when NO emission rule can produce this event type from this dataset. The step
    is then missing from every instance for one reason, and it is a property of the source
    rather than of any instance."""
    optional: bool

    @property
    def miss_rate(self) -> float:
        """Return the share of expecting instances with no event of this type."""
        if not self.attributable or not self.anchors_expecting:
            return 0.0
        return self.anchors_missing / self.anchors_expecting

    @property
    def systematically_missing(self) -> bool:
        """Return whether every instance that expected this step lacked it.

        False for a step that is not attributable. An unmeasured step is not a missing one,
        and a report that conflated them would state a rate for a number it never counted.
        """
        return (
            self.attributable
            and bool(self.anchors_expecting)
            and self.anchors_missing == self.anchors_expecting
        )


class ProcessCoverage(BaseModel):
    """One process definition measured against every instance of it in the run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    process_id: str
    anchor_entity_type: str
    anchors: int = Field(ge=0)
    anchors_by_sequence: tuple[tuple[str, int], ...] = ()
    steps: tuple[ProcessStepCoverage, ...] = ()

    @property
    def unwitnessable_steps(self) -> tuple[str, ...]:
        """Return the steps no emission rule can ever produce, sequenced."""
        return tuple(sorted(item.event_type for item in self.steps if not item.witnessable))

    @property
    def unattributable_steps(self) -> tuple[str, ...]:
        """Return the steps this measurement cannot attribute to an instance, sequenced."""
        return tuple(sorted(item.event_type for item in self.steps if not item.attributable))

    @property
    def systematic_gaps(self) -> tuple[ProcessStepCoverage, ...]:
        """Return the steps missing from every instance that expected them."""
        return tuple(item for item in self.steps if item.systematically_missing)


@dataclass
class ProcessCoverageAccumulator:
    """Collect, per anchor entity, which event types were observed for it.

    Bounded by the number of anchor entities times the number of event types they saw --
    on a source whose records are sub-items of an anchor, that is the number of anchors and
    not the number of records, because occurrences are deduplicated before they reach here.
    """

    definitions: tuple[ProcessDefinitionSpec, ...]
    participant_types: dict[str, frozenset[str]] = field(default_factory=dict)
    """event type -> the entity types its participants name. Read to decide whether a step
    can be attributed to a process's anchor at all."""
    anchors: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    """process id -> anchor entity id -> observed event types."""

    def __post_init__(self) -> None:
        """Prepare an empty table per declared process."""
        for definition in self.definitions:
            self.anchors.setdefault(definition.id, {})

    def sequences(self, definition: ProcessDefinitionSpec) -> tuple[SequenceOption, ...]:
        """Return every declared path through one process, canonical first."""
        return (
            SequenceOption(CANONICAL_VARIANT_ID, tuple(definition.canonical_sequence)),
            *(
                SequenceOption(variant.id, tuple(variant.sequence))
                for variant in definition.variants
            ),
        )

    def observe(
        self,
        anchor_entity_ids: frozenset[str],
        event_type: str,
        entity_ids: tuple[str, ...],
    ) -> None:
        """Record that one occurrence of `event_type` names one or more anchors.

        `anchor_entity_ids` is the set of identifiers that ARE anchors of some process, so
        the walk over an event's participants is a set membership test rather than a lookup
        of every participant's type.
        """
        for definition in self.definitions:
            table = self.anchors[definition.id]
            for entity_id in entity_ids:
                if entity_id not in anchor_entity_ids:
                    continue
                table.setdefault(entity_id, set()).add(event_type)

    def register(self, process_id: str, anchor_entity_id: str) -> None:
        """Record an anchor that exists, whether or not any event named it.

        An instance with no events at all is still an instance, and one whose every step is
        missing is the most severe coverage finding there is. Counting anchors only when an
        event mentions them would make that instance invisible.
        """
        self.anchors[process_id].setdefault(anchor_entity_id, set())

    def results(self, witnessable: frozenset[str]) -> tuple[ProcessCoverage, ...]:
        """Return one coverage record per declared process, canonically sequenced."""
        reports: list[ProcessCoverage] = []
        for definition in sorted(self.definitions, key=lambda item: item.id):
            table = self.anchors[definition.id]
            options = self.sequences(definition)
            optional = frozenset(definition.optional_steps)
            expecting: dict[str, int] = {}
            missing: dict[str, int] = {}
            chosen_counts: dict[str, int] = {}
            for observed in table.values():
                option = _best_match(options, observed)
                chosen_counts[option.variant_id] = chosen_counts.get(option.variant_id, 0) + 1
                for step in option.step_set:
                    expecting[step] = expecting.get(step, 0) + 1
                    if step not in observed:
                        missing[step] = missing.get(step, 0) + 1
            steps = tuple(
                ProcessStepCoverage(
                    process_id=definition.id,
                    event_type=step,
                    anchors_expecting=(
                        expecting.get(step, 0) if self.attributable(definition, step) else 0
                    ),
                    anchors_missing=(
                        missing.get(step, 0) if self.attributable(definition, step) else 0
                    ),
                    attributable=self.attributable(definition, step),
                    witnessable=step in witnessable,
                    optional=step in optional,
                )
                for step in sorted({item for option in options for item in option.steps})
            )
            reports.append(
                ProcessCoverage(
                    process_id=definition.id,
                    anchor_entity_type=definition.anchor_entity_type,
                    anchors=len(table),
                    anchors_by_sequence=tuple(sorted(chosen_counts.items())),
                    steps=steps,
                )
            )
        return tuple(reports)

    def attributable(self, definition: ProcessDefinitionSpec, event_type: str) -> bool:
        """Return whether an event of this type can be attributed to this process's anchor.

        True exactly when the event type names a participant of the anchor's entity type. An
        event type declared with no participant of that type produces events that exist and
        that this accumulator cannot connect to any instance.
        """
        return definition.anchor_entity_type in self.participant_types.get(event_type, frozenset())

    def gaps_for(self, definition: ProcessDefinitionSpec, observed: set[str]) -> tuple[str, ...]:
        """Return the steps one instance was expected to have and does not, sequenced.

        Optional steps are excluded: a step the process declares optional is not a gap when
        it is absent, which is what declaring it optional means.
        """
        option = _best_match(self.sequences(definition), observed)
        optional = frozenset(definition.optional_steps)
        return tuple(
            sorted(
                step for step in option.step_set if step not in observed and step not in optional
            )
        )


def _best_match(options: tuple[SequenceOption, ...], observed: set[str]) -> SequenceOption:
    """Return the declared sequence this instance's observed steps best match.

    Total and deterministic: largest intersection, then the shorter sequence, then the
    lexicographically smaller identifier. Never the declaration sequence in the file, which
    would make coverage a function of YAML layout.
    """
    return min(
        options,
        key=lambda option: (
            -len(option.step_set & observed),
            len(option.steps),
            option.variant_id,
        ),
    )
