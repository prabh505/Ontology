"""The seven candidate generators (prd.md §27), independent and composable.

prd.md §27 names seven sources. Six of them map one-to-one onto a generator here; the
seventh -- "domain ontology" -- is not a generator, because the ontology's contribution is
already structural rather than proposing: it declares which event types and participants
exist at all, and every generator below reads pairs that could not exist if the pack had not
declared them. A separate "ontology generator" would propose every admissible pair in the
vocabulary, which is the whole cross product wearing a justification.

`ALL_GENERATORS` is the canonical sequence, sorted by `generator_id`. That sequence is
load-bearing: the round-robin cap policy in `graph.py` walks it, so a change to it changes
which candidates survive truncation. It is sorted rather than authored for exactly that
reason.
"""

from causalog.causal_engine.candidate_cause_generator.context import CandidateGenerator
from causalog.causal_engine.candidate_cause_generator.generators.historical_frequency import (
    HistoricalFrequencyGenerator,
)
from causalog.causal_engine.candidate_cause_generator.generators.rule_based import (
    RuleBasedGenerator,
)
from causalog.causal_engine.candidate_cause_generator.generators.shared_entity import (
    SharedEntityGenerator,
)
from causalog.causal_engine.candidate_cause_generator.generators.shared_identifier import (
    SharedIdentifierGenerator,
)
from causalog.causal_engine.candidate_cause_generator.generators.statistical_association import (
    ASSOCIATION_DISCLAIMER,
    StatisticalAssociationGenerator,
)
from causalog.causal_engine.candidate_cause_generator.generators.structural_path import (
    StructuralPathGenerator,
)
from causalog.causal_engine.candidate_cause_generator.generators.temporal_proximity import (
    TemporalProximityGenerator,
)

__all__ = [
    "ALL_GENERATORS",
    "ASSOCIATION_DISCLAIMER",
    "HistoricalFrequencyGenerator",
    "RuleBasedGenerator",
    "SharedEntityGenerator",
    "SharedIdentifierGenerator",
    "StatisticalAssociationGenerator",
    "StructuralPathGenerator",
    "TemporalProximityGenerator",
]

#: Every generator built here, before sequencing. Annotated against the protocol so that a
#: class which drifts out of conformance -- a renamed method, a changed signature -- fails
#: `mypy --strict` at this line rather than at some call site much later.
_REGISTERED: tuple[CandidateGenerator, ...] = (
    HistoricalFrequencyGenerator(),
    RuleBasedGenerator(),
    SharedEntityGenerator(),
    SharedIdentifierGenerator(),
    StatisticalAssociationGenerator(),
    StructuralPathGenerator(),
    TemporalProximityGenerator(),
)

#: Every generator, in canonical `generator_id` sequence.
ALL_GENERATORS: tuple[CandidateGenerator, ...] = tuple(
    sorted(_REGISTERED, key=lambda generator: generator.generator_id)
)
