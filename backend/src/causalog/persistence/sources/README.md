# `causalog.persistence.sources`

**Layer rank:** none — a driven adapter, like the rest of `persistence`.

## Single responsibility

Hold the `SourceReader` implementations — extension seam 1 of the six in
`docs/architecture.md` §5. One module per dataset, named for the dataset, each reading
bytes and emitting `RawRecordBatch` values in a stable sequence.

This directory is the **single pinned location** for that seam. It is the one code file a
new domain writes: the other five seams are data (`ontology/packs/<domain>/*.yaml` and
`rule_engine/<domain>/`). Before this was pinned, `docs/architecture.md` §5.1 said
"under `persistence/` or a small adapter package", so the answer to "which single file
changes if the domain changes?" was "it depends" — which is not an answer.

## Why here, and not in `ingestion/`

Three existing rules make this the only location that works, each verified by planting a
probe adapter and running the checks rather than by reading the rule:

- **LAW-DOMAIN does not scan `persistence/`.** A reader must name the real columns of a
  real dataset — `ward_code`, `discharge_ready_at` — and that is domain vocabulary. In a
  scanned package it would be a violation; here it is correct.
  (`scripts/check_domain_independence.py`, `IN_SCOPE_PACKAGES`.)
- **F4 keeps it out of reasoning.** Only `orchestration` may import
  `causalog.persistence.*`, so a reader is *supplied* to module 1, never imported by it.
  A reasoning package that reaches for one fails the build.
- **F7 permits the tabular import.** `persistence` carries no layer rank, so the ban on
  `csv`/`pandas` above rank 3 does not apply. A reader may parse a file; nothing above
  L2 may hold the row it parsed.

## Contents

Empty by intent. This is a reserved location, in the same sense as `ontology/_schema/`:
the first reader lands with module 1 (Data Adapter). Adding one does not change any
reasoning code — see §5.3, whose per-module diff is zero lines.

**Forbidden:** no reasoning, no mapping, no defaults. A reader reports what the source
said. Interpreting a column is module 2's job, and it does that from `mapping.yaml`.
