"""Ontology-facing seams (extension seams 2, 3, 5, 6 of 6).

These Protocols are declared in `core/` so that a domain author has one place to look.
Declaring them here does NOT license a reasoning package to import them: forbidden edge
F3 in `docs/architecture.md` §1 restricts ontology consumption to L1-L3 (mapping and
extraction) and, for `PresentationLabels` only, to L10 (presentation).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["CostBand", "CostModel", "OntologySpec", "PresentationLabels", "SchemaMappingSpec"]

#: Intervention cost is ontology-supplied configuration, never inferred (OQ-013).
#: An ordinal band, deliberately not a currency amount -- a fabricated number would
#: silently drive the recommendation ranking.
CostBand = str


@runtime_checkable
class OntologySpec(Protocol):
    """The declared vocabulary of one domain: types, states, and legal transitions."""

    def ontology_version(self) -> str:
        """Return the semantic version of this ontology instance."""
        ...

    def ontology_hash(self) -> str:
        """Return the content hash that participates in every `run_id` and envelope."""
        ...

    def entity_types(self) -> frozenset[str]:
        """Return every declared entity type name."""
        ...

    def event_types(self) -> frozenset[str]:
        """Return every declared event type name."""
        ...

    def state_names(self) -> frozenset[str]:
        """Return every declared state name."""
        ...

    def transition_is_legal(self, from_state: str, to_state: str) -> bool:
        """Return whether the ontology declares this state change admissible."""
        ...

    def event_type_is_actionable(self, event_type: str) -> bool:
        """Return whether an event of this type is one a human could have acted on.

        Configuration, never inferred (ADR-0008). prd.md §29 ranks root causes by
        actionability -- a storm is not actionable, a dispatch is -- and that judgement is
        domain knowledge. It is declared here and stamped onto each `Event` at generation
        time, so the module that ranks on it never reads the ontology (forbidden edge F3).

        An event type with no declaration is an `OntologyMappingError`, never a default:
        defaulting to actionable inflates the ranking, defaulting to not-actionable hides
        the only interventions a user could make.
        """
        ...


@runtime_checkable
class SchemaMappingSpec(Protocol):
    """The binding from dataset columns and values to ontology concepts.

    Every lookup either resolves or raises `OntologyMappingError`. There is no default
    concept and no catch-all (`CONVENTIONS.md` §7).
    """

    def concept_for_column(self, column_name: str) -> str:
        """Return the ontology concept a source column binds to."""
        ...

    def concept_for_value(self, column_name: str, raw_value: str) -> str:
        """Return the ontology concept a source value binds to."""
        ...

    def unmapped_columns(self) -> frozenset[str]:
        """Return columns the mapping deliberately drops, declared explicitly."""
        ...


@runtime_checkable
class CostModel(Protocol):
    """Ordinal cost bands for interventions, supplied as ontology configuration."""

    def band_for(self, intervention_kind: str) -> CostBand:
        """Return the declared ordinal cost band. Never computed from data."""
        ...


@runtime_checkable
class PresentationLabels(Protocol):
    """Display strings for ontology concepts. The ONLY ontology seam L10 may read.

    Labels are presentation data. A reasoning package that reads a label to decide
    something has reintroduced the domain into the core (LAW-DOMAIN).
    """

    def label_for(self, concept: str, locale: str) -> str:
        """Return the human-facing string for an ontology concept."""
        ...
