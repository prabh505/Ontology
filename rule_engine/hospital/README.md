# `rule_engine/hospital/` — the domain-independence proof for the rule DSL

**There is no dataset behind this pack, and there is not meant to be.**
`ontology/packs/hospital/` exists for one reason (ADR-0026): "an unrelated domain with no
dataset behind it, carried as proof that the DSL is not secretly logistics-shaped." This
directory extends that proof to the **rule** DSL.

The argument only works if something exercises it. `rule_engine/dataco/rules.yaml` cannot
show that the rule schema is domain-neutral — a schema built around one domain will always
express that domain fluently. A second pack over a vocabulary sharing no term with logistics
can, and `backend/tests/ontology/test_rule_pack_loads.py` loads both through the identical
code path.

What this pack exercises: all six rule kinds (`CONSTRAINT`, `CAUSAL`, `CONDITIONAL`,
`JOINT`, `AMPLIFICATION`, and the modifier bound), a condition tree over a role-bound
attribute, a terminal-state prohibition, and a joint cause — none of them with a logistics
term anywhere.

## What it does not prove

**It proves the schema is domain-neutral. It does not prove the ENGINE is.**
`docs/architecture.md` §1.5 states the residual precisely: a reasoning package that branches
on the *value* of an event-type string is domain-dependent while containing no banned
token, and LAW-DOMAIN's vocabulary lint cannot see it. The real proof of that is
`tests/ontology/test_ontology_swap.py`, which asserts a swap changes what the engine
*concludes* — and which `docs/architecture.md` §8 still carries as open. This pack is one
input that test will need; it is not a substitute for it.

Every rule here is `DOMAIN_EXPERTISE` or `ASSUMPTION` by necessity. A `DATASET_OBSERVATION`
would be a claim about data that does not exist.
