"""Semantic validation: what is probably wrong, and what could not be checked at all.

Nothing here refuses a pack. These are judgements, and a judgement that blocks a load is a
judgement the author cannot disagree with.

The third severity is the one that matters. `NOT_RUNNABLE` reports a check this validator
was **unable to perform** -- distinct from a check that ran and found nothing. The
distinction is not pedantry: DEF-0001 shipped a LAW-DOMAIN lint that matched nothing and
read as green for weeks, and OQ-014 tracks a determinism gate that cannot run and would
otherwise look identical to one that passes. A validator that quietly skipped the
rule-coverage check would be the third instance.
"""

from __future__ import annotations

from collections.abc import Collection

from causalog.ontology_runtime.diagnostics import Diagnostic, Severity
from causalog.ontology_runtime.dsl import ResolvedPack
from causalog.ontology_runtime.locator import Address, PackLocator

__all__ = ["validate_semantics"]


def _note(
    locator: PackLocator, severity: Severity, code: str, address: Address, message: str
) -> Diagnostic:
    """Build one non-fatal diagnostic located against the authored source."""
    file, line = locator.locate(address)
    rendered = str(address[0]) if address else ""
    for part in address[1:]:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return Diagnostic(
        severity=severity,
        code=code,
        message=message,
        path=rendered,
        file=file,
        line=line,
    )


def validate_semantics(
    pack: ResolvedPack,
    locator: PackLocator,
    *,
    produced_event_types: Collection[str] | None = None,
) -> tuple[Diagnostic, ...]:
    """Return warnings about a structurally valid pack, plus any check that could not run.

    Args:
        pack: the resolved pack.
        locator: maps addresses back to authored lines.
        produced_event_types: the event type identifiers some rule pack is known to
            produce. `None` means **no rule pack was supplied**, which is reported as
            `NOT_RUNNABLE` rather than passed over -- see this module's docstring.
    """
    findings: list[Diagnostic] = []

    for entity_type in pack.entity_types:
        base: Address = ("entity_types", entity_type.id)
        if not entity_type.identifying_keys:
            findings.append(
                _note(
                    locator,
                    Severity.WARNING,
                    "ONT-W-NO-IDENTIFYING-KEY",
                    base,
                    f"'{entity_type.id}' declares no identifying_keys. Entity extraction "
                    "builds a natural key from them; without one, two distinct things in "
                    "the source resolve to one entity and their histories merge.",
                )
            )
        lifecycle = entity_type.lifecycle
        if lifecycle is None:
            findings.append(
                _note(
                    locator,
                    Severity.WARNING,
                    "ONT-W-NO-LIFECYCLE",
                    base,
                    f"'{entity_type.id}' declares no lifecycle. The state engine can derive "
                    "no state for it, so it can carry structure but never change.",
                )
            )
            continue
        terminal = set(lifecycle.terminal_states)
        with_exit = {transition.from_state for transition in lifecycle.transitions}
        for state in lifecycle.states:
            if state not in with_exit and state not in terminal:
                findings.append(
                    _note(
                        locator,
                        Severity.WARNING,
                        "ONT-W-NO-EXIT-TRANSITION",
                        (*base, "lifecycle", "states"),
                        f"'{state}' has no exit transition and is not declared terminal. An "
                        "entity reaching it can never leave, which is either a missing "
                        "transition or a missing terminal declaration.",
                    )
                )

    referenced_in_process: set[str] = set()
    for process in pack.process_definitions:
        referenced_in_process.update(process.canonical_sequence)
        for variant in process.variants:
            referenced_in_process.update(variant.sequence)
    for event_type in pack.event_types:
        if event_type.id not in referenced_in_process:
            findings.append(
                _note(
                    locator,
                    Severity.WARNING,
                    "ONT-W-EVENT-TYPE-OUTSIDE-PROCESS",
                    ("event_types", event_type.id),
                    f"'{event_type.id}' appears in no process definition. The timeline "
                    "builder groups against processes, so it will be placed on no timeline.",
                )
            )

    if produced_event_types is None:
        findings.append(
            _note(
                locator,
                Severity.NOT_RUNNABLE,
                "ONT-N-RULE-COVERAGE",
                (),
                "no rule pack was supplied, so 'every event type has a producing rule' was "
                "NOT CHECKED. This is reported rather than skipped: a check that could not "
                "run must never read as a check that passed (DEF-0001, OQ-014).",
            )
        )
    else:
        produced = set(produced_event_types)
        for event_type in pack.event_types:
            if event_type.id not in produced:
                findings.append(
                    _note(
                        locator,
                        Severity.WARNING,
                        "ONT-W-NO-PRODUCING-RULE",
                        ("event_types", event_type.id),
                        f"no supplied rule produces '{event_type.id}'; it is declared and "
                        "unreachable.",
                    )
                )
    return tuple(findings)
