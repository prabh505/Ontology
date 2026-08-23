# `frontend/`

**Single responsibility:** render the six workspaces (prd.md §51) against the Visualization
API, and nothing else.

**Layer rank:** above `api` (L10). It is the only place local time exists — timestamps are
UTC everywhere inside the engine and are converted for display here, and here only
(`CONVENTIONS.md` §10).

## Forbidden dependencies

- No direct database access. The frontend talks to the Visualization API over HTTP.
- No reasoning. A computation that changes a conclusion belongs in a reasoning package,
  where it can be tested for determinism and carry provenance.
- No conflating provenance classes. `OBSERVED`, `ASSUMED`, `STATISTICAL`, `INFERRED`, and
  `SIMULATED` must be **visually distinct** (LAW-PROVENANCE); collapsing them into one
  style is a defect, not a design simplification.
- Counterfactual output is labelled a _plausibility simulation_, never a prediction
  (`CONTEXT.md` OQ-007).

## Deliberately not installed

React Flow, Cytoscape.js, D3, and Apache ECharts are named in prd.md §41 but are **not**
dependencies yet: no module consumes them, and `CONVENTIONS.md` §12 forbids a dependency
without an approved module using it. They arrive with module 16 (ADR-0018).
