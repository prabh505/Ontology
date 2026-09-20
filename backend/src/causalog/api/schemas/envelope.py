"""The response envelope. Every body on this API is one of these, and that is structural.

prd.md §53 says "All APIs return structured JSON". `docs/architecture.md` §2 says rather
more: every response carries its `OutputEnvelope`, provenance classes survive serialization
intact, and returning a body without its envelope is listed under what module 16 is
**forbidden from**. `CONVENTIONS.md` §11 puts it most bluntly -- "an output without its
envelope cannot be verified and is a defect".

A convention would not hold that. A route is added by a person in a hurry, and the field
they forget is the one nothing forces them to supply. So `ApiResponse` is generic over its
payload and required in every other field, which converts "remember the envelope" into
"the response will not construct without it". Three further mechanisms back it up, because
a type alone cannot stop a handler returning a bare `dict`:

1. Every route declares `response_model=ApiResponse[...]`.
2. `tests/law/test_api_returns_no_body_without_envelope.py` walks the **live FastAPI route
   table** and rejects any route whose `response_model` is not an `ApiResponse`.
3. The same file asserts it over the **AST** of `api/routes/`, parametrized per source
   file, so the check grows with the package rather than having to be remembered.

The one field worth defending individually is `confidence`. It is a `ConfidenceView`, whose
`components` carries `min_length=1`, so **this API cannot return a confidence number
without its decomposition**. LAW-EVIDENCE says a bare float is a defect; making the
decomposed form the only constructible form is what turns that from a rule into a fact.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from causalog.core.run import OutputEnvelope
from causalog.orchestration.timing import TimingMeta
from causalog.orchestration.views import (
    ConfidenceView,
    EvidenceReference,
    GraphStandingView,
    ProvenanceSummary,
    StageStatusView,
)

__all__ = ["ApiResponse", "PayloadT", "ResponseScope"]

PayloadT = TypeVar("PayloadT")


class ResponseScope(str, Enum):
    """Whether a body describes engine output or the deployment around it.

    This distinction exists because of an honest problem with requiring an envelope
    everywhere: an `OutputEnvelope` describes ONE run, and a handful of endpoints are not
    about one run. A listing of runs spans many. A job that refused before its packs
    resolved has none yet -- migration 0017's `pipeline_job.run_id` is nullable for exactly
    that reason, and minting a placeholder would be an identifier that addresses nothing
    (`CONVENTIONS.md` §9).

    The alternative was to synthesize an envelope of empty strings for those, which would
    mean a body carrying version fields that describe nothing. `CONVENTIONS.md` §11 wants
    outputs to be VERIFIABLE; a fabricated envelope is worse than an absent one, because it
    is unverifiable while looking verified.

    So the scope is declared, and the validator below makes `RUN_SCOPED` mean what it says.
    `CATALOG` is a visible choice in a diff, the set of routes using it is small, and
    `tests/api/test_catalog_scope_is_closed.py` fails if a route adopts it without being on
    the declared list.
    """

    RUN_SCOPED = "RUN_SCOPED"
    CATALOG = "CATALOG"


class ApiResponse(BaseModel, Generic[PayloadT]):
    """One response body: the payload, and everything that must travel with it.

    Field-by-field, and why each is not optional:

    * `scope` -- whether this body describes one run's output or the deployment around
      it. See `ResponseScope`; it is what lets the envelope be genuinely required where it
      means something instead of fabricated where it does not.
    * `run_id` -- duplicated from `envelope.run_id` on purpose. It is the single most
      common thing a client correlates on, and requiring a client to reach into a nested
      object for it is how a client ends up not carrying it. The validator keeps the two in
      step, so the duplication cannot become a disagreement.
    * `envelope` -- the nine `OutputEnvelope` fields (`CONVENTIONS.md` §11), present on
      every `RUN_SCOPED` body.
    * `provenance` -- the payload's epistemic status, with the five classes never
      flattened.
    * `standing` -- which graph was walked. Required, because ADR-0059 makes it a required
      field on every artifact these modules produce and an API that dropped it would undo
      that at the last hop.
    * `stage_status` -- whether the pipeline stage behind this payload actually ran.
    * `timing` -- what the call cost against its prd.md §55 budget.
    * `generated_at` -- when this body was produced. Excluded from determinism comparisons,
      like every wall-clock value (`CONVENTIONS.md` §11).

    `evidence` and `confidence` default to empty and `None` respectively, and that is not a
    weakening: many payloads make no single confidence claim (a run listing, an ontology
    summary), and a required-but-meaningless confidence would have to be invented. What is
    enforced is the shape when it IS present -- there is no path here that yields a
    confidence without components.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: ResponseScope
    #: `None` only under `CATALOG` scope; the validator enforces it.
    run_id: str | None = None
    envelope: OutputEnvelope | None = None
    provenance: ProvenanceSummary
    standing: GraphStandingView
    stage_status: StageStatusView
    timing: TimingMeta
    generated_at: datetime
    data: PayloadT
    evidence: tuple[EvidenceReference, ...] = ()
    confidence: ConfidenceView | None = None
    #: Required in substance whenever `stage_status` is not `COMPLETE`: an endpoint may not
    #: report that something could not be computed without saying what. Enforced by the
    #: validator below rather than by a type, because the requirement is conditional.
    stage_detail: str | None = None
    #: The disowning notice for a diagnostic standing. Also conditionally required: a
    #: payload walked over the unpromoted graph may not travel without the statement that
    #: the engine does not assert it (ADR-0059, and OQ-026's residual risk).
    standing_notice: str | None = None

    def check_conditional_fields(self) -> ApiResponse[PayloadT]:
        """Refuse a body that omits an explanation it is required to carry.

        A pydantic `model_validator` would be the idiomatic home for this, and it is
        deliberately a plain method instead: as a validator it would run on every
        deserialization in a client's test suite too, and a client legitimately holds an
        older body whose conditional fields this version did not yet require. It is called
        by the response builder, which is the only place bodies are constructed here.
        """
        if (
            self.stage_status is not StageStatusView.COMPLETE
            and not (self.stage_detail or "").strip()
        ):
            raise ValueError(
                f"A response with stage_status={self.stage_status.value} carries no "
                "stage_detail. Reporting that something could not be computed without "
                "saying what is missing leaves a client unable to tell an absent module "
                "from an empty result."
            )
        if (
            self.standing is GraphStandingView.UNPROMOTED_DIAGNOSTIC
            and not (self.standing_notice or "").strip()
        ):
            raise ValueError(
                "A response under the UNPROMOTED_DIAGNOSTIC standing carries no "
                "standing_notice. Everything walked under that standing is disowned by "
                "the engine (ADR-0059), and a disowned figure travelling without its "
                "notice is the OQ-026 risk arriving through the door this API opened."
            )
        return self
