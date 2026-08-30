"""Signed, expiring CSRF `state` for the OIDC authorization code flow.

RFC 6749 §10.12. Without `state`, an attacker can complete an authorization
flow the victim's browser never began and have the victim's session bound to
the attacker's identity. errand had no `state` at all before this module.

The value is a JWT signed with the server's `jwt_signing_secret`, carrying a
random nonce and an expiry. The same nonce is set as a short-lived HttpOnly
cookie, so the state is bound to the browser that started the flow: holding
the callback URL is not enough, you must also hold the cookie.

Deliberately stateless. Persisting nonces in Postgres or Valkey is the more
conventional design but adds a round-trip to the login path, a cleanup
obligation, and a failure mode where a restart invalidates in-flight logins.
The cost of signing instead is that a captured state stays usable until it
expires, which is why STATE_TTL_SECONDS is short.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt

logger = logging.getLogger(__name__)

STATE_COOKIE_NAME = "errand_oauth_state"
STATE_TTL_SECONDS = 600
_ALGORITHM = "HS256"


class StateValidationError(Exception):
    """The callback's `state` did not validate. Always fatal to the flow."""


def issue_state(secret: str) -> tuple[str, str]:
    """Return `(state, nonce)` for a new authorization request.

    `state` goes in the authorization URL; `nonce` goes in the cookie.
    """
    nonce = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    state = jwt.encode(
        {"nonce": nonce, "iat": now, "exp": now + timedelta(seconds=STATE_TTL_SECONDS)},
        secret,
        algorithm=_ALGORITHM,
    )
    return state, nonce


def validate_state(state: str, cookie_nonce: str, secret: str) -> None:
    """Raise `StateValidationError` unless `state` is one we issued to this browser.

    There is no permissive branch here on purpose. Warning-and-continuing when
    `state` is absent would leave the vulnerability fully intact for an
    attacker who simply omits the parameter, which is the attack itself.
    """
    if not state:
        raise StateValidationError("Missing state parameter")
    if not cookie_nonce:
        raise StateValidationError("Missing state cookie")

    try:
        claims = jwt.decode(state, secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise StateValidationError("State expired") from exc
    except jwt.InvalidTokenError as exc:
        raise StateValidationError("State signature invalid") from exc

    signed_nonce = claims.get("nonce")
    if not isinstance(signed_nonce, str) or not secrets.compare_digest(
        signed_nonce, cookie_nonce
    ):
        raise StateValidationError("State does not match the initiating browser")
