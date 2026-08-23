# `causalog.explanation_engine`

**Layer rank:** `L8`

## Single responsibility

Render graph evidence into traceable natural-language explanations (module 15).

## Forbidden dependencies

`orchestration`, `api`. No sentence without a graph-evidence reference; no LLM in this path in V1.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
