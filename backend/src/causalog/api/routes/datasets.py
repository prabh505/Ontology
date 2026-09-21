"""Dataset validation status (prd.md §53's dataset half).

prd.md §53 lists `POST /dataset/upload` and `POST /dataset/map`. Neither is served as
written, and the reasons are different:

* **Upload** is `POST /v1/jobs`. An import is a STAGE of a pipeline execution in this
  engine, not a standalone action: it pins the file, mints the `dataset_version` that
  participates in `run_id` (ADR-0035), and everything downstream depends on it. Modelling
  it as a separate upload would create a dataset that exists and belongs to no run.
* **Mapping** is pack DATA -- `ontology/packs/<domain>/mapping.yaml` -- and it participates
  in `dataset_version` through its hash. Accepting a mapping over HTTP would let a request
  change an input to `run_id` without changing anything the pin can see, which is ADR-0013's
  guarantee broken silently. A mapping is edited, reviewed and committed, not POSTed.

What IS served is the third thing the task asks for and §53 does not name: **validation
status**, which is what an author actually needs from both of the above.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from causalog.api.dependencies import AdaptersDep, ClockDep, FacadeDep, requires
from causalog.api.responses import respond_catalog
from causalog.api.schemas.envelope import ApiResponse
from causalog.api.security.authorization import Capability
from causalog.api.security.context import RequestContext
from causalog.orchestration import views
from causalog.orchestration.timing import TimingMeta

__all__ = ["router"]

router = APIRouter(prefix="/v1/datasets", tags=["datasets"])

ObservedDep = Annotated[RequestContext, Depends(requires(Capability.READ_OBSERVED))]


@router.get("/{dataset_id}/validation", response_model=ApiResponse[views.ValidationStatusView])
def read_validation_status(
    dataset_id: str,
    facade: FacadeDep,
    adapters: AdaptersDep,
    clock: ClockDep,
    context: ObservedDep,
) -> ApiResponse[views.ValidationStatusView]:
    """Report whether a dataset is described, and whether it is usable.

    `CATALOG` scope: a dataset is not a run. A dataset is a pack plus a mapping plus a
    pinned file; a run is those PLUS a rule pack, an engine version and a seed (ADR-0013).
    Attaching a run envelope here would claim this answer came from a run it did not.

    The two measurements are reported separately and never combined into one verdict. A
    dataset whose every column binds can still be unusable, and one with mapping gaps can
    still be measured clean over what it does bind.
    """
    status = facade.validate_dataset(dataset_id, adapters.repository_root)
    return respond_catalog(
        status,
        clock=clock,
        timing=TimingMeta.measured(operation="validate_dataset", elapsed_seconds=0.0, budget=None),
        provenance=views.provenance_summary(()),
    )
