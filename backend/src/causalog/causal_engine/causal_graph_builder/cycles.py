"""Feedback loop detection (prd.md §31), and the refusal to call an artifact a discovery.

THE LOAD-BEARING DESIGN DECISION, stated before the algorithm
-------------------------------------------------------------
**Cycle detection runs over the event-TYPE projection of the graph, not over the event
instances.** That is not a performance choice. At the instance level a genuine loop is
*arithmetically impossible*: a `CERTAIN` verdict means `cause.t_latest < effect.t_earliest`,
which is a strict precedence relation, and strict precedence admits no cycle. Any circuit
found among event instances therefore contains at least one link that is `UNDETERMINED` or
unverifiable -- it
exists *because* precedence was unresolvable. A detector that ran at that level could only
ever find artifacts, and every "feedback loop" it reported would be a restatement of the
source's timestamp granularity.

prd.md §31's own example says the same thing once read carefully. Its chain ends on the same
event TYPE it began with -- but not on the same event. The last link is a *later instance* of
the first type, produced by a later run of the process. The loop closes at the level of
types, across process instances, and that is what makes it a real mechanism rather than a
sequencing artifact. (The example itself is domain vocabulary and stays in prd.md;
LAW-DOMAIN keeps it out of here.)

So: circuits are enumerated over types, and each projected link is then asked what actually
supports it among the instances. Four outcomes, because collapsing them would overclaim:

* `GENUINE` -- every projected link has support that is `CERTAIN`, verifiable, and
  **promoted**, and the supporting instances span more than one process instance.
* `TEMPORAL_ARTIFACT` -- some projected link has no temporally sound support at all. **A
  data artifact, reported in its own section, never presented as a discovered loop.**
* `WITHIN_INSTANCE` -- temporally sound, but every supporting edge sits inside one process
  instance. Not a feedback loop between runs of a process; more likely a modelling error
  worth surfacing separately.
* `UNPROMOTED` -- sound and cross-instance, but at least one link is a claim the engine does
  not stand behind. A loop of hypotheses is not a loop the system asserts.

**Classification is engine code and no pack may override it** (ADR-0055). Whether a circuit
resting on unresolvable precedence is a discovery is not a domain judgement; if a pack could
decide it, "the engine detected a reinforcing loop" would mean two different things in two
packs and would stop being a finding.

Loop gain, and its honest ceiling
---------------------------------
`loop_gain` is the product of the member weights around the circuit, multiplied by the
declared multiplier of any modifier member. **Propagation weights are normalized shares in
`[0, 1]`, so a product of them can never exceed 1.0.** A gain above one -- the textbook
signature of a reinforcing loop -- is therefore unreachable from contributing edges alone,
and only an `AMPLIFYING` member's multiplier can lift it there. This is stated rather than
hidden: the number ranks loops against each other and does not, on its own, test for
reinforcement.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalog.causal_engine.causal_graph_builder.context import GraphBuildContext
from causalog.causal_engine.causal_graph_builder.graph import PromotedGraph
from causalog.causal_engine.confidence_scorer import CausalGraph
from causalog.core.errors import ContractViolationError
from causalog.core.temporal import TemporalVerdict
from causalog.core.types import Event
from causalog.core.types.causal_edge import AmplifyingCause, InhibitingCause

__all__ = [
    "GAIN_CEILING_NOTICE",
    "CircuitTruncation",
    "DetectionStatus",
    "FeedbackLoop",
    "LoopClassification",
    "LoopDetectionResult",
    "LoopMember",
    "detect_loops",
]

#: Fixed text, printed above every reported gain. A property on the loop, never a field.
GAIN_CEILING_NOTICE = (
    "LOOP GAIN CANNOT EXCEED 1.0 FROM CONTRIBUTING EDGES ALONE. Propagation weights are "
    "normalized shares in [0, 1], so their product is bounded by one however strong the "
    "loop is. Only an AMPLIFYING member's declared multiplier can lift a gain above one. "
    "Read this number as a ranking between loops, not as a test for whether a loop "
    "reinforces itself."
)


class LoopClassification(str, Enum):
    """What a detected circuit actually is. Never collapsed into a single 'loop' count."""

    GENUINE = "GENUINE"
    """Every link is temporally sound, promoted, and the support spans process instances."""

    TEMPORAL_ARTIFACT = "TEMPORAL_ARTIFACT"
    """A link rests on unresolvable or absent precedence. A property of the SOURCE's timestamp
    granularity, not a discovery about the domain, and reported as such."""

    WITHIN_INSTANCE = "WITHIN_INSTANCE"
    """Temporally sound, but confined to one process instance. A loop that closes inside a
    single run of a process is not the cross-instance reinforcement prd.md §31 describes."""

    UNPROMOTED = "UNPROMOTED"
    """Sound and cross-instance, but a link is a claim the engine does not assert. A loop of
    hypotheses, reported so that it is visible if the evidence later improves."""


class DetectionStatus(str, Enum):
    """Whether detection ran at all. `NOT_RUNNABLE` is never reported as 'no loops'."""

    RAN = "RAN"
    NOT_RUNNABLE = "NOT_RUNNABLE"


class LoopMember(BaseModel):
    """One projected link of a circuit, and the instance-level support behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_event_type: str = Field(min_length=1)
    target_event_type: str = Field(min_length=1)
    edge_kind: str = Field(min_length=1)
    #: The instance-level claims supporting this link, as `(source, target)`, sorted.
    supporting_pairs: tuple[tuple[str, str], ...] = Field(min_length=1)
    #: How many supporting claims are CERTAIN and verifiable.
    temporally_sound_count: int = Field(ge=0)
    #: How many supporting claims the engine actually promoted.
    promoted_count: int = Field(ge=0)
    #: The representative weight used in the gain: the strongest sound support's weight.
    weight: float = Field(ge=0.0, le=1.0)
    #: An AMPLIFYING or INHIBITING member's declared multiplier, else None.
    magnitude_multiplier: float | None = None


