"""`RulePack` -- the seam a new domain's causal rules implement (extension seam 4 of 6)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["RulePack"]


@runtime_checkable
class RulePack(Protocol):
    """A versioned, conflict-checked set of rules expressed as data, never as code.

    prd.md §46: rules are configurable and are never hardcoded. A pack that contradicts
    itself raises `RuleConflictError` at load time -- never a runtime coin-flip
    (`CONVENTIONS.md` §7).
    """

    def rule_pack_version(self) -> str:
        """Return the semantic version of this pack; participates in the `run_id`."""
        ...

    def rule_ids(self) -> tuple[str, ...]:
        """Return every rule identifier, in canonical sequence."""
        ...
