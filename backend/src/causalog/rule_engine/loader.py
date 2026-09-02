"""Load a rule pack, validate it, and refuse one that contradicts itself.

Three things happen here, in this sequence, and the sequence matters:

1. **Parse and validate the shape.** The DSL models are normative; a malformed pack is a
   `ContractViolationError` naming the file.
2. **Detect static contradictions.** A pack that contradicts itself raises
   `RuleConflictError` **at load time, never a runtime coin-flip** (`CONVENTIONS.md` §7, and
   the `RulePack` port's own docstring). Load time is the only place where refusing costs
   nothing and where the author is still holding the file.
3. **Check every reference against the declared vocabulary** -- if one was supplied. If none
   was, the check reports `NOT_RUNNABLE` and never passes. A validator that silently skips a
   check it lacks inputs for is indistinguishable from one that ran it and found nothing;
   this repository has made that mistake twice (DEF-0001, OQ-014).

What this module cannot check, stated so a green load is not over-read
---------------------------------------------------------------------
The same limit `docs/ontology.md` §6 states for the pack loader applies here, for the same
reason. **A valid rule pack can be a wrong rule pack.** Nothing here checks that a claimed
mechanism is real, that a window is the right width, that a weight is calibrated, or that an
`evidence_basis` describes the evidence it claims to. Those are judgements, and a judgement
this module made would be one the author could not disagree with. Tracked as risk R-16.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from causalog.core.errors import ContractViolationError, RuleConflictError
from causalog.core.identifiers import IdentifierPrefix, digest
from causalog.core.ontology_view import VocabularyView
from causalog.core.serialization import to_canonical_json
from causalog.rule_engine.diagnostics import Diagnostic, Severity, render
from causalog.rule_engine.dsl import (
    RULE_PACK_SCHEMA_VERSION,
    CausalBody,
    ConstraintBody,
    EntityRelation,
    EventPattern,
    JointBody,
    ModifierBody,
    Rule,
    RuleKind,
    RulePackSpec,
)

__all__ = ["LoadedRulePack", "inspect_rule_pack", "load_rule_pack", "rule_pack_hash"]


class LoadedRulePack(BaseModel):
    """A validated pack, its content address, and everything the validator wanted to say."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pack: RulePackSpec
    rule_pack_hash: str
    diagnostics: tuple[Diagnostic, ...]

    @property
    def rule_pack_version(self) -> str:
        """Return the pack's semantic version; participates in `run_id` (ADR-0013)."""
        return self.pack.rule_pack_version

    def rule_ids(self) -> tuple[str, ...]:
        """Return every rule identifier, in canonical sequence."""
        return tuple(rule.id for rule in self.pack.rules)

    def produced_event_types(self) -> tuple[str, ...]:
        """Return every event type some enabled rule explains, sorted and without repeats.

        This is the value `causalog.ontology_runtime.load_pack(produced_event_types=...)`
        has been waiting for. Supplying it turns `ONT-N-RULE-COVERAGE` from a
        `NOT_RUNNABLE` finding into a real check.

        **Disabled rules are excluded.** A rule switched off explains nothing today, and
        crediting its event type with an explanation would make disabling a rule invisible
        in coverage -- which is the one place it most needs to be visible.
        """
        produced: set[str] = set()
        for rule in self.pack.enabled_rules():
            produced.update(rule.produced_event_types())
        return tuple(sorted(produced))


def rule_pack_hash(pack: RulePackSpec) -> str:
    """Return the content address of a rule pack: `rul:<16 hex>`.

    Reuses `core.serialization.to_canonical_json` and `core.identifiers.digest`, so there is
    one hashing scheme in this system and no second path (the choice `ontology_hash` made,
    ADR-0028). It is computed over the validated model rather than the file bytes, so it is
    invariant to comments, indentation and key sequence -- none of which changes what the
    pack says -- and sensitive to every declared value, including a weight nudged by 0.01.
    """
    return digest(IdentifierPrefix.RULE_PACK, to_canonical_json(pack))