class FeedbackLoop(BaseModel):
    """One detected circuit over event types, classified and characterized.

    `participants` is the circuit in traversal sequence, starting from its
    lexicographically smallest type, so one circuit has one canonical rendering however it
    was discovered.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    classification: LoopClassification
    participants: tuple[str, ...] = Field(min_length=2)
    members: tuple[LoopMember, ...] = Field(min_length=2)
    #: Process instances whose events support any member, sorted.
    process_instance_ids: tuple[str, ...] = ()
    #: Product of member weights and any modifier multipliers. See `GAIN_CEILING_NOTICE`.
    loop_gain: float | None = None
    #: Index into `members` of the cheapest link to break, by propagation weight. `None`
    #: when the loop is not genuine, because naming an intervention point on an artifact
    #: would invite acting on it.
    weakest_link_index: int | None = None
    #: Why this is not a genuine loop. Required whenever the classification is not GENUINE.
    classification_reason: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> FeedbackLoop:
        """A non-genuine loop states why, and names no intervention point."""
        if self.classification is LoopClassification.GENUINE:
            if self.classification_reason is not None:
                raise ContractViolationError(
                    "FeedbackLoop is GENUINE and carries a classification_reason; the "
                    "field exists to say why a circuit is NOT a loop."
                )
        else:
            if not self.classification_reason:
                raise ContractViolationError(
                    f"FeedbackLoop is {self.classification.value} and states no reason. A "
                    "circuit reported as an artifact without saying which link made it one "
                    "is unactionable, and a reader will assume the worst or the best."
                )
            if self.weakest_link_index is not None:
                raise ContractViolationError(
                    f"FeedbackLoop is {self.classification.value} and names a weakest link. "
                    "Naming the cheapest place to break a circuit the engine does not "
                    "assert invites acting on a data artifact."
                )
        if self.weakest_link_index is not None and not (
            0 <= self.weakest_link_index < len(self.members)
        ):
            raise ContractViolationError("FeedbackLoop.weakest_link_index is out of range.")
        if len(self.participants) != len(self.members):
            raise ContractViolationError(
                f"FeedbackLoop has {len(self.participants)} participant(s) and "
                f"{len(self.members)} member(s); a circuit has one link per "
                "participant."
            )
        return self

    @property
    def gain_notice(self) -> str:
        """Return the fixed ceiling notice. A property so a revision cannot soften it."""
        return GAIN_CEILING_NOTICE

    def sort_key(self) -> tuple[str, ...]:
        """Return the canonical sequence key: the circuit itself."""
        return self.participants


class CircuitTruncation(BaseModel):
    """A strongly connected component whose circuits exceeded the declared cap.

    Module 9's `TruncationRecord` idiom: a bound that was hit is reported with what it was
    and what it stopped at, never silently applied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_event_types: tuple[str, ...] = Field(min_length=2)
    cap: int = Field(ge=1)
    enumerated: int = Field(ge=0)


