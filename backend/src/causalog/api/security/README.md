# `causalog.api.security`

**Layer rank:** `L10`

## Single responsibility

Decide who is asking and what they may ask for: authentication, the prd.md §54 permission
matrix, and the request context that threads a correlation id through both.

## Forbidden dependencies

`persistence`, and every reasoning package. Authorization reads `causalog.core.ports.identity`
and nothing below it — a module that knew what a run *contained* could make an access
decision depend on the answer, which is how an authorization check becomes a data leak.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and by
`scripts/check_domain_independence.py`, which scans this package as of ADR-0081.

See `docs/api.md` §5 for the published matrix and `docs/architecture.md` §1 for the layer map.