def _at(code: str, message: str, path: str, file: Path | None) -> Diagnostic:
    """Build one ERROR diagnostic located against the authored file."""
    return Diagnostic(severity=Severity.ERROR, code=code, message=message, path=path, file=file)


def _check_references(
    pack: RulePackSpec, vocabulary: VocabularyView, file: Path | None
) -> tuple[Diagnostic, ...]:
    """Return an ERROR for every name a rule uses that the vocabulary does not declare."""
    findings: list[Diagnostic] = []

    for rule in pack.rules:
        base = f"rules[{rule.id}]"

        for event_type in rule.event_types():
            if vocabulary.event_type(event_type) is None:
                findings.append(
                    _at(
                        "RUL-E-UNDECLARED-EVENT-TYPE",
                        f"rule '{rule.id}' names event type '{event_type}', which the "
                        "ontology pack does not declare. A rule that matches a type "
                        "nothing can emit is not a strict rule, it is a dead one.",
                        f"{base}.event_types",
                        file,
                    )
                )

        findings.extend(_check_relation(rule, vocabulary, base, file))
        findings.extend(_check_constraint(rule, vocabulary, base, file))
        findings.extend(_check_condition_addresses(rule, vocabulary, base, file))

    known_ids = {rule.id for rule in pack.rules}
    for rule in pack.rules:
        body = rule.body
        if not isinstance(body, ModifierBody):
            continue
        modifies = body.modifies
        if modifies not in known_ids:
            findings.append(
                _at(
                    "RUL-E-UNDECLARED-TARGET-RULE",
                    f"rule '{rule.id}' modifies '{modifies}', which this pack does not "
                    "declare. A modifier pointing at nothing rescales nothing and would "
                    "load as if it worked.",
                    f"rules[{rule.id}].body.modifies",
                    file,
                )
            )
    return tuple(findings)


def _check_relation(
    rule: Rule, vocabulary: VocabularyView, base: str, file: Path | None
) -> tuple[Diagnostic, ...]:
    """Check a rule's linkage names a declared relationship type and declared roles."""
    relation = rule.body.relation if not isinstance(rule.body, ConstraintBody) else None
    if relation is None:
        return ()
    findings: list[Diagnostic] = []
    if (
        relation.relationship_type is not None
        and vocabulary.relationship_type(relation.relationship_type) is None
    ):
        findings.append(
            _at(
                "RUL-E-UNDECLARED-RELATIONSHIP-TYPE",
                f"rule '{rule.id}' traverses relationship type "
                f"'{relation.relationship_type}', which the ontology pack does not "
                "declare.",
                f"{base}.body.relation.relationship_type",
                file,
            )
        )
    for label, role, pattern in _relation_role_sites(rule, relation):
        declared = vocabulary.event_type(pattern.event_type)
        if declared is None:
            continue
        if declared.participant(role) is None:
            findings.append(
                _at(
                    "RUL-E-UNDECLARED-ROLE",
                    f"rule '{rule.id}' binds role '{role}' on event type "
                    f"'{pattern.event_type}', which declares no such participant. "
                    "Conditions refer to roles, not to entity types, so a role the type "
                    "does not declare can never resolve.",
                    f"{base}.body.relation.{label}",
                    file,
                )
            )
    return tuple(findings)


def _relation_role_sites(
    rule: Rule, relation: EntityRelation
) -> tuple[tuple[str, str, EventPattern], ...]:
    """Return each (field label, role, event pattern) the linkage constrains."""
    body = rule.body
    cause_role = relation.cause_role
    effect_role = relation.effect_role
    if isinstance(body, CausalBody):
        return (
            ("cause_role", cause_role, body.cause),
            ("effect_role", effect_role, body.effect),
        )
    if isinstance(body, JointBody):
        sites: list[tuple[str, str, EventPattern]] = [
            ("cause_role", cause_role, member) for member in body.contributors
        ]
        sites.append(("effect_role", effect_role, body.effect))
        return tuple(sites)
    if isinstance(body, ModifierBody):
        return (("cause_role", cause_role, body.modifier),)
    return ()


