"""Synthetic, domain-neutral rule packs and facts for the rule-engine tests.

`CONVENTIONS.md` §14: fixtures are synthetic and domain-neutral by default, and
DataCo-derived fixtures live only in `tests/fixtures/dataco/`. Nothing here names a real
domain -- the event types are `STAGE_ONE` and `STAGE_TWO`, the entity type is
`PARTICIPANT`. A rule-engine test written in supply-chain vocabulary would read as though
the evaluator knew something about supply chains, and the whole claim of this layer is that
it does not.

Fact builders are reused from `tests/fixtures/facts.py` rather than duplicated, so a change
to a core address recipe breaks these tests too instead of leaving them passing against a
private copy of the old shape.
"""

from __future__ import annotations

from typing import Any

from causalog.core.ontology_view import VocabularyView
from causalog.core.types import Entity, Event
from causalog.rule_engine.dsl import RulePackSpec
from causalog.rule_engine.facts import FactSet
from tests.fixtures.facts import entity, evidence_record, interval, relationship, state

#: The two event types every synthetic rule reasons over, and a third that no rule names --
#: carried so a coverage test has a type to report as a blind spot.
STAGE_ONE = "STAGE_ONE"
STAGE_TWO = "STAGE_TWO"
STAGE_THREE = "STAGE_THREE"

PARTICIPANT = "PARTICIPANT"


def vocabulary() -> VocabularyView:
    """Return the declared names the synthetic packs are validated against."""
    return VocabularyView.model_validate(
        {
            "event_types": [
                {
                    "id": name,
                    "participants": [
                        {"role": "SUBJECT", "entity_type": PARTICIPANT, "required": True}
                    ],
                    "required_attributes": ["stage"],
                }
                for name in (STAGE_ONE, STAGE_THREE, STAGE_TWO)
            ],
            "entity_types": [
                {
                    "id": PARTICIPANT,
                    "state_names": ["CLOSED", "OPEN"],
                    "terminal_state_names": ["CLOSED"],
                    "attribute_names": ["label", "stage"],
                }
            ],
            "relationship_types": [
                {
                    "id": "BELONGS_TO",
                    "from_entity_type": PARTICIPANT,
                    "to_entity_type": PARTICIPANT,
                }
            ],
        }
    )


def rule(
    identifier: str = "R-ONE", *, replace_body: dict[str, Any] | None = None, **overrides: Any
) -> dict[str, Any]:
    """Return a well-formed CAUSAL rule document, with any field overridden.

    `body=` MERGES into the default causal body, which is what a test tweaking one window
    or one linkage wants. `replace_body=` swaps it wholesale, which is what a test changing
    the rule's KIND needs -- merging there would leave the causal body's fields behind and
    the failure would be an `extra_forbidden` about `cause`, not the refusal under test.
    """
    document: dict[str, Any] = {
        "id": identifier,
        "kind": "CAUSAL",
        "description": "stage one precedes stage two",
        "rationale": "the synthetic process declares the two adjacently",
        "author": "fixture",
        "knowledge_provenance": "DOMAIN_EXPERTISE",
        "evidence_basis": "the fixture's declared sequence",
        "base_strength": 0.5,
        "body": {
            "cause": {"binding": "CAUSE", "event_type": STAGE_ONE},
            "effect": {"binding": "EFFECT", "event_type": STAGE_TWO},
            "window": {"minimum_seconds": 0, "maximum_seconds": 864000},
            "relation": {
                "direction": "SHARED_PARTICIPANT",
                "cause_role": "SUBJECT",
                "effect_role": "SUBJECT",
            },
        },
    }
    body_overrides = overrides.pop("body", None)
    document.update(overrides)
    if replace_body is not None:
        document["body"] = replace_body
    elif body_overrides is not None:
        document["body"] = {**document["body"], **body_overrides}
    return document


def constraint(
    identifier: str = "C-ONE",
    *,
    subject_state: str = "CLOSED",
    forbidden_event_type: str = STAGE_TWO,
    **overrides: Any,
) -> dict[str, Any]:
    """Return a well-formed CONSTRAINT rule document."""
    document: dict[str, Any] = {
        "id": identifier,
        "kind": "CONSTRAINT",
        "description": "a closed participant produces no further stage",
        "rationale": "CLOSED is declared terminal",
        "author": "fixture",
        "knowledge_provenance": "DOMAIN_EXPERTISE",
        "evidence_basis": "the fixture lifecycle declares CLOSED terminal",
        "base_strength": 1.0,
        "body": {
            "subject_entity_type": PARTICIPANT,
            "subject_state": subject_state,
            "subject_role": "SUBJECT",
            "forbidden_event_type": forbidden_event_type,
        },
    }
    body_overrides = overrides.pop("body", None)
    document.update(overrides)
    if body_overrides is not None:
        document["body"] = {**document["body"], **body_overrides}
    return document


def pack(*rules: dict[str, Any], version: str = "1.0.0") -> RulePackSpec:
    """Return a validated pack around the given rule documents."""
    return RulePackSpec.model_validate(
        {
            "rule_pack_schema_version": "1.0.0",
            "rule_pack_id": "fixture",
            "rule_pack_version": version,
            "ontology_pack": "fixture",
            "description": "synthetic pack",
            "rules": list(rules),
        }
    )


def two_stage_facts(
    *,
    cause_day: int = 0,
    effect_day: int = 2,
    span_days: int = 0,
    shared: bool = True,
    closed: bool = False,
) -> tuple[FactSet, Event, Event, Entity]:
    """Return a fact set holding one `STAGE_ONE` and one `STAGE_TWO`.

    `shared=False` gives the two events different participants, so a `SHARED_PARTICIPANT`
    linkage finds nothing -- the negative case every linkage test needs.

    `closed=True` additionally puts the subject in `CLOSED`, which is what a terminal-state
    constraint fires on.
    """
    from tests.fixtures.facts import event as build_event

    citation = evidence_record("fixture/0001")
    subject = entity("subject-a", PARTICIPANT, citation=citation)
    other = entity("subject-b", PARTICIPANT, citation=citation)

    first = build_event(
        STAGE_ONE,
        interval(cause_day, span_days=span_days),
        citation=citation,
        participants=(subject,),
    )
    second = build_event(
        STAGE_TWO,
        interval(effect_day, span_days=span_days),
        citation=citation,
        participants=(subject,) if shared else (other,),
    )
    states = ()
    if closed:
        states = (
            state(
                subject,
                "CLOSED",
                interval(cause_day, span_days=365),
                derived_from=first,
                citation=citation,
            ),
        )
    facts = FactSet.of(
        events=(first, second),
        states=states,
        relationships=(relationship(subject, other, citation=citation),),
    )
    return facts, first, second, subject
