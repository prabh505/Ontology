"""Cursor pagination that is stable because the sequence underneath it is.

Offset pagination is wrong here for the usual reason and for a sharper one. The usual: a
page boundary shifts when the collection changes. The sharper: `CONVENTIONS.md` §11 already
fixes a canonical sort key per artifact -- events by `(t_earliest, t_latest, event_id)`,
entities by `entity_id`, edges by `(source, target, kind)` -- so a total sequence already
exists, and a cursor naming a position in THAT sequence is stable by construction rather
than by luck.

The cursor is the last item's identifier, not an index and not an opaque blob. Three
consequences, all of them wanted: a client can see what it is holding, a cursor from
another run is detectable (the facade refuses an identifier that is not in the run it was
handed), and there is no encoded state to version.
"""

from __future__ import annotations

from typing import Final, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAXIMUM_PAGE_SIZE",
    "Page",
    "PageItemT",
    "clamp_limit",
]

PageItemT = TypeVar("PageItemT")

#: What a caller gets when it asks for nothing in particular.
DEFAULT_PAGE_SIZE: Final[int] = 100

#: The ceiling, and it is enforced rather than advisory. An unbounded page is how one
#: request materializes a whole run into memory and makes the prd.md §55 budgets
#: unmeetable for everybody else on the process.
MAXIMUM_PAGE_SIZE: Final[int] = 1_000


class Page(BaseModel, Generic[PageItemT]):
    """One page of a canonically sequenced collection.

    `has_more` is carried explicitly rather than inferred from `next_cursor`. They can
    differ at exactly one boundary -- a page that is exactly the size of the remainder --
    and a client inferring "more" from a non-null cursor would make one empty request every
    time a collection divides evenly.

    `total_known` is `None` when counting the collection would cost a traversal the caller
    did not ask for. A `None` here means "not counted", never "zero"; conflating those is
    how an interface reports a collection as empty because nobody counted it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[PageItemT, ...] = ()
    next_cursor: str | None = None
    has_more: bool = False
    total_known: int | None = None
    sequenced_by: str = Field(min_length=1)


def clamp_limit(requested: int | None) -> int:
    """Return a page size within the declared bounds.

    Clamps rather than refuses. A caller asking for more than the ceiling has made a
    reasonable request that this deployment will not serve in one response; answering with
    the ceiling and an honest `has_more` is more useful than a 422, and the ceiling is
    published in `docs/api.md` so the clamp is not a surprise.
    """
    if requested is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(requested, MAXIMUM_PAGE_SIZE))