def _check_constraint(
    rule: Rule, vocabulary: VocabularyView, base: str, file: Path | None
) -> tuple[Diagnostic, ...]:
    """Check a constraint names a declared entity type, a declared state, and a real target."""
    body = rule.body
    if not isinstance(body, ConstraintBody):
        return ()
    findings: list[Diagnostic] = []
    declared = vocabulary.entity_type(body.subject_entity_type)
    if declared is None:
        findings.append(
            _at(
                "RUL-E-UNDECLARED-ENTITY-TYPE",
                f"constraint '{rule.id}' names entity type "
                f"'{body.subject_entity_type}', which the ontology pack does not declare.",
                f"{base}.body.subject_entity_type",
                file,
            )
        )
        return tuple(findings)
    for label, state in (
        ("subject_state", body.subject_state),
        ("forbidden_state", body.forbidden_state),
    ):
        if state is None:
            continue
        if state not in declared.state_names:
            findings.append(
                _at(
                    "RUL-E-UNDECLARED-STATE",
                    f"constraint '{rule.id}' names state '{state}' on entity type "
                    f"'{declared.id}', whose declared states are "
                    f"{list(declared.state_names)}. A state absent from the lifecycle can "
                    "never hold, so the constraint would silently never fire.",
                    f"{base}.body.{label}",
                    file,
                )
            )
    if body.forbidden_event_type is not None:
        target = vocabulary.event_type(body.forbidden_event_type)
        if target is not None and target.participant(body.subject_role) is None:
            findings.append(
                _at(
                    "RUL-E-UNDECLARED-ROLE",
                    f"constraint '{rule.id}' binds role '{body.subject_role}' on event "
                    f"type '{body.forbidden_event_type}', which declares no such "
                    "participant.",
                    f"{base}.body.subject_role",
                    file,
                )
            )
    return tuple(findings)


def _check_condition_addresses(
    rule: Rule, vocabulary: VocabularyView, base: str, file: Path | None
) -> tuple[Diagnostic, ...]:
    """Check every address in a condition tree names a declared binding, role and attribute."""
    findings: list[Diagnostic] = []
    declared_bindings = set(rule.bindings())
    patterns = _patterns_by_binding(rule)
    for address in rule.conditions().addresses():
        rendered = address.rendered()
        if address.binding not in declared_bindings:
            findings.append(
                _at(
                    "RUL-E-UNDECLARED-BINDING",
                    f"rule '{rule.id}' reads '{rendered}', but declares no binding "
                    f"'{address.binding}'. Its bindings are {sorted(declared_bindings)}.",
                    f"{base}.body.conditions",
                    file,
                )
            )
            continue
        pattern = patterns.get(address.binding)
        if pattern is None:
            continue
        declared = vocabulary.event_type(pattern)
        if declared is None:
            continue
        participant = declared.participant(address.role)
        if participant is None:
            findings.append(
                _at(
                    "RUL-E-UNDECLARED-ROLE",
                    f"rule '{rule.id}' reads '{rendered}', but event type '{pattern}' "
                    f"declares no role '{address.role}'.",
                    f"{base}.body.conditions",
                    file,
                )
            )
            continue
        entity_type = vocabulary.entity_type(participant.entity_type)
        known = set(declared.required_attributes)
        if entity_type is not None:
            known |= set(entity_type.attribute_names)
        if address.attribute not in known:
            findings.append(
                _at(
                    "RUL-E-UNDECLARED-ATTRIBUTE",
                    f"rule '{rule.id}' reads '{rendered}', but neither event type "
                    f"'{pattern}' nor the entity type filling role '{address.role}' "
                    f"declares attribute '{address.attribute}'. A condition over an "
                    "attribute nothing carries evaluates to absent on every record, which "
                    "is a rule that never fires rather than a rule that is strict.",
                    f"{base}.body.conditions",
                    file,
                )
            )
    return tuple(findings)


