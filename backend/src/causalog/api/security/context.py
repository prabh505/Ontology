"""What one request is: who is asking, under what correlation id, and what it may do.

`correlation_id` is minted here and threads through everything the request touches -- the
structured log (`CONVENTIONS.md` §8's required fields), the audit trail (`audit_log`'s
`correlation_id` column and its partial index, whose justifying query is "everything one
API request did"), and every error body. prd.md §54 calls it a request id;
`CONVENTIONS.md` §8 and `GLOSSARY.md` call it `correlation_id`, and one concept gets one
name (`CONTEXT.md` §5), so there is no second field here holding the same value.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from causalog.core.ports.identity import Principal

__all__ = ["CORRELATION_HEADER", "RequestContext", "new_correlation_id"]

#: Accepted from the caller when present, so a client tracing a multi-service call can join
#: its own identifier to ours. Minted when absent -- never optional downstream, because an
#: audit row with no correlation id cannot answer "everything one request did".
CORRELATION_HEADER: str = "X-Correlation-Id"


def new_correlation_id() -> str:
    """Mint a request-scoped identifier.

    Random, and legitimately so: `CONVENTIONS.md` §9 bans random identifiers in the
    reasoning pipeline and names `execution_id` and `correlation_id` as the two exceptions,
    both excluded from every determinism comparison. A content-addressed correlation id
    would be a contradiction -- two identical requests are two requests.
    """
    return f"corr:{uuid.uuid4().hex}"


@dataclass(frozen=True)
class RequestContext:
    """One authenticated request in flight."""

    principal: Principal
    correlation_id: str
    endpoint: str
