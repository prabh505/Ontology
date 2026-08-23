"""The closed error taxonomy every module raises across a boundary.

`CONVENTIONS.md` §7: never raise a bare `Exception` or `ValueError` across a module
boundary; a swallowed exception is a defect. Error messages in reasoning packages must
stay domain-neutral (LAW-DOMAIN applies to strings) and must name the offending
identifier, the module, and the contract violated. No message may quote a raw source
record -- reference the evidence record identifier instead.
"""

from __future__ import annotations

__all__ = [
    "CausaLogError",
    "ContractViolationError",
    "DataQualityError",
    "LawViolationError",
    "OntologyMappingError",
    "ProjectionStaleError",
    "RuleConflictError",
]


class CausaLogError(Exception):
    """Root of the closed error taxonomy. Never raised directly."""


class LawViolationError(CausaLogError):
    """One of the Five Inviolable Laws was violated. Always logged `CRITICAL`.

    A law violation is a programming error. It is never repaired, never skipped, and
    never resolved in the code's favour.
    """


class ContractViolationError(CausaLogError):
    """A registered interface was given or returned a value it does not admit.

    Raised at the boundary on entry, not at the point of use.
    """


class OntologyMappingError(CausaLogError):
    """A dataset column or value has no ontology concept.

    Never defaulted, never guessed, never collapsed into a catch-all concept. The
    unmapped value is named in the message.
    """


class DataQualityError(CausaLogError):
    """A source record is malformed beyond the tolerated degradation policy.

    Tolerable degradation is rejected-and-counted, not raised. This class exists for the
    case where the degradation itself breaks a contract.
    """


class RuleConflictError(CausaLogError):
    """A rule pack contradicts itself. Raised at load time, never at evaluation time."""


class ProjectionStaleError(CausaLogError):
    """The requested graph projection version is not the version available.

    A stale projection is never served as if fresh. The message names the store and the
    projection version requested.
    """