def _patterns_by_binding(rule: Rule) -> dict[str, str]:
    """Return each binding label mapped to the event type it matches."""
    body = rule.body
    if isinstance(body, CausalBody):
        return {
            body.cause.binding: body.cause.event_type,
            body.effect.binding: body.effect.event_type,
        }
    if isinstance(body, JointBody):
        mapped = {member.binding: member.event_type for member in body.contributors}
        mapped[body.effect.binding] = body.effect.event_type
        return mapped
    if isinstance(body, ConstraintBody):
        return {} if body.forbidden_event_type is None else {"SUBJECT": body.forbidden_event_type}
    return {body.modifier.binding: body.modifier.event_type}


def _static_conflicts(pack: RulePackSpec) -> tuple[str, ...]:
    """Return a message for every contradiction detectable without facts.

    Two shapes are genuinely decidable here, and only two.

    **Opposed modifiers.** An `AMPLIFICATION` and an `INHIBITION` that name the same target
    rule, the same modifier event type, the same linkage, and carry no condition between
    them. The same trigger is asserted to push one claim's magnitude up and down at once,
    with nothing to separate the two cases, so which one applies depends on the sequence the
    evaluator happens to walk the pack in. That is the runtime coin-flip `CONVENTIONS.md` §7
    forbids, and it is a load error.

    **Duplicated rules.** Two enabled rules of one kind with the same pattern, linkage and
    condition tree, differing only in identity or weight. Both fire on every match, so every
    candidate is counted twice by two rules nobody meant to be two rules.

    What is deliberately NOT checked here, and why
    ----------------------------------------------
    A constraint and a generator naming one event type are **not** a contradiction, and an
    earlier draft of this function treated them as one. A constraint is scoped to an entity
    in a named state -- "a line already withdrawn cannot be dispatched" -- while a generator
    is not. The two are complementary: the generator proposes, the constraint prunes the
    subset the state rules out. Refusing that pair at load would refuse the exact pack this
    seam exists to support, and it would push authors toward writing constraints that are
    too weak to prune anything.

    Whether two condition trees can hold together at all is a satisfiability question this
    loader does not answer. Fact-dependent disagreements are resolved at evaluation by the
    documented precedence and are REPORTED (ADR-0047). What is not checked here is stated as
    a `NOT_RUNNABLE` finding rather than left to be assumed.
    """
    messages: list[str] = []

    modifiers: dict[tuple[str, str, str], list[tuple[str, RuleKind]]] = {}
    for rule in pack.enabled_rules():
        body = rule.body
        if not isinstance(body, ModifierBody) or not body.conditions.is_trivial():
            continue
        key = (
            body.modifies,
            body.modifier.event_type,
            body.relation.model_dump_json(),
        )
        modifiers.setdefault(key, []).append((rule.id, rule.kind))

    for (target, event_type, _), members in sorted(modifiers.items()):
        kinds = {kind for _, kind in members}
        if RuleKind.AMPLIFICATION in kinds and RuleKind.INHIBITION in kinds:
            named = ", ".join(f"'{identifier}' ({kind.value})" for identifier, kind in members)
            messages.append(
                f"{named} all modify rule '{target}' on the same event type "
                f"'{event_type}' through the same linkage, with no condition on any of "
                "them. One raises the magnitude and another lowers it for the identical "
                "trigger, so which applies would depend on evaluation sequence. Give them "
                "conditions that separate the cases, or delete one."
            )

    shapes: dict[str, list[str]] = {}
    for rule in pack.enabled_rules():
        signature = f"{rule.kind.value}|{rule.body.model_dump_json()}"
        shapes.setdefault(signature, []).append(rule.id)
    for identifiers in sorted(shapes.values()):
        if len(identifiers) > 1:
            messages.append(
                f"rules {identifiers} are identical in kind, pattern, linkage and "
                "condition, and differ only in identity or weight. Both fire on every "
                "match, so every candidate they propose is counted twice."
            )

    return tuple(messages)


