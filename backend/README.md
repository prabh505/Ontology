# `backend/`

**Single responsibility:** hold the one installable Python distribution, `causalog`, that
contains every reasoning package (ADR-0012).

PRD §43 prints `graph_engine/`, `causal_engine/`, `counterfactual_engine/`, and
`recommendation_engine/` as repository-root directories. They live here instead, under a
single import root, so that packaging, `mypy --strict`, ruff, and the layer lint each have
exactly one configuration. The deviation and its cost are recorded in ADR-0012.

- `src/causalog/` — the package. Layer ranks and forbidden dependencies are stated in each
  sub-package's `README.md` and enforced by `scripts/check_layers.py`.
- `tests/` — the taxonomy from `CONVENTIONS.md` §14; `tests/unit/` mirrors `src/causalog/`.
- `pyproject.toml` — exact pins only. Every dependency is justified in ADR-0015.
