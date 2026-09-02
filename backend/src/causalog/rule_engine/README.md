# `causalog.rule_engine`

**Layer rank:** `L5`

## Single responsibility

Load, conflict-check, and evaluate rule packs against graph facts.

## Forbidden dependencies

`causal_engine` and above. Also `ontology_runtime`: this package is L5 and forbidden edge
F3 blocks L4–L10 from importing it, so the declared vocabulary arrives as a plain
`core.ontology_view.VocabularyView` produced by an adapter in `extraction` (ADR-0046).

Rule **data** lives in `/rule_engine/<domain>/`. This package holds code only and is NOT
exempt from the LAW-DOMAIN lint.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.

## The three properties this package exists to guarantee

**Rules are data.** There is no expression string, no callable reference and no plugin hook
anywhere in `dsl.py` — asserted over the generated JSON Schema in
`tests/unit/rule_engine/test_dsl.py`, so a field added later is caught without anyone
remembering to update a list. A condition that cannot be written as a closed operator tree
needs a new operator and an ADR, never an escape hatch (prd.md §46, ADR-0044).

**A firing that cannot explain itself does not exist.** `RuleFiring` refuses to construct
without its trace. Not a lint, not a review convention, not a nullable field — a defect that
is representable eventually gets represented (ADR-0047).

**Constraints beat generators, and every suppression is reported.** The precedence policy is
one sentence and is applied unconditionally; the conflict is reported rather than resolved
silently. An absent edge is the one kind of error this system cannot otherwise surface
(`docs/architecture.md` §8, risk 2), so a suppression that is visible is one absence that is
no longer silent.

## What it does not do

It does not create a `CausalEdge`, assign confidence, or read `Event.trigger`. Module 9 owns
the LAW-TIME gate and edge construction; module 10 assembles confidence; ADR-0020 forbids the
third. All three are asserted in `tests/law/test_a_firing_explains_itself.py` — the first two
by checking this package's own imports, the third over the AST.

## Modules

```
dsl.py          the normative pydantic models. A pack file is one YAML document validated
                against them.
diagnostics.py  ERROR / WARNING / NOT_RUNNABLE. The third is the point.
loader.py       parse, refuse a self-contradictory pack at load, check every reference.
facts.py        `GraphFacts` -- what the evaluator reads, as values rather than as a store.
index.py        the bucketing and bisection the complexity bound rests on.
evaluate.py     deterministic evaluation, with the trace built as it goes.
trace.py        `RuleFiring`. Refuses to exist without its reasoning.
conflict.py     the precedence policy, and the report of every time it was applied.
coverage.py     which event types have an explanatory rule, and which are blind spots.
```

## Complexity

Evaluation is `O(E·p + S + R + Σ_r(|C_r|·log|F_r| + m_r))` — linear in the inputs plus the
output, never quadratic in the event count. The derivation is in `index.py`'s docstring; the
bound is **asserted against a returned counter** in
`tests/unit/rule_engine/test_complexity_bound.py`, which also proves its own threshold
rejects a quadratic scan. A claim like this in a comment is worth nothing: the naive
implementation passes every correctness test in this package and differs only in how long it
takes.
