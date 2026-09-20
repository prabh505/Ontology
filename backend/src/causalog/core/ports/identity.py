"""`Principal` and `Authenticator` -- who is asking, and what they are allowed to ask for.

prd.md §54 requires role-based access and requires every access to an endpoint returning
inferences to be audited with an `actor` and a `role` (`CONVENTIONS.md` §8). Neither
document says where an actor comes from, and until this port existed nothing in the
distribution could name one -- the audit schema had an `actor` column that no code path
could populate.

The port is declared here, at L0, for the reason ADR-0014 declares every other port here:
so that the layer needing an identity depends on the SHAPE of one and never on the
mechanism that issued it. V1's mechanism is a signed token verified with the standard
library (ADR-0082); an external identity provider is an adapter swap and touches no route.

`Role` is a closed set, and it is closed deliberately. prd.md §54 says "Role-based access"
and enumerates nothing; prd.md §10 names five user types and nothing else in the document
names a sixth. Inventing one here would be inventing a requirement (`CONVENTIONS.md` §4),
so the set is exactly §10's five, under names that carry no domain vocabulary because
`causalog.api` is in the LAW-DOMAIN scan (ADR-0081).
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

__all__ = ["Authenticator", "Principal", "Role"]


class Role(Enum):
    """The five prd.md §10 user types, as the closed access-control vocabulary.

    The names are functional rather than domain-flavoured: this enum is read by
    `causalog.api`, which the LAW-DOMAIN lint scans (ADR-0081), and a role named after the
    first implementation's industry would put that industry into the reasoning surface's
    vocabulary permanently.

    The mapping back to prd.md §10 is one-to-one and is published in `docs/api.md`:

    | prd.md §10 user type      | member                |
    |---------------------------|-----------------------|
    | Operations Manager        | `OPERATIONS_MANAGER`  |
    | Supply Chain Analyst      | `HISTORICAL_ANALYST`  |
    | Executive Leadership      | `EXECUTIVE`           |
    | Data Scientist            | `DATA_SCIENTIST`      |
    | Process Improvement Team  | `PROCESS_IMPROVEMENT` |
    """

    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    HISTORICAL_ANALYST = "HISTORICAL_ANALYST"
    EXECUTIVE = "EXECUTIVE"
    DATA_SCIENTIST = "DATA_SCIENTIST"
    PROCESS_IMPROVEMENT = "PROCESS_IMPROVEMENT"


class Principal(BaseModel):
    """One authenticated caller: who they are, what role they hold, and for how long.

    `actor` is what the audit trail records (`CONVENTIONS.md` §8). It is an opaque,
    stable identifier for the caller -- never a credential, and never anything that would
    put a secret into an append-only table that is by design impossible to edit.

    `issued_at_epoch` and `expires_at_epoch` are integer seconds rather than `datetime`
    because they are transported inside a signed token and are compared against a `Clock`
    reading; an integer has exactly one serialization and so cannot make a signature
    depend on a formatting choice.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor: str
    role: Role
    issued_at_epoch: int
    expires_at_epoch: int


@runtime_checkable
class Authenticator(Protocol):
    """Turn a transport credential into a `Principal`, or refuse it.

    Refusal is an exception, never a `None` and never an anonymous fallback principal: a
    caller that silently degrades to a default identity writes audit rows attributing a
    read to whoever that default names, which is worse than having no audit trail because
    it looks like one.
    """

    def authenticate(self, credential: str) -> Principal:
        """Return the `Principal` a credential attests to.

        Raises:
            ContractViolationError: the credential is malformed, unsigned, signed with the
                wrong key, or expired. The message names which of those it was and never
                echoes the credential.
        """
        ...
