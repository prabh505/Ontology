"""Rule coverage: which types the pack explains, and which are the system's blind spots.

This is the module that answers a question nothing else in the system can. `docs/architecture.md`
§8 carries it as the second open risk: *"Recall is bounded by rule coverage, and the system
cannot report what it missed. A causal relationship not expressible as a rule is invisible,
and its absence is silent."* A coverage report does not fix that. It makes one part of it --
which declared types no rule reasons about at all -- loud instead of silent.

Three questions per event type, kept apart because they have different answers:

  * **Explained** -- some enabled rule names it as a CONSEQUENT. Without this, an occurrence
    of that type can never receive an incoming candidate edge, and a root-cause query that
    reaches it stops there with no reason given.
  * **Reasoned from** -- some enabled rule names it as an ANTECEDENT. Without this, the type
    can never explain anything else, however often it occurs.
  * **Witnessable** -- the schema mapping carries an emission rule for it, so some record
    could in principle produce one. A type nothing emits cannot be covered by any rule, and
    a rule matching it is dead code in data form.

A type that is unwitnessable is reported separately from one that is merely unexplained. The
first is a limit of the dataset; the second is a gap in the pack. Collapsing them would let a
pack author "fix" coverage by writing rules for types no record can ever produce.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalog.core.ontology_view import VocabularyView
from causalog.rule_engine.dsl import KnowledgeProvenance, RulePackSpec

__all__ = ["CoverageReport", "EventTypeCoverage", "measure_coverage"]


class EventTypeCoverage(BaseModel):
    """One declared event type, and what the pack does and does not say about it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: str
    explained_by: tuple[str, ...]
    reasoned_from_by: tuple[str, ...]
    witnessable: bool | None

    @property
    def is_blind_spot(self) -> bool:
        """Return whether a witnessable type has no rule explaining it.

        `witnessable is None` means the mapping was not supplied, so witnessability was NOT
        CHECKED. An unchecked type is treated as potentially witnessable and therefore as a
        potential blind spot -- the conservative direction, because reporting a blind spot
        that turns out to be unwitnessable costs a reader one line, and hiding a real one
        costs a conclusion.
        """
        return not self.explained_by and self.witnessable is not False


