# `causalog.ingestion.schema_mapper`

**Layer rank:** `L2`

## Single responsibility

Bind dataset columns and values to ontology concepts (module 2).

## Forbidden dependencies

`extraction` and above; may never default an unmapped value.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
