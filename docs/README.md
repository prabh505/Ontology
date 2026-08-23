# `docs/`

**Single responsibility:** hold the documents that state *intent*, as distinct from the
governance files at the repository root that state *current state*.

```
prd.md              product intent (moved here from the root — ADR-0017, closes OQ-010)
architecture.md     layer map and forbidden edges, module inventory, the storage
                    boundary, the Run model, extension seams, sequence diagrams
```

There is deliberately **no `adr/` directory**. `DECISIONS.md` at the repository root is the
canonical, append-only ADR log; a second copy on disk would be a divergence waiting to
happen, and `HANDOFF.md` §4 treats a divergence as a defect rather than a documentation
chore.

`DECISIONS.md`, `CONTEXT.md`, `CONVENTIONS.md`, `GLOSSARY.md`, `PROGRESS.md`, and
`HANDOFF.md` stay at the repository root: they are read at the start of every session and
must be impossible to miss.
