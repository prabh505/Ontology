# `causalog.api`

**Layer rank:** `L10`

## Single responsibility

Expose reasoning results as structured JSON over HTTP (module 16).

## Forbidden dependencies

`persistence` and `graph_engine` directly; the API talks to `orchestration` only.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
