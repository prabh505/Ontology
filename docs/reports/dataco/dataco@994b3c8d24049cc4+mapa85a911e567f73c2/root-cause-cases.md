# Root Cause Analysis — the engine's stated view

> **BOUNDED RUN.** Built from the first 150 rows of the clean layer, not from
> all 180,519. Neither module 9 nor module 10 is a streaming module -- the base
> rates measure across process instances and the fusion needs the whole candidate
> graph in hand -- and the full expansion does not fit in memory as models on an 8 GB
> machine (`tests/integration/test_full_expansion_budget.py`). **Every number below
> measures this slice, not the dataset.** Re-run with `--rows 0` to remove the bound.

- standing: `STATED`
- `run_id`: `run:f5e7ab410fa9eeb4`
- links available in this view: 0

## Case 1

- outcome: `evt:015bd166df4b2162`
- declared delay on this instance: **4.000000**
- standing: `STATED`
- candidates considered: 0

**No candidate cause.** Nothing in this view leads to the outcome, so there is no chain to rank and no propagation to measure. That is a statement about the graph and not about the outcome.

## Case 2

- outcome: `evt:0a8cc6602ef4cf45`
- declared delay on this instance: **4.000000**
- standing: `STATED`
- candidates considered: 0

**No candidate cause.** Nothing in this view leads to the outcome, so there is no chain to rank and no propagation to measure. That is a statement about the graph and not about the outcome.

## Case 3

- outcome: `evt:3c35f1c1b640806c`
- declared delay on this instance: **4.000000**
- standing: `STATED`
- candidates considered: 0

**No candidate cause.** Nothing in this view leads to the outcome, so there is no chain to rank and no propagation to measure. That is a statement about the graph and not about the outcome.

## Case 4

- outcome: `evt:3f48319b818320c1`
- declared delay on this instance: **4.000000**
- standing: `STATED`
- candidates considered: 0

**No candidate cause.** Nothing in this view leads to the outcome, so there is no chain to rank and no propagation to measure. That is a statement about the graph and not about the outcome.

## Case 5

- outcome: `evt:67ecbde833a19000`
- declared delay on this instance: **4.000000**
- standing: `STATED`
- candidates considered: 0

**No candidate cause.** Nothing in this view leads to the outcome, so there is no chain to rank and no propagation to measure. That is a statement about the graph and not about the outcome.
