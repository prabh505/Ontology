# `datasets/`

**Single responsibility:** pin the exact source data a Run consumes, by hash, without
committing the data itself.

```
dataco.pin.json     COMMITTED. Source URL, byte count, file hash, row count, header, the
                    codec chosen and the codecs rejected, the mapping and ontology
                    identities, and the dataset_version they compose to.
raw/                local working copy — git-ignored, never committed
clean/              git-ignored. One directory per dataset_version, holding
                      records.jsonl          the cleaned layer
                      quarantine.jsonl       rejected rows, each with its rule codes
                      cleaning_ledger.jsonl  one receipt per (transform, column)
```

Written by module 1 (Data Adapter), via `make import DATASET=<id>`.

**The pin carries no timestamp.** A `pinned_at` field would make two runs over identical
inputs produce different files, which is the determinism guarantee failing in the one
artifact whose whole job is to make a run reproducible. When it was written is in git;
what it describes is not recoverable from anywhere else.

**The raw file is opened read-only and is byte-identical after an import.** Cleaning produces
a new layer keyed by `dataset_version`; it never edits its own evidence, because the record a
conclusion cites must still say what it said when the conclusion was drawn (LAW-EVIDENCE).

`dataset_version` participates in the `run_id` (ADR-0013) and is
`<dataset_id>@<content_sha256[:16]>+map<mapping_digest[:16]>` (ADR-0035). Two datasets that
differ by one byte are two different Runs, and so are two runs over one file read through
different mappings — their conclusions are not comparable either way. The composite is
legible rather than digested so both halves stay recoverable; the pin holds them in full.

The current pin is `dataco@994b3c8d24049cc4+map7acd9e24866745fb` — 95,729,629 bytes,
180,519 data rows, `cp1252`. Its Data Quality Report is at
`docs/reports/dataco/<dataset_version>/`.

**Forbidden:** loading a dataset into PostgreSQL by any path other than the Data Adapter
(module 1). A fact that arrives without an evidence record cannot satisfy LAW-EVIDENCE, and
nothing downstream can cite it.
