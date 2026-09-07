# `causalog.causal_engine.pattern_miner`

**Layer rank:** `L6` · **Not one of the sixteen modules** · Status `built-unverified`

## Single responsibility

Find what recurs across a whole run: type-level motifs and chronic bottlenecks.

## Why this is not a module

`prd.md` §36 lists sixteen modules and none of them answers a question about the run — modules 11 and 12 both answer questions about **one** outcome. `prd.md` §10 nonetheless names a user, Executive Leadership, who "needs strategic patterns rather than individual incidents".

The Causal Graph Builder set the precedent (OQ-025, ADR-0054): PRD-required work that §36 names no owner for lands as a named package beside the modules, not smuggled into one of their remits. Module 11's contract is "rank causes by consequence prevented" and module 12's is "measure how an effect spreads from a seed". Cross-run mining is neither, and widening either would make `docs/architecture.md` §2 wrong about what that module does.

## What it produces

| Artifact | What it holds |
|---|---|
| `Motif` | one recurring cause-type → effect-type shape, its claim count, and the process instances it spans |
| `Bottleneck` | one chronically busy type, with in-degree and out-degree kept apart |
| `StructuralPatternReport` | both, with a stated reason beside every empty section |

## Rules this module holds

**Everything runs over the event-TYPE projection, never over instances.** The altitude `causal_graph_builder.cycles` chose, for the reason stated there: a claim about instances is unique by construction, so a recurrence counter running at that level could only ever return one.

**The cost of that choice is on every row.** A shape reported here may be carried by one pathological instance repeating, so every finding shows the process instances it spans beside its raw count. One type firing forty times inside one instance is a local pathology; the same count across forty instances is systemic; one number cannot tell them apart.

**In-degree and out-degree are never summed.** A type consequence collects at and a type consequence originates from are different structures needing different responses.

**There is no combined "importance" figure.** The weighting between "happens often" and "costs a lot when it happens" would be an unexplainable constant — the same objection ADR-0008 raises to a blended root-cause score, one level up.

**An empty list is never published alone.** It reads as "there are none", and it may instead mean nothing was looked for. Every empty section carries a sentence saying which, and the report's validator refuses one that does not.

## Forbidden dependencies

Everything above `L6`; `ontology_runtime` (F3); `causalog.persistence` (F4). It creates no link and assigns no provenance class — only `causal_graph_builder/policy.py` may assign `INFERRED`.

## Every parameter is declared, none is a literal

`motif_minimum_support`, `motif_maximum_length` and `bottleneck_minimum_degree` are read from the pack's `pattern_mining` block (`rule_pack_schema_version` 1.5.0). An absent declaration means nothing is looked for and the report says so (ADR-0049) — how many repetitions make a pattern, and what degree makes a hub, both depend on how many types the domain declares.

**This version enumerates motifs of length two only**, and the report states that against the declared maximum rather than implying that longer shapes were searched for and not found.

See `docs/architecture.md` §1 for the layer map.
