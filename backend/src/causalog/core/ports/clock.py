"""`Clock` -- time is injected, never read from the ambient clock (`CONVENTIONS.md` §11).

`datetime.now()` inside a reasoning package is a defect: it makes reruns differ.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock"]


@runtime_checkable
class Clock(Protocol):
    """Supply the current instant to the layers that legitimately need one."""

    def now_utc(self) -> datetime:
        """Return a timezone-aware UTC instant. A naive datetime is a defect."""
        ...