def inspect_rule_pack(
    pack_path: Path, *, vocabulary: VocabularyView | None = None
) -> tuple[RulePackSpec, tuple[Diagnostic, ...]]:
    """Parse and check one rule pack, returning it with every finding.

    Raises:
        ContractViolationError: the file is unreadable, is not one YAML mapping, or does not
            validate against the DSL.
        RuleConflictError: the pack contradicts itself. Raised here rather than returned as
            a diagnostic, because `CONVENTIONS.md` §7 makes a self-contradictory pack a load
            failure and not a judgement the caller may weigh.
    """
    try:
        document = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractViolationError(f"rule pack {pack_path} could not be read: {error}") from error
    except yaml.YAMLError as error:
        raise ContractViolationError(f"rule pack {pack_path} is not valid YAML: {error}") from error

    if not isinstance(document, dict):
        raise ContractViolationError(
            f"rule pack {pack_path} is not a mapping at its root; a pack is one document "
            "declaring `rules`."
        )

    try:
        pack = RulePackSpec.model_validate(document)
    except ValidationError as error:
        raise ContractViolationError(f"rule pack {pack_path} is not valid:\n{error}") from error

    if pack.rule_pack_schema_version != RULE_PACK_SCHEMA_VERSION:
        raise ContractViolationError(
            f"rule pack {pack_path} declares rule_pack_schema_version "
            f"{pack.rule_pack_schema_version!r}; this distribution implements "
            f"{RULE_PACK_SCHEMA_VERSION!r}. A pack written against another DSL version is "
            "refused rather than reinterpreted, because reinterpreting it silently changes "
            "what its rules mean."
        )

    conflicts = _static_conflicts(pack)
    if conflicts:
        raise RuleConflictError(
            f"rule pack {pack_path} contradicts itself; {len(conflicts)} conflict(s). A "
            "contradictory pack fails at load, never as a runtime coin-flip "
            "(CONVENTIONS.md §7):\n  " + "\n  ".join(conflicts)
        )

    findings: list[Diagnostic] = []
    if vocabulary is None:
        findings.append(
            Diagnostic(
                severity=Severity.NOT_RUNNABLE,
                code="RUL-N-VOCABULARY",
                message=(
                    "no ontology vocabulary was supplied, so 'every type, role, state and "
                    "attribute a rule names is declared' was NOT CHECKED. This is reported "
                    "rather than skipped: a check that could not run must never read as a "
                    "check that passed (DEF-0001, OQ-014)."
                ),
                file=pack_path,
            )
        )
    else:
        findings.extend(_check_references(pack, vocabulary, pack_path))

    findings.append(
        Diagnostic(
            severity=Severity.NOT_RUNNABLE,
            code="RUL-N-CONDITIONAL-CONFLICT",
            message=(
                "contradictions between two rules that BOTH carry conditions were not "
                "checked statically: deciding whether two condition trees can hold together "
                "is a satisfiability question this loader does not answer. Such pairs are "
                "resolved at evaluation by the documented precedence and reported in the "
                "ConflictReport (ADR-0047)."
            ),
            file=pack_path,
        )
    )
    return pack, tuple(findings)


def load_rule_pack(pack_path: Path, *, vocabulary: VocabularyView | None = None) -> LoadedRulePack:
    """Load and validate one rule pack, returning it with its content address.

    Args:
        pack_path: the authored `rules.yaml`.
        vocabulary: the declared names, from
            `causalog.extraction.ontology_adapters.vocabulary_of`. `None` makes the
            reference checks report `NOT_RUNNABLE` rather than pass.

    Raises:
        ContractViolationError: the pack is malformed, or any diagnostic is an `ERROR`. The
            message carries every error, not just the first -- an author who reloads ten
            times learns to distrust the tenth message.
        RuleConflictError: the pack contradicts itself.
    """
    pack, findings = inspect_rule_pack(pack_path, vocabulary=vocabulary)
    errors = tuple(item for item in findings if item.severity is Severity.ERROR)
    if errors:
        raise ContractViolationError(
            f"{pack_path} is not a valid rule pack; {len(errors)} error(s):\n" + render(errors)
        )
    return LoadedRulePack(pack=pack, rule_pack_hash=rule_pack_hash(pack), diagnostics=findings)
