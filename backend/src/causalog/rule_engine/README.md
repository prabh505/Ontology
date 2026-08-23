# `causalog.rule_engine`

**Layer rank:** `L5`

## Single responsibility

Load, conflict-check, and evaluate rule packs against graph facts.

## Forbidden dependencies

`causal_engine` and above. Rule *data* lives in `/rule_engine`; this package holds code only and is NOT exempt from the LAW-DOMAIN lint.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
