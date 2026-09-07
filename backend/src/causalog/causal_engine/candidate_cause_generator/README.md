# `causalog.causal_engine.candidate_cause_generator`

**Layer rank:** `L6` · **Module 9** · Status `built-unverified`

## Single responsibility

Propose temporally admissible candidate causes (prd.md §27), each carrying the evidence that
produced it. **Hypotheses, never conclusions.**

## What it produces

`CandidateEdge` values in a `CandidateGraph` multigraph, plus `ConfoundingFlag` values and a
`CandidateGraphReport`. Seven generators, one gate, one report.

## What it structurally cannot do

- **Assign confidence.** `CandidateEdge` has no confidence field. A generator cannot score
  because the artifact has nowhere to put a score (ADR-0048).
- **Rank.** The per-effect cap selects round-robin across generators, because every
  plausibility sequence is a ranking wearing a bound's clothing (ADR-0050).
- **Prune on "seems unlikely".** The only refusals are a LAW-TIME violation, a self-pair, a
  declared constraint, and the declared cap. All four are counted and reported.
- **Drop an `UNDETERMINED` candidate.** Retained, flagged, blocked from `INFERRED`, reported
  as a ratio (`CONTEXT.md` R-14).
- **Resolve confounding.** It makes two structures visible and says on every flag that
  visibility is not resolution — and that an absent flag is not evidence of absence
  (ADR-0051).
- **Read `Event.trigger`** (ADR-0020), **construct a `CandidateEdge` outside `gate.py`**, or
  **build a `ConfidenceVector`**. All three asserted over the AST in
  `tests/law/test_law_time_gates_every_candidate.py`, so an eighth generator that broke one
  fails on the day it is written.

## Forbidden dependencies

Everything above L6. `ontology_runtime` (F3), `causalog.persistence` (F4), and every library
in F9. Owns the LAW-TIME gate; may never assign confidence.

## What it reads

`GraphFacts` (the by-value protocol `rule_engine.facts` established), `tuple[Timeline, ...]`,
the rule pack's `candidate_generation` block, and a `rule_engine.EvaluationResult`.

**Not `TemporalPropertyGraph`:** module 8 does not exist. `GraphFacts` is what module 8 will
satisfy when it lands, without this module changing.

## Every parameter is declared, none is a literal

Windows, hop bound, support floor, lift floor, per-effect cap and each generator's evidence
weight all come from `rule_engine/<domain>/rules.yaml` (ADR-0049). **An absent parameter makes
its generator `NOT_RUNNABLE`, which is deliberately not the same as zero** — a generator that
did not run and one that ran and found nothing are different findings, and the report keeps
them apart.

Enforced by `scripts/check_layers.py`, `scripts/check_domain_independence.py`, and
`scripts/check_metrics_are_declared.py` — the last of which is clean over this package with
no allowlist entry.

See `docs/architecture.md` §1 for the layer map and §2 for this package's module contract.
