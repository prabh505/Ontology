# `causalog.causal_engine.candidate_cause_generator`

**Layer rank:** `L6`

## Single responsibility

Propose temporally admissible candidate edges (module 9).

## Forbidden dependencies

Everything above L6. Owns the LAW-TIME gate; may never assign confidence.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
