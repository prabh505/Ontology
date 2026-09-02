"""Two evaluations over the same facts produce byte-identical output.

`CONVENTIONS.md` §11 makes this a Definition-of-Done item for every module: identical inputs
plus identical seed plus identical `ontology_hash` yield byte-identical outputs. The threat
here is specific -- a rule engine walks dictionaries of buckets and emits a list whose
sequence nobody looks at, which is exactly the shape that varies between runs without
anybody noticing.
"""

from __future__ import annotations

from causalog.core.serialization import to_canonical_json
from causalog.rule_engine import evaluate, rule_pack_hash
from causalog.rule_engine.facts import FactSet
from tests.fixtures.rules import constraint, pack, rule, two_stage_facts


def _evaluated(facts: FactSet) -> str:
    """Return the canonical serialization of one evaluation's firings and conflicts."""
    result = evaluate(pack(rule(), constraint()), facts)
    return to_canonical_json(result)


def test_two_evaluations_over_one_fact_set_are_byte_identical() -> None:
    """The base guarantee."""
    facts, _, _, _ = two_stage_facts(closed=True)
    assert _evaluated(facts) == _evaluated(facts)


def test_the_output_does_not_depend_on_the_sequence_the_facts_arrived_in() -> None:
    """A caller that assembled its inputs differently must reach the same conclusion.

    `FactSet.of` sequences at the boundary rather than trusting the caller, for the same
    reason `Event.address` sorts its participants: the canonical sequence is part of the
    contract, so it is applied where the contract is entered.
    """
    facts, _, _, _ = two_stage_facts(closed=True)

    forwards = FactSet.of(
        events=facts.events(),
        states=facts.states(),
        relationships=facts.relationships(),
    )
    backwards = FactSet.of(
        events=tuple(reversed(facts.events())),
        states=tuple(reversed(facts.states())),
        relationships=tuple(reversed(facts.relationships())),
    )
    assert _evaluated(forwards) == _evaluated(backwards)


def test_the_output_does_not_depend_on_the_authored_rule_sequence() -> None:
    """A pack grouped for a reader must evaluate the same as one grouped any other way."""
    facts, _, _, _ = two_stage_facts(closed=True)

    forwards = to_canonical_json(evaluate(pack(rule(), constraint()), facts))
    backwards = to_canonical_json(evaluate(pack(constraint(), rule()), facts))
    assert forwards == backwards


def test_the_pack_hash_is_stable_across_two_computations() -> None:
    """`rule_pack_version` participates in `run_id`, so its address must not drift."""
    built = pack(rule(), constraint())
    assert rule_pack_hash(built) == rule_pack_hash(built)


def test_statistics_are_stable_across_two_evaluations() -> None:
    """The counters are part of the output, so they are part of the guarantee."""
    facts, _, _, _ = two_stage_facts(closed=True)
    first = evaluate(pack(rule(), constraint()), facts).statistics
    second = evaluate(pack(rule(), constraint()), facts).statistics
    assert first == second
