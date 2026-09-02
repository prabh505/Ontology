# `causalog.core`

**Layer rank:** `L0`

## Single responsibility

Declare the canonical types every layer computes over.

**Status: frozen at contract version 1.0.0 (ADR-0025).** The full specification -- every
public type with its fields, invariants, failure modes, and prohibitions -- is
`docs/contracts.md`. Changing anything here requires an ADR and a coordinated update of
every consumer; it is a decision, not an edit.

## Forbidden dependencies

Every project-local package. `core/` imports the standard library and the data-validation base only (CONVENTIONS.md §6, §12).

Enforced by `scripts/check_layers.py` (layer ranks and forbidden edges) and, where the
package is in LAW-DOMAIN scope, by `scripts/check_domain_independence.py`.

See `docs/contracts.md` for the frozen public interface, and `docs/architecture.md` §1 for
the full layer map.

Three sections of `docs/contracts.md` govern behaviour rather than shape and are worth
reading before changing the code they describe: the timestamp comparison semantics (§3),
which govern LAW-TIME; the hashing scheme and its collision bound (§2); and the provenance
algebra (§4).
