# `causalog.causal_engine.root_cause_analyzer`

**Layer rank:** `L6` · **Module 11** · Status `built-unverified`

## Single responsibility

Rank causes by consequence prevented, with structural earliness reported separately.

## The ruling this module is built around

`prd.md` §29 defines a root cause as the earliest **actionable** event whose modification would prevent the largest downstream consequence, and then gives the example that settles the design:

> An external event → a knock-on effect → a controllable step → a downstream complaint
> "The [external event] may be earliest. The [controllable step] may be actionable. **The system should distinguish both.**"

*(prd.md §29's example, with two of its four node names replaced by their structural role. The literal names are domain vocabulary and the LAW-DOMAIN lint refuses them inside a reasoning package — correctly, since it is the shape and not the vocabulary that the ruling turns on.)*

ADR-0008 ruled on it. Earliness and prevented consequence are not commensurable; any weighting between them would be an unexplainable constant; LAW-EVIDENCE forbids a number whose parts cannot be inspected.

## What it produces

**Four separately labelled fields, and no fifth field collapsing them.**

| Field | The question it answers |
|---|---|
| `earliest_cause` | where did this start? |
| `highest_consequence_cause` | what single removal prevents the most? |
| `most_actionable_cause` | what can anybody actually change? |
| `actionable_root_causes` | what should we change? |

Wherever two of them name different events a `TradeOff` is emitted naming which two, what each is answering, and what preferring one gives up — so a user who disagrees with the recommendation can see the alternative and the reason it lost. When all four agree, that is reported too: a simple chain is worth saying explicitly rather than printing four identical rows.

## There is no root-cause score anywhere in this package

Not an omission. The number would have to weight a quantity against a position in a chain, so any figure produced would be a judgement disguised as arithmetic, and it would move the headline answer without anybody being able to say why.

`sequencing_value` is ADR-0008's literal prevented-times-confidence criterion, names the function in `causalog.core.ranking` that produced it, and is **one of five signals carried side by side** — not a score. `RankedCause.sort_key` is a tuple whose elements a reader can read off one at a time; earliness enters it at position two, as a tie-break, never as a weighted term.

## Five signals, carried separately

| Signal | Source |
|---|---|
| consequence prevented | module 12's counterfactual-lite: re-reachability with the node deleted, correct on diamonds by construction |
| actionability | `Event.is_actionable`, refined but never overridden by declared cost and severity ranks |
| earliness | structural backward distance in the graph, ranked — not a reading of any clock |
| chain confidence | composed under a named function, with path length beside it |
| recurrence | how often the shape appears across the run, counted always and classified only when the pack declares a threshold |

Every ranked result carries its evidence chain and its whole `ConfidenceVector`, never a scalar.

## Actionability is declared and cannot be validated

`Event.is_actionable` is stamped at generation time (ADR-0008) precisely so this module, at `L6`, never reads the ontology — forbidden edge F3. Where the stamp and the current pack disagree, the disagreement is **reported** and the stamp is used: silently preferring either would move the headline answer with nothing recording that it had.

**R-15 stands unmitigated.** A mis-declared flag changes the recommendation and nothing here can detect it. That sentence is printed above every ranking, as a property no revision can soften.

## What it structurally cannot do

- **Create a link.** `CausalEdge` is never constructed here and `ProvenanceClass.INFERRED` is never assigned here — asserted over the AST by `tests/law/test_ranking_never_collapses.py`.
- **Return one field where four are required.** Enforced by `RootCauseRanking`'s validator, which also refuses an unactionable recommendation and a headline view absent from the candidate list beneath it.
- **Present a plateau as a ranking.** Where every recommended candidate carries one sequencing value the engine cannot separate them; the report says so and does not break the tie.

## Forbidden dependencies

Everything above `L6`; `ontology_runtime` (F3); `causalog.persistence` (F4); creating an edge; scoring (module 10's); proposing a pair (module 9's).

## Every parameter is declared, none is a literal

`ranking_function`, `minimum_chain_confidence`, `candidate_cap` and `recurrence_minimum_support` come from the pack's `root_cause_analysis` block (`rule_pack_schema_version` 1.5.0). An absent declaration means the policy **cannot run**, is reported with what it would have needed, and is never defaulted (ADR-0049).

There is deliberately **no weighting field** between earliness and consequence. It is absent because ADR-0008 rules the number must not exist, not because nobody has added it.

See `docs/architecture.md` §1 for the layer map and §2 for this package's module contract.
