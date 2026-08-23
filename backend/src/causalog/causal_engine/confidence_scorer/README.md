# `causalog.causal_engine.confidence_scorer`

**Layer rank:** `L6`

## Single responsibility

Decompose edge support into named confidence components (module 10).

## Forbidden dependencies

Everything above L6. Owns the LAW-EVIDENCE gate; may never emit a bare float.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
