# `causalog.ontology_runtime`

**Layer rank:** `L1`

## Single responsibility

Load and validate an ontology instance into an in-memory specification.

## Forbidden dependencies

`ingestion` and everything above it; ontology *data* lives in `/ontology`, never here.

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/architecture.md` §1 for the full layer map and §2 for this package's module
contract.
