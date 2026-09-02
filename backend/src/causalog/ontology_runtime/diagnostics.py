"""Diagnostics: what a pack load reports, and how it reports it.

Three severities, and the third is the point of this module.

  * `ERROR` -- the pack is refused.
  * `WARNING` -- the pack loads; something about it is likely wrong.
  * `NOT_RUNNABLE` -- **a check that could not run.**

`NOT_RUNNABLE` exists because this repository has twice mistaken a check that could not run
for a check that passed: DEF-0001 (a lint that matched nothing) and OQ-014 (a determinism
gate with no pipeline to run against). A validator that silently skips a check it lacks the
inputs for is indistinguishable from one that ran it and found nothing. So it says so.

Every diagnostic carries a stable machine-readable `code` as well as prose. Tests assert on
codes; humans read messages. Asserting on message text makes rewording a test failure, which
is how validators end up with messages nobody dares improve.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

__all__ = ["Diagnostic", "Severity", "render"]


class Severity(str, Enum):
    """How a diagnostic bears on whether the pack may be used."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    NOT_RUNNABLE = "NOT_RUNNABLE"


class Diagnostic(BaseModel):
    """One finding about one pack, addressed to the person who has to fix it.

    `path` is the dotted address inside the document (`event_types[X].participants[0]`),
    `line` is where that address sits in the file. Both are present whenever the finding
    can be located; `line` is `None` for a finding about the document as a whole.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: Severity
    code: str
    message: str
    path: str
    file: Path | None = None
    line: int | None = None

    def render(self) -> str:
        """Return the one-line form: location, code, then the message."""
        where = str(self.file) if self.file is not None else "<pack>"
        if self.line is not None:
            where = f"{where}:{self.line}"
        address = f" {self.path}" if self.path else ""
        return f"{where} [{self.code}]{address}: {self.message}"


def render(diagnostics: tuple[Diagnostic, ...]) -> str:
    """Render a block of diagnostics, most severe first, one per line.

    Every diagnostic is reported, not just the first. A validator that stops at the first
    problem turns fixing a pack into a sequence of reloads, and an author who reloads ten
    times learns to distrust the tenth message.
    """
    sequence = {Severity.ERROR: 0, Severity.NOT_RUNNABLE: 1, Severity.WARNING: 2}
    ranked = sorted(
        diagnostics,
        key=lambda item: (sequence[item.severity], str(item.file), item.line or 0, item.code),
    )
    return "\n".join(item.render() for item in ranked)
