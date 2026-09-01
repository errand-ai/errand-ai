"""Cloud OAuth authentication module.

Handles authentication with errand-cloud via the OAuth 2.0 device
authorization grant (RFC 8628), plus token refresh.
errand-cloud acts as the OAuth intermediary with Keycloak — this module
only needs to know the cloud service URL.
"""
import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


async def refresh_token(cloud_url: str, refresh_token_value: str) -> dict:
    """Refresh an access token via errand-cloud.

    Returns the token response dict with new access_token, refresh_token, expires_in, etc.
    Raises httpx.HTTPStatusError on failure.
    """
    url = f"{cloud_url.rstrip('/')}/auth/tenant/refresh"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(url, json={"refresh_token": refresh_token_value})
        resp.raise_for_status()
        return resp.json()


# --- Device authorization grant (RFC 8628) ---
#
# errand-cloud removed the `redirect_uri` parameter from its tenant login: a
# caller-supplied callback meant the authorization code could be delivered to
# an attacker. The device grant has no callback at all — this instance asks for
# a code, shows the user a short verification code and a URL on the cloud's own
# origin, and polls for tokens. Nothing is sent that the cloud would have to
# validate, and nothing an attacker could substitute.
#
# Polling is deliberately server-side. The `device_code` is a bearer credential
# — whoever holds it collects the tokens once the grant is approved — so it
# never leaves this process.

DEVICE_TOKENS = "tokens"
DEVICE_PENDING = "authorization_pending"
DEVICE_SLOW_DOWN = "slow_down"
DEVICE_DENIED = "access_denied"
DEVICE_EXPIRED = "expired_token"
DEVICE_ERROR = "error"

#: Used when the cloud advertises no usable interval.
DEVICE_DEFAULT_INTERVAL = 5
#: RFC 8628 §3.5: on `slow_down`, increase the interval rather than retry at
#: the same rate. The cloud rate limits these endpoints (polling 60/min per IP).
DEVICE_SLOW_DOWN_INCREMENT = 5

_DEVICE_ERROR_OUTCOMES = {
    "authorization_pending": DEVICE_PENDING,
    "slow_down": DEVICE_SLOW_DOWN,
    "access_denied": DEVICE_DENIED,
    "expired_token": DEVICE_EXPIRED,
}


@dataclass(frozen=True)
class DeviceTokenResult:
    """One poll's outcome. `tokens` is populated only for `DEVICE_TOKENS`."""

    outcome: str
    tokens: dict | None = None
    detail: str | None = None


async def request_device_code(cloud_url: str) -> dict:
    """Begin a device authorization against errand-cloud.

    Returns `{device_code, user_code, verification_uri,
    verification_uri_complete, expires_in, interval}`.
    Raises httpx.HTTPStatusError on failure.
    """
    url = f"{cloud_url.rstrip('/')}/auth/tenant/device/code"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(url, json={})
        resp.raise_for_status()
        return resp.json()


async def poll_device_token(cloud_url: str, device_code: str) -> DeviceTokenResult:
    """Poll errand-cloud once for the outcome of a device authorization.

    Never raises: every failure — including a 429 from the cloud's rate limiter
    — is reported as `DEVICE_ERROR` so the caller stops rather than tightening
    its loop.
    """
    url = f"{cloud_url.rstrip('/')}/auth/tenant/device/token"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(url, json={"device_code": device_code})
    except Exception as exc:
        logger.warning("Device token poll failed: %s", exc)
        return DeviceTokenResult(outcome=DEVICE_ERROR, detail=str(exc))

    if resp.status_code == 200:
        try:
            return DeviceTokenResult(outcome=DEVICE_TOKENS, tokens=resp.json())
        except Exception as exc:
            return DeviceTokenResult(outcome=DEVICE_ERROR, detail=f"Malformed token response: {exc}")

    if resp.status_code == 429:
        return DeviceTokenResult(
            outcome=DEVICE_ERROR,
            detail="Rate limited by the cloud service (HTTP 429)",
        )

    try:
        body = resp.json()
    except Exception:
        body = {}
    error_code = body.get("error") if isinstance(body, dict) else None
    outcome = _DEVICE_ERROR_OUTCOMES.get(error_code)
    if outcome:
        return DeviceTokenResult(outcome=outcome, detail=body.get("error_description"))

    return DeviceTokenResult(
        outcome=DEVICE_ERROR,
        detail=f"HTTP {resp.status_code}: {error_code or resp.text[:200]}",
    )


async def poll_until_complete(
    cloud_url: str,
    device_code: str,
    interval: int,
    expires_in: int,
    *,
    sleep=asyncio.sleep,
    monotonic=time.monotonic,
) -> DeviceTokenResult:
    """Poll until the grant resolves, or until it expires.

    Bounded by `expires_in` so the poller cannot outlive the grant it polls
    for. `sleep` and `monotonic` are injectable so the loop is testable
    without real time passing.
    """
    deadline = monotonic() + expires_in
    wait = interval if interval and interval > 0 else DEVICE_DEFAULT_INTERVAL

    while monotonic() < deadline:
        await sleep(wait)
        if monotonic() >= deadline:
            break

        result = await poll_device_token(cloud_url, device_code)
        if result.outcome == DEVICE_PENDING:
            continue
        if result.outcome == DEVICE_SLOW_DOWN:
            wait += DEVICE_SLOW_DOWN_INCREMENT
            continue
        return result

    return DeviceTokenResult(
        outcome=DEVICE_EXPIRED,
        detail="Device authorization expired before it was approved",
    )
