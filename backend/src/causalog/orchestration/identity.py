"""The V1 `Authenticator`: a signed, expiring token verified with the standard library.

ADR-0082. prd.md §54 says "Role-based access" and names no mechanism, and
`CONVENTIONS.md` §12 requires an ADR before any third-party import is written -- so
reaching for a JWT library would have been a dependency decision taken to satisfy an
unstated requirement. The standard library signs and verifies adequately, and the
`Authenticator` port means an external identity provider later is an adapter swap that
touches no route.

**Token form**, chosen so that every field a verifier needs is in the token and nothing a
verifier needs is looked up:

    <payload-b64url>.<signature-b64url>
    payload = actor | role | issued_at_epoch | expires_at_epoch   (canonical_payload)

Three properties, each of which a hand-rolled scheme usually gets wrong:

* **The signature covers the payload bytes that were transported**, not a re-serialization
  of a parsed payload. Re-serializing lets a verifier accept a payload whose canonical form
  differs from what was signed, which is the classic signature-bypass shape.
* **Comparison is `hmac.compare_digest`**, never `==`. A timing-variable comparison on a
  signature leaks the signature one byte at a time.
* **Expiry is checked against an injected `Clock`**, never `datetime.now()`. Time is a port
  in this repository (ADR-0014), and a test that cannot move the clock cannot assert that
  an expired token is refused.

What this is NOT: a key-rotation scheme, a revocation list, or an authorization decision.
The first two are deployment concerns this class deliberately leaves to the identity
provider it will eventually front; the third belongs to `causalog.api.security`, and
keeping it out of here is what stops "who are you" and "what may you do" from becoming one
tangled check.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import os
from hashlib import sha256
from typing import Final

from causalog.core.errors import ContractViolationError
from causalog.core.identifiers import canonical_payload, canonical_text
from causalog.core.ports.clock import Clock
from causalog.core.ports.identity import Principal, Role

__all__ = ["SECRET_ENVIRONMENT_VARIABLE", "SignedTokenAuthenticator", "mint_token"]

#: The one spelling of the signing secret. A second spelling would let the issuer and the
#: verifier disagree while both look configured.
# S105 flags the *name* of this constant, not its value: the value is the name of an
# environment variable and holding it in a differently-named constant would only hide
# the string from the rule. The secret itself is read from the environment at call
# time, is never a default, and is never logged or echoed in an error.
SECRET_ENVIRONMENT_VARIABLE: Final[str] = "CAUSALOG_API_SECRET"  # noqa: S105

#: Refuses a secret short enough to be guessed. Not a strength estimate -- it is a floor
#: that catches the failure actually seen in practice, which is a placeholder left in an
#: environment file.
_MINIMUM_SECRET_LENGTH: Final[int] = 32


def _encode(raw: bytes) -> str:
    """Base64url without padding, so a token carries no `=` to be mangled in a header."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(text: str) -> bytes:
    """Reverse `_encode`, restoring the padding base64 requires."""
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _payload_text(principal: Principal) -> str:
    """Return the canonical signed payload for a principal.

    Built with `core.identifiers.canonical_payload` rather than an f-string so that the
    signed bytes follow the same canonicalization rule as every content address in this
    system. A second formatting convention for a second purpose is how two things that must
    agree stop agreeing.
    """
    return canonical_payload(
        canonical_text(principal.actor),
        canonical_text(principal.role.value),
        canonical_text(str(principal.issued_at_epoch)),
        canonical_text(str(principal.expires_at_epoch)),
    )


def mint_token(principal: Principal, *, secret: str) -> str:
    """Issue a token for a principal. Present so that tests and operators share one issuer.

    A second issuer -- a fixture that built tokens its own way -- would let the test suite
    pass against a format the verifier does not actually accept.
    """
    payload = _payload_text(principal).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload, sha256).digest()
    return f"{_encode(payload)}.{_encode(signature)}"


