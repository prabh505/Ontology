"""Derive `State` and `Transition` from events (module 6).

See `README.md` for this package's forbidden dependencies.
"""

from __future__ import annotations

from causalog.graph_engine.state_engine.asof import StateAsOf, state_as_of
from causalog.graph_engine.state_engine.derive import StateDerivationResult, StateEngine
from causalog.graph_engine.state_engine.quality import (
    STATE_QUALITY_SCHEMA_VERSION,
    DurationStatistic,
    IllegalTransitionFinding,
    StateQualityReport,
    render_markdown,
)

__all__ = [
    "STATE_QUALITY_SCHEMA_VERSION",
    "DurationStatistic",
    "IllegalTransitionFinding",
    "StateAsOf",
    "StateDerivationResult",
    "StateEngine",
    "StateQualityReport",
    "render_markdown",
    "state_as_of",
]