class LoopDetectionResult(BaseModel):
    """Everything detection found, or the stated reason it could not run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DetectionStatus
    loops: tuple[FeedbackLoop, ...] = ()
    truncations: tuple[CircuitTruncation, ...] = ()
    #: What the pack would have to declare. Present only when status is NOT_RUNNABLE.
    requirement: str | None = None
    #: How many event types and projected links the search actually covered.
    types_examined: int = 0
    projected_links: int = 0

    @model_validator(mode="after")
    def _check_status(self) -> LoopDetectionResult:
        """A run that could not happen reports nothing and says what it needed."""
        if self.status is DetectionStatus.NOT_RUNNABLE:
            if not self.requirement:
                raise ContractViolationError(
                    "LoopDetectionResult is NOT_RUNNABLE and names no requirement; a check "
                    "that could not run must say what it needed, or it reads exactly like "
                    "a check that ran and found nothing (DEF-0001)."
                )
            if self.loops:
                raise ContractViolationError(
                    "LoopDetectionResult is NOT_RUNNABLE and carries loops."
                )
        elif self.requirement is not None:
            raise ContractViolationError(
                "LoopDetectionResult RAN and names a requirement; the field says why "
                "nothing ran."
            )
        return self

    def by_classification(self) -> tuple[tuple[str, int], ...]:
        """Return the loop tally per classification, including classifications with none.

        Every member is present even at zero, deliberately: 'no genuine loops' is a finding
        and it must be visible as one rather than as an absent row a reader has to notice.
        """
        tally = {member.value: 0 for member in LoopClassification}
        for loop in self.loops:
            tally[loop.classification.value] += 1
        return tuple(sorted(tally.items()))


# ---------------------------------------------------------------------------------------
# Projection and enumeration.
# ---------------------------------------------------------------------------------------


class _ProjectedLink:
    """The instance-level support behind one type-level link. Internal to this module."""

    __slots__ = ("edge_kind", "multiplier", "pairs", "promoted", "sound", "sound_weight")

    def __init__(self, edge_kind: str) -> None:
        self.edge_kind = edge_kind
        self.pairs: set[tuple[str, str]] = set()
        self.sound: int = 0
        self.promoted: int = 0
        self.sound_weight: float = 0.0
        self.multiplier: float | None = None


def _project(
    graph: CausalGraph,
    promoted: PromotedGraph,
    events_by_id: dict[str, Event],
) -> dict[tuple[str, str], _ProjectedLink]:
    """Collapse the instance graph onto event types, keeping what supports each link.

    One `_ProjectedLink` per directed type pair. When several edge kinds connect one type
    pair the first by sorted kind names the link, and every kind's support is folded in --
    a circuit is about whether influence flows, and splitting one type pair across parallel
    links would report the same circuit several times.
    """
    promoted_keys = {edge.sort_key() for edge in promoted.edges}
    weight_by_key = {edge.sort_key(): edge.weight.weight for edge in promoted.edges}
    links: dict[tuple[str, str], _ProjectedLink] = {}
    for scored in graph.edges:
        source = events_by_id.get(scored.edge.source_event_id)
        target = events_by_id.get(scored.edge.target_event_id)
        if source is None or target is None or source.event_type == target.event_type:
            # A self-loop at the type level is an event type influencing its own later
            # instances. Real, and NOT a multi-participant feedback loop; it is excluded
            # here and would need its own treatment rather than being folded into §31's.
            continue
        key = (source.event_type, target.event_type)
        kind = scored.edge.payload.edge_kind.value
        link = links.get(key)
        if link is None or kind < link.edge_kind:
            replacement = _ProjectedLink(kind)
            if link is not None:
                replacement.pairs = link.pairs
                replacement.sound = link.sound
                replacement.promoted = link.promoted
                replacement.sound_weight = link.sound_weight
                replacement.multiplier = link.multiplier
            links[key] = replacement
            link = replacement
        link.pairs.add((scored.edge.source_event_id, scored.edge.target_event_id))
        edge_key = scored.sort_key()
        is_sound = (
            scored.edge.temporal_verdict is TemporalVerdict.CERTAIN
            and not scored.edge.temporally_unverifiable
        )
        if is_sound:
            link.sound += 1
            link.sound_weight = max(
                link.sound_weight,
                weight_by_key.get(edge_key, scored.edge.confidence.scalar),
            )
        if edge_key in promoted_keys:
            link.promoted += 1
        payload = scored.edge.payload
        if isinstance(payload, AmplifyingCause | InhibitingCause):
            link.multiplier = payload.magnitude_multiplier
    return links


def _elementary_circuits(
    adjacency: dict[str, tuple[str, ...]], cap: int
) -> tuple[tuple[tuple[str, ...], ...], int]:
    """Enumerate elementary circuits, each exactly once, capped.

    Each circuit is emitted rooted at its lexicographically smallest participant, and the
    search from a given root visits only nodes at or above it. That is the standard
    canonicalization: it enumerates every elementary circuit exactly once and gives one
    rendering per circuit regardless of where the search started, which is what makes two
    runs over one graph produce byte-identical output (`CONVENTIONS.md` §11).

    Returns the circuits and the number of times the cap stopped the search.
    """
    found: list[tuple[str, ...]] = []
    stopped = 0
    for root in sorted(adjacency):
        stack: list[tuple[str, tuple[str, ...]]] = [(root, (root,))]
        while stack:
            if len(found) >= cap:
                stopped += 1
                break
            node, path = stack.pop()
            for neighbour in sorted(adjacency.get(node, ()), reverse=True):
                if neighbour == root and len(path) > 1:
                    found.append(path)
                    continue
                if neighbour < root or neighbour in path:
                    continue
                stack.append((neighbour, (*path, neighbour)))
        if len(found) >= cap:
            break
    return tuple(sorted(set(found))), stopped


def detect_loops(
    graph: CausalGraph, promoted: PromotedGraph, context: GraphBuildContext
) -> LoopDetectionResult:
    """Detect and classify feedback loops over the event-type projection.

    Runs over the SCORED graph rather than the promoted one, and that is deliberate. A
    `TEMPORAL_ARTIFACT` is by definition made of links that could never be promoted, so a
    detector restricted to promoted edges would make the artifact category structurally
    unreachable -- and the module would silently stop warning about the one thing prd.md §31
    is most likely to be wrong about on a day-granular source.
    """
    parameters = context.parameters
    if parameters.circuit_enumeration_cap is None or parameters.loop_minimum_participants is None:
        return LoopDetectionResult(
            status=DetectionStatus.NOT_RUNNABLE,
            requirement=(
                "graph_construction.circuit_enumeration_cap and "
                "graph_construction.loop_minimum_participants. Without the cap a "
                "combinatorial component would run until somebody killed the process; "
                "without the minimum, mutual pairs are neither included nor excluded by any "
                "declaration. Absent means NOT RUNNABLE, never a default (ADR-0049)."
            ),
        )

    events_by_id = context.events_by_id()
    links = _project(graph, promoted, events_by_id)
    adjacency: dict[str, tuple[str, ...]] = {}
    for source_type, target_type in sorted(links):
        adjacency.setdefault(source_type, ())
        adjacency[source_type] = (*adjacency[source_type], target_type)

    circuits, stopped = _elementary_circuits(adjacency, parameters.circuit_enumeration_cap)
    instances = context.instances_by_event_id()

    loops: list[FeedbackLoop] = []
    for circuit in circuits:
        if len(circuit) < parameters.loop_minimum_participants:
            continue
        loops.append(_characterize(circuit, links, instances))

    truncations: tuple[CircuitTruncation, ...] = ()
    if stopped:
        truncations = (
            CircuitTruncation(
                component_event_types=tuple(sorted(adjacency)),
                cap=parameters.circuit_enumeration_cap,
                enumerated=len(circuits),
            ),
        )
    return LoopDetectionResult(
        status=DetectionStatus.RAN,
        loops=tuple(sorted(loops, key=lambda item: item.sort_key())),
        truncations=truncations,
        types_examined=len(adjacency),
        projected_links=len(links),
    )


def _characterize(
    circuit: tuple[str, ...],
    links: dict[tuple[str, str], _ProjectedLink],
    instances: dict[str, tuple[str, ...]],
) -> FeedbackLoop:
    """Build one classified, characterized loop from a circuit of event types."""
    members: list[LoopMember] = []
    witnessed: set[str] = set()
    for index, source_type in enumerate(circuit):
        target_type = circuit[(index + 1) % len(circuit)]
        link = links[(source_type, target_type)]
        pairs = tuple(sorted(link.pairs))
        for source_event_id, target_event_id in pairs:
            witnessed.update(instances.get(source_event_id, ()))
            witnessed.update(instances.get(target_event_id, ()))
        members.append(
            LoopMember(
                source_event_type=source_type,
                target_event_type=target_type,
                edge_kind=link.edge_kind,
                supporting_pairs=pairs,
                temporally_sound_count=link.sound,
                promoted_count=link.promoted,
                weight=min(1.0, max(0.0, link.sound_weight)),
                magnitude_multiplier=link.multiplier,
            )
        )

    unsound = [member for member in members if member.temporally_sound_count == 0]
    unpromoted = [member for member in members if member.promoted_count == 0]
    instance_ids = tuple(sorted(witnessed))

    if unsound:
        return FeedbackLoop(
            classification=LoopClassification.TEMPORAL_ARTIFACT,
            participants=circuit,
            members=tuple(members),
            process_instance_ids=instance_ids,
            classification_reason=(
                "THIS IS A DATA ARTIFACT, NOT A DISCOVERED FEEDBACK LOOP. "
                f"{len(unsound)} of {len(members)} link(s) in this circuit -- "
                + ", ".join(
                    f"{member.source_event_type} -> {member.target_event_type}"
                    for member in unsound
                )
                + " -- have no temporally sound support: every claim behind them is "
                "UNDETERMINED or rests on an event the source never placed in time. The "
                "circuit closes because precedence could not be resolved, which is a "
                "statement about the source's timestamp granularity (CONTEXT.md R-14) and "
                "not about the domain."
            ),
        )
    if len(instance_ids) < 2:
        return FeedbackLoop(
            classification=LoopClassification.WITHIN_INSTANCE,
            participants=circuit,
            members=tuple(members),
            process_instance_ids=instance_ids,
            classification_reason=(
                "Every link is temporally sound, but the whole circuit is supported by "
                f"{len(instance_ids)} process instance(s). prd.md §31's reinforcement runs "
                "ACROSS instances -- the delays at the end of the chain are later runs of "
                "the process, not the run that started it. A circuit closing inside one "
                "instance is more likely a modelling error than a feedback loop, and is "
                "reported separately so it can be investigated as one."
            ),
        )
    if unpromoted:
        return FeedbackLoop(
            classification=LoopClassification.UNPROMOTED,
            participants=circuit,
            members=tuple(members),
            process_instance_ids=instance_ids,
            classification_reason=(
                f"{len(unpromoted)} of {len(members)} link(s) in this circuit -- "
                + ", ".join(
                    f"{member.source_event_type} -> {member.target_event_type}"
                    for member in unpromoted
                )
                + " -- are claims the engine does not stand behind: no supporting edge "
                "cleared its kind's promotion threshold. The circuit is temporally sound "
                "and spans instances, so it is worth watching, but a loop of hypotheses is "
                "not a loop the system asserts."
            ),
        )

    gain = 1.0
    for member in members:
        gain = gain * member.weight
        if member.magnitude_multiplier is not None:
            gain = gain * member.magnitude_multiplier
    weakest = min(range(len(members)), key=lambda index: (members[index].weight, index))
    return FeedbackLoop(
        classification=LoopClassification.GENUINE,
        participants=circuit,
        members=tuple(members),
        process_instance_ids=instance_ids,
        loop_gain=gain,
        weakest_link_index=weakest,
    )
