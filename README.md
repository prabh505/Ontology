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

Phase **P0 (Governance)**. The architecture blueprint, the repository scaffold, and the
law-enforcement tooling exist. **None of the 16 modules is built and there is no business
logic.** See `CONTEXT.md` for the authoritative answer to "where is this project right
now", and `PROGRESS.md` for what was built and what was deliberately not.

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
make lint typecheck test
```

```bash
make up
```

**Allocate the container runtime at least 4 GB of memory.** Neo4j is the constraint: below
that — or with unrelated containers already holding most of the budget — it is OOM-killed
during startup and exits 137, which reads like a configuration error and is not one. Its
`mem_limit` is declared in `deployment/docker-compose.yml` so the kill is attributable to
neo4j rather than to whichever container the kernel picks.

See `deployment/.env.example` if a conventional host port is already taken on your machine;
every published port is overridable without editing the compose file.

## Layout

| Path | Holds |
|---|---|
| `backend/` | the one installable Python distribution, `causalog` (ADR-0012) |
| `frontend/` | Next.js + TypeScript; the six workspaces (prd.md §51), not yet built |
| `ontology/` | domain vocabulary as **data** — replacing this is how a domain is added |
| `rule_engine/` | rule packs as **data** (the evaluator code lives in the backend) |
| `datasets/` | dataset pins by hash; no data is committed |
| `docs/` | `prd.md` (intent), `architecture.md` (structure) |
| `scripts/` | the checks that make the Five Laws build outcomes rather than prose |
| `deployment/` | Docker Compose, Dockerfiles, numbered SQL migrations |

## The Five Inviolable Laws

Stated verbatim in `CONTEXT.md` §2 and `CONVENTIONS.md` §1 — two copies that must remain
byte-identical, checked by `scripts/check_law_copies.py`.

**LAW-EVENT** · **LAW-TIME** · **LAW-PROVENANCE** · **LAW-DOMAIN** · **LAW-EVIDENCE**

Four checks enforce them mechanically; run them with `make laws`.
