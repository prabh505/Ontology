# Project CausaLog

A **domain-agnostic causal intelligence engine**. It ingests historical event data and
produces an explainable causal knowledge graph supporting root-cause identification,
propagation measurement, counterfactual simulation, and ranked intervention
recommendation — with every assertion carrying inspectable evidence and an explicit
provenance class.

The first implementation uses the DataCo SMART Supply Chain dataset because it is a
convenient reference domain, not because the system is about logistics. **The domain is
replaceable. The reasoning engine is not.**

## Current state

Phase **P0 (Governance)** closing. The architecture blueprint, the repository scaffold, the
law-enforcement tooling, the frozen canonical core, the ontology layer and the persistence
layer exist. **Two of the 16 modules are built** — 1 Data Adapter and 2 Schema Mapper, both
`built-unverified` — so the reference dataset can be pinned, profiled, validated, cleaned and
mapped, but **there is still no `Event`, no graph, and no inference.**

```bash
make import DATASET=dataco     # pins the file, measures it, publishes the report
```

The published Data Quality Report for the reference dataset is at
`docs/reports/dataco/<dataset_version>/`. **Read its headline constraints first** — they bound
what any causal claim about this dataset can ever mean, and one of them corrects an assumption
this project held for a week (DEF-0004).

See `CONTEXT.md` for the authoritative answer to "where is this project right now", and
`PROGRESS.md` §01a for what was built, what it measured, and what it deliberately does not
check.

## If you are a new session, read in this order

| # | File | Answers |
|---|---|---|
| 1 | `CONTEXT.md` | Where the project is, what is frozen, what is undecided |
| 2 | `CONVENTIONS.md` | The Five Inviolable Laws; naming, logging, errors, seeding, tests |
| 3 | `DECISIONS.md` | What was already decided and why (the ADR log) |
| 4 | `GLOSSARY.md` §2 | The six overloaded terms |
| 5 | `PROGRESS.md` | What exists, what was deliberately omitted |
| 6 | `docs/architecture.md` | Layer ranks, forbidden edges, storage boundary, Run model |
| 7 | `docs/prd.md` | Product intent — relevant sections only |

`HANDOFF.md` is the transfer protocol, including the staleness checks to run after a gap.

## Getting started

```bash
make setup
```

```bash
make verify
```

```bash
make up
```

```bash
make migrate
```

`make verify` is `lint typecheck test` in one command. **`make up` deliberately does not
migrate** — PostgreSQL's init directory applies `*.sql` without writing the migration
ledger, which leaves a schema that exists and a history saying nothing was applied, and the
disagreement stays invisible until a later migration fails on an object it did not create
(ADR-0033). Run `make migrate` after `make up`; `make migrate-status` shows what is applied
and what is pending. `make up` runs `make doctor` first,
which checks the container runtime and every published host port and names the remedy for
whatever is missing — so the two failures that actually happen arrive diagnosed:

- **Memory.** Allocate the container runtime **at least 4 GB**. Neo4j is the constraint:
  below that — or with unrelated containers holding most of the budget — it is OOM-killed
  during startup and exits 137, which reads like a configuration error and is not one.
  Every service declares a `mem_limit`, so a kill names its container.
- **Ports.** Every published port is overridable in `deployment/.env` without editing the
  compose file; `make doctor` prints the exact line to add. Ports this project already
  publishes are not conflicts, so `make up` is idempotent.

## Layout

| Path | Holds |
|---|---|
| `backend/` | the one installable Python distribution, `causalog` (ADR-0012) |
| `frontend/` | Next.js + TypeScript; the six workspaces (prd.md §51), not yet built |
| `ontology/` | domain vocabulary as **data** — `packs/<domain>/ontology.yaml`; replacing this is how a domain is added (`docs/ontology.md`) |
| `rule_engine/` | rule packs as **data** — `dataco/` and `hospital/` (the evaluator code lives in the backend, and contains none of their vocabulary) |
| `datasets/` | dataset pins by hash; no data is committed |
| `docs/` | `prd.md` (intent), `architecture.md` (structure), `contracts.md` (the frozen core types), `ontology.md` (the domain pack schema and how to onboard a domain), `data-model.md` (the schema, the graph model, and the storage boundary) |
| `scripts/` | the checks that make the Five Laws build outcomes rather than prose |
| `deployment/` | Docker Compose, Dockerfiles, and the numbered SQL migration series — `sql/migrations/` forward, `sql/down/` reverse, applied by `make migrate` |

## The Five Inviolable Laws

Stated verbatim in `CONTEXT.md` §2 and `CONVENTIONS.md` §1 — two copies that must remain
byte-identical, checked by `scripts/check_law_copies.py`.

**LAW-EVENT** · **LAW-TIME** · **LAW-PROVENANCE** · **LAW-DOMAIN** · **LAW-EVIDENCE**

Ten checks enforce them mechanically; run them with `make laws`. Each ships a
`--self-test` and is observed to reject a planted violation before it is trusted to pass —
a check that has only ever passed is not evidence a law is enforced (DEF-0001, ADR-0019).

The same rule reaches inside the ontology loader, which reports a third diagnostic severity
beside error and warning: `NOT_RUNNABLE`, for a check it could not perform. It was carrying
one — rule coverage, because no rule pack existed — until the rule engine landed on
2026-09-01; that check is now real, and what it reports is that **6 of 20 declared DataCo
event types have no rule explaining them** (`docs/reports/dataco/rule-coverage.md`). A
validator that silently skipped it would have been indistinguishable from one that ran it
and found nothing. The scripts say the same thing
with an exit code: `check_metrics_are_declared.py` and `check_determinism.py` exit **2**
while the code they would scan does not exist, rather than exiting 0 over nothing.