class CoverageReport(BaseModel):
    """Coverage of one rule pack against one ontology's declared event types."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_pack_id: str
    rule_pack_version: str
    ontology_pack: str
    entries: tuple[EventTypeCoverage, ...]
    rules_total: int
    rules_enabled: int
    rules_by_knowledge_provenance: tuple[tuple[str, int], ...]
    #: True when a schema mapping was supplied, so the witnessability column is real. False
    #: makes every `witnessable` `None`, and the renderer says NOT CHECKED rather than
    #: printing a blank a reader would read as "no".
    witnessability_checked: bool

    @property
    def explained_count(self) -> int:
        """Return how many declared event types some enabled rule explains."""
        return sum(1 for entry in self.entries if entry.explained_by)

    @property
    def coverage_ratio(self) -> float:
        """Return explained types over declared types, in `[0, 1]`.

        Deliberately computed over **declared** types rather than over witnessable ones. The
        denominator that flatters a pack is the one that hides that a declared type has no
        rule, and the point of this report is the opposite.
        """
        if not self.entries:
            return 0.0
        return self.explained_count / len(self.entries)

    def blind_spots(self) -> tuple[EventTypeCoverage, ...]:
        """Return every witnessable type no enabled rule explains, in canonical sequence."""
        return tuple(entry for entry in self.entries if entry.is_blind_spot)

    def unwitnessable(self) -> tuple[str, ...]:
        """Return every declared type no record can produce. A dataset limit, not a gap."""
        return tuple(entry.event_type for entry in self.entries if entry.witnessable is False)


def measure_coverage(
    pack: RulePackSpec,
    vocabulary: VocabularyView,
    *,
    witnessable_event_types: frozenset[str] | None = None,
) -> CoverageReport:
    """Measure one rule pack's coverage of one ontology's declared event types.

    Args:
        pack: the loaded rule pack.
        vocabulary: the declared names (`extraction.ontology_adapters.vocabulary_of`).
        witnessable_event_types: the types some emission rule can produce. `None` means no
            mapping was supplied and witnessability was not checked -- reported as such,
            never silently treated as "all witnessable".

    Only **enabled** rules contribute. A disabled rule explains nothing today, and crediting
    it would make switching a rule off invisible in the one report where it most needs to be
    visible.
    """
    explained: dict[str, list[str]] = {}
    reasoned: dict[str, list[str]] = {}
    for rule in pack.enabled_rules():
        for event_type in rule.produced_event_types():
            explained.setdefault(event_type, []).append(rule.id)
        for event_type in rule.antecedent_event_types():
            reasoned.setdefault(event_type, []).append(rule.id)

    entries = tuple(
        EventTypeCoverage(
            event_type=declared.id,
            explained_by=tuple(sorted(explained.get(declared.id, []))),
            reasoned_from_by=tuple(sorted(reasoned.get(declared.id, []))),
            witnessable=(
                None if witnessable_event_types is None else declared.id in witnessable_event_types
            ),
        )
        for declared in vocabulary.event_types
    )

    tally: dict[str, int] = {member.value: 0 for member in KnowledgeProvenance}
    for rule in pack.rules:
        tally[rule.knowledge_provenance.value] += 1

    return CoverageReport(
        rule_pack_id=pack.rule_pack_id,
        rule_pack_version=pack.rule_pack_version,
        ontology_pack=pack.ontology_pack,
        entries=entries,
        rules_total=len(pack.rules),
        rules_enabled=len(pack.enabled_rules()),
        rules_by_knowledge_provenance=tuple(sorted(tally.items())),
        witnessability_checked=witnessable_event_types is not None,
    )


def render_markdown(report: CoverageReport) -> str:
    """Render the report as the document written beside the other dataset reports.

    Blind spots are listed BEFORE the full table. A report whose finding is buried under
    twenty rows of "covered" is a report nobody reads to the end.
    """
    lines: list[str] = [
        f"# Rule coverage — `{report.rule_pack_id}` v{report.rule_pack_version}",
        "",
        f"Ontology pack: `{report.ontology_pack}`  ",
        f"Rules: **{report.rules_enabled} enabled** of {report.rules_total} declared  ",
        f"Declared event types explained: "
        f"**{report.explained_count} of {len(report.entries)}** "
        f"({report.coverage_ratio:.0%})",
        "",
    ]

    provenance = ", ".join(
        f"{name} {count}" for name, count in report.rules_by_knowledge_provenance
    )
    lines += [f"Knowledge provenance of the rules: {provenance}.", ""]

    spots = report.blind_spots()
    lines += ["## Blind spots", ""]
    if not spots:
        lines += ["None. Every declared event type has at least one rule explaining it.", ""]
    else:
        lines += [
            f"{len(spots)} declared event type(s) have **no rule explaining them**. An "
            "occurrence of one of these can never receive an incoming candidate edge, so a "
            "root-cause query that reaches it stops there and says nothing.",
            "",
        ]
        for entry in spots:
            reached = (
                f"reasoned FROM by {', '.join(entry.reasoned_from_by)}"
                if entry.reasoned_from_by
                else "named by no rule at all"
            )
            lines.append(f"- `{entry.event_type}` — {reached}")
        lines.append("")

    unwitnessable = report.unwitnessable()
    if unwitnessable:
        lines += [
            "## Declared but unwitnessable",
            "",
            "The schema mapping carries no emission rule for these, so no record can "
            "produce one. This is a limit of the dataset, not a gap in the pack, and a rule "
            "matching one of them would be dead code in data form.",
            "",
        ]
        lines += [f"- `{name}`" for name in unwitnessable]
        lines.append("")
    elif not report.witnessability_checked:
        lines += [
            "## Declared but unwitnessable",
            "",
            "**NOT CHECKED** — no schema mapping was supplied, so whether a record can "
            "witness each type was not determined. Reported rather than skipped: a check "
            "that could not run must never read as a check that passed.",
            "",
        ]

    lines += [
        "## Every declared event type",
        "",
        "| Event type | Explained by | Reasoned from by | Witnessable |",
        "|---|---|---|---|",
    ]
    for entry in report.entries:
        explained_by = ", ".join(entry.explained_by) or "—"
        reasoned_by = ", ".join(entry.reasoned_from_by) or "—"
        if entry.witnessable is None:
            witnessable = "not checked"
        else:
            witnessable = "yes" if entry.witnessable else "**no**"
        lines.append(f"| `{entry.event_type}` | {explained_by} | {reasoned_by} | {witnessable} |")
    lines.append("")
    return "\n".join(lines)
