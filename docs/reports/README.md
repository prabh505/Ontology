# `docs/reports/`

**Single responsibility:** hold the published reports for each pinned dataset.

```
<dataset_id>/<dataset_version>/
    data-quality.json       canonical JSON — the machine-readable report
    data-quality.md         the same object, rendered for a human
    report.sha256           the digest of the canonical bytes
    mapping.proposal.yaml   optional; written by `make import … PROPOSE=1`
    reconciliation.json     module 3: what identity resolution created, merged, conflicted
    reconciliation.md       the same object, rendered for a human
    event-quality.json      module 4: what the reconstructed event log does and does not
                            contain — counts by type and provenance class, timestamp
                            precision, orphans, and process coverage
    event-quality.md        the same object, rendered for a human
```

Written by `scripts/import_dataset.py` (module 1, `make import`) and
`scripts/build_event_log.py` (modules 3 and 4, `make events`). **Committed**, while the data
they describe is git-ignored and pinned by hash — which makes these files the only durable
description of what was in a dataset at a given `dataset_version`, and of what could be
reconstructed from it.

**Read the Event Quality Report before believing any count derived from the graph.** It
states how much of the log is observed rather than reconstructed, how much of it can be
placed in time at all, and which process steps no record in this source can ever witness.
Those three numbers bound every causal claim anything downstream is entitled to make.

## Why both formats, from one object

The JSON and the Markdown are rendered from the same `DataQualityReport`, so they cannot
drift into disagreeing about what was found. The JSON is canonical
(`core.serialization.to_canonical_json`), so two imports of one file produce identical bytes
and an identical `report_sha256`; `tests/determinism/` asserts exactly that.

## How to read one

**Start at the top and do not skip it.** `Headline constraints` renders first, in both
formats, and it is a field on the model rather than a convention about where to put
important text. It holds the limitations that bound what any downstream conclusion about
this dataset may claim — things nobody can fix, only know about — each with the measurement
behind it.

Then `Row reconciliation`: every row read is in the clean layer or in quarantine with a
reason, and the arithmetic is printed. Then the findings, most severe first, each naming
what it breaks downstream.

**Finish at `What this report did not check`.** A report that lists only what it looked at
reads as a report that looked at everything, and this repository has twice mistaken a check
that could not run for one that passed (DEF-0001, OQ-014).

## Severity

| | |
|---|---|
| `ERROR` | an ontology violation. The row is quarantined. |
| `WARNING` | a statistical anomaly. The row is carried forward untouched — an outlier is a fact about the world at least as often as it is a defect. |
| `NOT_RUNNABLE` | **a check that could not be performed.** Not a pass. |

## Reproducing one

```bash
make import DATASET=dataco
```

Requires the pinned source at the path `datasets/<dataset_id>.pin.json` names. The report is
a pure function of the bytes, the mapping and the pack, so a matching `report.sha256` is
proof you read the same dataset through the same interpretation.
