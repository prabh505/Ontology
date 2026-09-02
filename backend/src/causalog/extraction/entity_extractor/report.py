"""The reconciliation report: what identity resolution created, merged, and could not settle.

A first-class output, not a log line. Identity resolution is the one step in this
pipeline whose mistakes are invisible afterwards: two participants merged into one produce
a graph that is well-formed, self-consistent, and wrong, and no downstream check can see it.
The counts here are what makes that step reviewable at all.

Every number is measured from the run that produced it. A report that stated a policy
without stating what the policy DID would be a configuration dump.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from causalog.core.run import OutputEnvelope
from causalog.extraction.entity_extractor.identity import AttributeConflict, ConflictPolicy

__all__ = [
    "RECONCILIATION_SCHEMA_VERSION",
    "EntityTypeReconciliation",
    "ReconciliationReport",
    "render_markdown",
]

#: This report's own shape. Bumping it invalidates comparison with a report written under a
#: prior shape. It does NOT participate in `run_id`: the report describes a run, it is not
#: an input to one -- the same rule `report_schema_version` follows (`CONTEXT.md` §7).
RECONCILIATION_SCHEMA_VERSION = "1.0.0"


class EntityTypeReconciliation(BaseModel):
    """What happened to one entity type across every record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: str
    entities_created: int = Field(ge=0)
    records_observed: int = Field(ge=0)
    """Records that named a derivable key for this type. Always at least `entities_created`."""
    entities_conflicted: int = Field(ge=0)
    conflicts: int = Field(ge=0)
    records_without_key: int = Field(ge=0)
    """Records naming no derivable key for this type. NOT an error: a source frequently
    references a participant it does not describe (`docs/architecture.md` §2, module 3)."""
    attribute_versions: int = Field(ge=0)
    entities_with_changed_attributes: int = Field(ge=0)

    @property
    def records_merged(self) -> int:
        """Return the records folded into an entity that already existed."""
        return self.records_observed - self.entities_created


class ReconciliationReport(BaseModel):
    """Every statement one extraction run makes about identity.

    Carries its `OutputEnvelope`: an output without its envelope cannot be verified and is a
    defect (`CONVENTIONS.md` §11).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_schema_version: str = RECONCILIATION_SCHEMA_VERSION
    envelope: OutputEnvelope
    conflict_policy: ConflictPolicy
    records_read: int = Field(ge=0)
    per_entity_type: tuple[EntityTypeReconciliation, ...] = ()
    conflicts: tuple[AttributeConflict, ...] = ()
    conflict_examples_capped_at: int = Field(ge=0)
    """Examples kept per `(entity_type, attribute)`, not per run. A flat cap fills with
    whichever disagreement is commonest and hides every other kind."""
    conflicts_total: int = Field(ge=0)
    not_checked: tuple[str, ...] = ()

    @property
    def entities_created(self) -> int:
        """Return the total number of distinct entities."""
        return sum(item.entities_created for item in self.per_entity_type)

    @property
    def records_merged(self) -> int:
        """Return the total number of records folded into an existing entity."""
        return sum(item.records_merged for item in self.per_entity_type)

    @property
    def entities_conflicted(self) -> int:
        """Return the total number of entities carrying at least one recorded disagreement."""
        return sum(item.entities_conflicted for item in self.per_entity_type)


def render_markdown(report: ReconciliationReport) -> str:
    """Render the report as committed markdown, deterministically.

    No wall clock, no host name, no absolute path: the file is compared byte-for-byte by
    the determinism test, and anything ambient in it would make an identical run look like
    a changed one.
    """
    lines = [
        "# Entity Reconciliation Report",
        "",
        f"- `report_schema_version`: `{report.report_schema_version}`",
        f"- `run_id`: `{report.envelope.run_id}`",
        f"- `dataset_version`: `{report.envelope.dataset_version}`",
        f"- `ontology_hash`: `{report.envelope.ontology_hash}`",
        f"- `engine_version`: `{report.envelope.engine_version}`",
        f"- conflict policy: **{report.conflict_policy.value}**",
        "",
        "## Reconciliation",
        "",
        f"Records read: **{report.records_read:,}**. "
        f"Entities created: **{report.entities_created:,}**. "
        f"Records merged into an existing entity: **{report.records_merged:,}**. "
        f"Entities carrying a recorded disagreement: **{report.entities_conflicted:,}**.",
        "",
        "| Entity type | Created | Records | Merged | Conflicted | Conflicts | No key | "
        "Attribute versions | Changed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report.per_entity_type:
        lines.append(
            f"| `{item.entity_type}` | {item.entities_created:,} | "
            f"{item.records_observed:,} | {item.records_merged:,} | "
            f"{item.entities_conflicted:,} | {item.conflicts:,} | "
            f"{item.records_without_key:,} | {item.attribute_versions:,} | "
            f"{item.entities_with_changed_attributes:,} |"
        )
    lines.extend(["", "## Conflicts", ""])
    if not report.conflicts_total:
        lines.append("No record disagreed with another about any attribute of any entity.")
    else:
        kinds = len({(item.entity_type, item.attribute) for item in report.conflicts})
        lines.append(
            f"**{report.conflicts_total:,}** disagreement(s) recorded across **{kinds}** "
            f"kind(s) of `(entity type, attribute)`. Up to "
            f"{report.conflict_examples_capped_at} example(s) of EACH kind are listed below, "
            f"{len(report.conflicts):,} in total -- per kind rather than per run, so a "
            "common disagreement cannot crowd out a rarer one. The count above is exact and "
            "uncapped. Every conflict was resolved by "
            f"`{report.conflict_policy.value}`, and every one is reported regardless of "
            "policy: the policy decides which value the entity carries, never whether the "
            "disagreement is visible."
        )
        lines.append("")
        lines.extend(f"- {conflict.render()}" for conflict in report.conflicts)
    lines.extend(["", "## What this run did NOT check", ""])
    lines.extend(f"- {item}" for item in report.not_checked)
    return "\n".join(lines) + "\n"
