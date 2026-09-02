"""Emit zero or more `Event` values per evidence record (module 4). THE LAW-EVENT BOUNDARY.

No row, no mapped record and no source column may cross out of this package. Everything
domain-specific reaches it as DATA -- the resolved ontology pack and the schema mapping --
and nothing in it names an event type, an entity type, an attribute or a column
(LAW-DOMAIN).

The three classes of generated event never merge (ADR-0029, ADR-0040):

  * **OBSERVED** -- a column records the occurrence. The pack declares the type OBSERVED,
    and only a direct `EVENT_OCCURRED_AT` binding can place it in time.
  * **DERIVED** -- the occurrence is implied by other fields. The pack declares the basis
    and the default confidence; the mapping declares which records witness it. Its
    provenance class comes from the pack, which refuses `OBSERVED` on a derived type, so no
    heuristic here has a path to an observed event.
  * **INFERRED-MISSING** -- the process definition expects a step no field supports. Under
    the default policy no event is emitted and the gap is reported; under
    `EMIT_GAP_MARKER` an explicit marker is emitted with zero rule support.

See `README.md` for this package's forbidden dependencies.
"""

from __future__ import annotations

from causalog.extraction.event_generator.conditions import ConditionCounters, evaluate
from causalog.extraction.event_generator.coverage import (
    CANONICAL_VARIANT_ID,
    ProcessCoverage,
    ProcessCoverageAccumulator,
    ProcessStepCoverage,
    SequenceOption,
)
from causalog.extraction.event_generator.emit import (
    GAP_MARKER_SUPPORT,
    OBSERVED_RULE_SUPPORT,
    BatchSource,
    EmissionOutcome,
    EventBuilder,
    MissingEventPolicy,
    OccurrenceIndex,
    canonical_events,
    occurrence_key,
)
from causalog.extraction.event_generator.generate import (
    EventGenerator,
    GenerationResult,
    StreamedGeneration,
)
from causalog.extraction.event_generator.participants import (
    ParticipantPlan,
    Participants,
    ResolvedParticipants,
)
from causalog.extraction.event_generator.quality import (
    EVENT_QUALITY_SCHEMA_VERSION,
    EventQualityReport,
    EventTypeTally,
    render_markdown,
)
from causalog.extraction.event_generator.temporal import (
    PRECISION_RANK,
    coarser,
    occurred_at,
    unknown_interval,
)

__all__ = [
    "CANONICAL_VARIANT_ID",
    "EVENT_QUALITY_SCHEMA_VERSION",
    "GAP_MARKER_SUPPORT",
    "OBSERVED_RULE_SUPPORT",
    "PRECISION_RANK",
    "BatchSource",
    "ConditionCounters",
    "EmissionOutcome",
    "EventBuilder",
    "EventGenerator",
    "EventQualityReport",
    "EventTypeTally",
    "GenerationResult",
    "MissingEventPolicy",
    "OccurrenceIndex",
    "ParticipantPlan",
    "Participants",
    "ProcessCoverage",
    "ProcessCoverageAccumulator",
    "ProcessStepCoverage",
    "ResolvedParticipants",
    "SequenceOption",
    "StreamedGeneration",
    "canonical_events",
    "coarser",
    "evaluate",
    "occurred_at",
    "occurrence_key",
    "render_markdown",
    "unknown_interval",
]
