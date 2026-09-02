# `docs/`

**Single responsibility:** hold the documents that state *intent*, as distinct from the
governance files at the repository root that state *current state*.

```
prd.md              product intent (moved here from the root — ADR-0017, closes OQ-010)
architecture.md     layer map and forbidden edges, module inventory, the storage
                    boundary, the Run model, extension seams, sequence diagrams
contracts.md        the frozen public interface of causalog.core, v1.3.0 — every public
                    type with its fields, invariants, failure modes, and prohibitions;
                    the timestamp comparison semantics; the hashing scheme; the
                    provenance algebra (ADR-0025, closes OQ-009; 1.1.0 adds the `ont`
                    identifier prefix, ADR-0028; 1.2.0 adds `map` and SourceDescription,
                    ADR-0035 / ADR-0038; 1.3.0 changes no type and restates how modules 3
                    and 4 USE Event, ADR-0039 / ADR-0041)
ontology.md         the domain pack schema, what the loader checks and what it cannot,
                    and the numbered checklist for onboarding a new domain (ADR-0026)
data-model.md       the bi-temporal PostgreSQL schema and the Neo4j projection: ER and
                    graph diagrams, every index with its justifying query, and the
                    indexes deliberately absent (ADR-0032 / ADR-0033 / ADR-0034)
reports/            NOT intent, and the one directory here that is neither intent nor a
                    commitment: the published reports per pinned dataset — the Data
                    Quality Report from module 1 (`make import`), and the Reconciliation
                    Report and Event Quality Report from modules 3 and 4
                    (`make events`). Committed because the data they describe is not.
                    See its own README for how to read one.
```

`contracts.md` and `ontology.md` are the exceptions to this directory's "intent, not state"
rule, and deliberately so: they state what the core types and the domain pack schema *are*,
which is neither intent nor current state but a commitment. It lives here because it is read alongside `architecture.md` when
touching a module boundary, and it is versioned independently of both.

There is deliberately **no `adr/` directory**. `DECISIONS.md` at the repository root is the
canonical, append-only ADR log; a second copy on disk would be a divergence waiting to
happen, and `HANDOFF.md` §4 treats a divergence as a defect rather than a documentation
chore.

`DECISIONS.md`, `CONTEXT.md`, `CONVENTIONS.md`, `GLOSSARY.md`, `PROGRESS.md`, and
`HANDOFF.md` stay at the repository root: they are read at the start of every session and
must be impossible to miss.
