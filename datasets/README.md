# `datasets/`

**Single responsibility:** pin the exact source data a Run consumes, by hash, without
committing the data itself.

```
dataco.pin.json     source URL, file hash, record count, dataset_version
raw/                local working copy — git-ignored, never committed
```

Both are authored with module 1 (Data Adapter); this directory is their reserved location.

`dataset_version` participates in the `run_id` (ADR-0013). Two datasets that differ by one
byte are two different Runs, and their conclusions are not comparable.

**Forbidden:** loading a dataset into PostgreSQL by any path other than the Data Adapter
(module 1). A fact that arrives without an evidence record cannot satisfy LAW-EVIDENCE, and
nothing downstream can cite it.
