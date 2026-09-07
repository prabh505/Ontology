"""Find what recurs across a whole run, for the reader who does not want an incident.

**Deliberately not one of the prd.md §36 modules.** §36 lists sixteen and none of them
answers a question about the run: modules 11 and 12 both answer questions about ONE outcome.
prd.md §10 nonetheless names a user -- Executive Leadership -- who "needs strategic patterns
rather than individual incidents", and this package is that answer. The Causal Graph Builder
set the precedent for landing PRD-required work that §36 names no owner for as a named
package beside the modules (OQ-025, ADR-0054), rather than widening a module's contract
until `docs/architecture.md` §2 is wrong about what that module does.

Everything here runs over the **event-type projection**, never over event instances -- the
altitude `causal_graph_builder.cycles` chose, for the reason stated there: a claim about
instances is unique by construction, so a recurrence counter running at that level could
only ever return one. The cost is stated on every row rather than discovered later: a shape
reported here may be carried by one pathological instance repeating, so every finding shows
the process instances it spans beside its raw count.

Three findings, never ranked against one another and never combined into an "importance"
figure. The weighting between "happens often" and "costs a lot when it happens" would be an
unexplainable constant -- the same objection ADR-0008 raises to a blended root-cause score,
one level up.

Every threshold is a pack declaration in the `pattern_mining` namespace. An absent one means
nothing was looked for, which is reported in a sentence beside the empty list, because an
empty list on its own reads as a finding that there are no patterns.
"""

from causalog.causal_engine.pattern_miner.mine import (
    bottlenecks_of,
    mine_patterns,
    motifs_of,
)
from causalog.causal_engine.pattern_miner.report import (
    PATTERN_REPORT_SCHEMA_VERSION,
    Bottleneck,
    Motif,
    StructuralPatternReport,
    build_report,
    render_markdown,
)

__all__ = [
    "PATTERN_REPORT_SCHEMA_VERSION",
    "Bottleneck",
    "Motif",
    "StructuralPatternReport",
    "bottlenecks_of",
    "build_report",
    "mine_patterns",
    "motifs_of",
    "render_markdown",
]
