"""Cloud OAuth authentication module.

Handles PKCE code_verifier/code_challenge generation, Keycloak discovery,
OAuth state management, token exchange, and token refresh for errand-cloud.
"""
import base64
import hashlib
import logging
import os
import secrets
import time

import httpx

logger = logging.getLogger(__name__)

# In-memory OAuth state store: state_key -> {code_verifier, created_at}
_oauth_states: dict[str, dict] = {}
_STATE_TTL = 600  # 10 minutes


def generate_pkce() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    """
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def store_state(state: str, code_verifier: str) -> None:
    """Store an OAuth state parameter with its PKCE code_verifier."""
    _cleanup_expired_states()
    _oauth_states[state] = {
        "code_verifier": code_verifier,
        "created_at": time.time(),
    }


def consume_state(state: str) -> str | None:
    """Consume and return the code_verifier for a state parameter, or None if invalid/expired."""
    _cleanup_expired_states()
    entry = _oauth_states.pop(state, None)
    if entry is None:
        return None
    if time.time() - entry["created_at"] > _STATE_TTL:
        return None
    return entry["code_verifier"]


def _cleanup_expired_states() -> None:
    """Remove expired state entries."""
    now = time.time()
    expired = [k for k, v in _oauth_states.items() if now - v["created_at"] > _STATE_TTL]
    for k in expired:
        del _oauth_states[k]


def get_keycloak_urls(cloud_service_url: str, realm_url: str | None, client_id: str) -> dict:
    """Derive Keycloak endpoint URLs.

    Returns dict with keys: authorize_url, token_url, client_id.
    """
    if realm_url:
        base = realm_url.rstrip("/")
    else:
        # Default: derive from cloud service URL
        # https://service.errand.cloud -> https://auth.errand.cloud/realms/errand
        base = "https://auth.errand.cloud/realms/errand"

    return {
        "authorize_url": f"{base}/protocol/openid-connect/auth",
        "token_url": f"{base}/protocol/openid-connect/token",
        "client_id": client_id,
    }


async def exchange_code(
    token_url: str,
    client_id: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict:
    """Exchange an authorization code for tokens using PKCE.

    Returns the token response dict with access_token, refresh_token, expires_in, etc.
    Raises httpx.HTTPStatusError on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_token(
    token_url: str,
    client_id: str,
    refresh_token_value: str,
) -> dict:
    """Refresh an access token using the offline refresh token.

    Returns the token response dict with new access_token, refresh_token, expires_in, etc.
    Raises httpx.HTTPStatusError on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token_value,
            },
        )
        resp.raise_for_status()
        return resp.json()
