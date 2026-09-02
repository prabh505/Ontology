"""Group events into per-process sequenced timelines (module 5).

See `README.md` for this package's forbidden dependencies.
"""

from __future__ import annotations

from causalog.graph_engine.timeline_builder.build import TimelineBuilder, TimelineBuildResult
from causalog.graph_engine.timeline_builder.join import join
from causalog.graph_engine.timeline_builder.quality import (
    TIMELINE_QUALITY_SCHEMA_VERSION,
    ProcessDefinitionConformance,
    SequenceViolation,
    SequenceViolationKind,
    TimelineQualityReport,
    render_markdown,
)

__all__ = [
    "TIMELINE_QUALITY_SCHEMA_VERSION",
    "ProcessDefinitionConformance",
    "SequenceViolation",
    "SequenceViolationKind",
    "TimelineBuildResult",
    "TimelineBuilder",
    "TimelineQualityReport",
    "join",
    "render_markdown",
]