class SignedTokenAuthenticator:
    """Verify a signed, expiring token and return the `Principal` it attests to."""

    def __init__(self, secret: str, clock: Clock) -> None:
        """Bind the verifier to a secret and an injected clock."""
        if len(secret) < _MINIMUM_SECRET_LENGTH:
            raise ContractViolationError(
                f"The API signing secret is shorter than {_MINIMUM_SECRET_LENGTH} "
                "characters. A short secret makes every signature in the deployment "
                "forgeable, and the value is never echoed in this message precisely "
                "because it is a secret (CONVENTIONS.md §8)."
            )
        self._secret = secret.encode("utf-8")
        self._clock = clock

    @classmethod
    def from_environment(cls, clock: Clock) -> SignedTokenAuthenticator:
        """Build a verifier from `CAUSALOG_API_SECRET`."""
        secret = os.environ.get(SECRET_ENVIRONMENT_VARIABLE)
        if not secret:
            raise ContractViolationError(
                f"No API signing secret: set {SECRET_ENVIRONMENT_VARIABLE}. There is "
                "deliberately no development default -- a default secret is a published "
                "secret, and an API that authenticates against one authenticates nobody."
            )
        return cls(secret, clock)

    def authenticate(self, credential: str) -> Principal:
        """Return the `Principal` a credential attests to, or refuse it.

        Every refusal raises `ContractViolationError` and names WHICH check failed --
        malformed, badly signed, or expired -- because an operator debugging a 401 needs
        that and an attacker learns nothing from it they could not learn by trying. The
        credential itself is never echoed.
        """
        payload_text, separator, signature_text = credential.partition(".")
        if not separator or not payload_text or not signature_text:
            raise ContractViolationError(
                "The API credential is malformed: expected '<payload>.<signature>'. The "
                "credential is not echoed here -- an error message is a place secrets "
                "leak from (CONVENTIONS.md §8)."
            )
        try:
            payload = _decode(payload_text)
            signature = _decode(signature_text)
        except (binascii.Error, ValueError) as failure:
            raise ContractViolationError(
                "The API credential is not valid base64url in one of its two parts."
            ) from failure

        # The signature is verified against the TRANSPORTED bytes, never against a
        # re-serialization of a parsed payload. Re-serializing would let a payload whose
        # canonical form differs from what was signed pass verification.
        expected = hmac.new(self._secret, payload, sha256).digest()
        if not hmac.compare_digest(expected, signature):
            raise ContractViolationError(
                "The API credential's signature does not verify against the configured "
                "secret. Either the token was issued by a different deployment or it was "
                "altered in transit."
            )

        principal = self._parse(payload)
        now_epoch = int(self._clock.now_utc().timestamp())
        if now_epoch >= principal.expires_at_epoch:
            raise ContractViolationError(
                f"The API credential expired at epoch {principal.expires_at_epoch} and "
                f"the clock reads {now_epoch}. An expired credential is refused rather "
                "than renewed: renewal is the issuer's decision, not the verifier's."
            )
        return principal

    def _parse(self, payload: bytes) -> Principal:
        """Turn verified payload bytes into a `Principal`.

        Reached only after the signature verifies, so a malformed payload here means the
        holder of the secret issued something wrong -- which is a contract violation on the
        issuing side and is reported as one, not as a rejected credential.
        """
        try:
            actor, role_name, issued, expires = payload.decode("utf-8").split("|")
        except (UnicodeDecodeError, ValueError) as failure:
            raise ContractViolationError(
                "A correctly signed API credential carried a payload with the wrong "
                "shape. Expected four fields: actor, role, issued_at, expires_at."
            ) from failure
        try:
            role = Role(role_name)
        except ValueError as failure:
            raise ContractViolationError(
                f"A correctly signed API credential names role {role_name!r}, which is "
                f"not in the closed set {sorted(member.value for member in Role)}. The "
                "roles are prd.md §10's five user types and the set is closed on purpose "
                "(ADR-0081)."
            ) from failure
        try:
            return Principal(
                actor=actor,
                role=role,
                issued_at_epoch=int(issued),
                expires_at_epoch=int(expires),
            )
        except ValueError as failure:
            raise ContractViolationError(
                "A correctly signed API credential carried a non-integer instant. The "
                "token's instants are integer epoch seconds so that a signature cannot "
                "depend on a formatting choice."
            ) from failure
