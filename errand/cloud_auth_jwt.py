"""Cloud-trusted JWT authentication.

Validates JWTs forwarded by errand-cloud via X-Cloud-JWT header.
The JWT is a Keycloak token from the cloud realm, validated against
the cloud Keycloak's JWKS endpoint.
"""
import logging
import os
import secrets
import time

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Environment variable that pins the expected JWT issuer. Without this the
# system would trust whatever `iss` claim the (unverified) token carries and
# happily fetch JWKS from an attacker-controlled URL. See S3 in
# fix-code-review-bugs.
CLOUD_KEYCLOAK_URL_ENV = "CLOUD_KEYCLOAK_URL"

# JWKS cache
_jwks_client: PyJWKClient | None = None
_jwks_issuer: str | None = None
_jwks_fetched_at: float = 0
JWKS_CACHE_TTL = 3600  # 1 hour


def _expected_cloud_issuer() -> str | None:
    """Return the trusted cloud Keycloak issuer URL, or None if not configured."""
    value = os.environ.get(CLOUD_KEYCLOAK_URL_ENV, "").strip()
    return value.rstrip("/") or None


async def _get_cloud_service_url() -> str | None:
    """Get the cloud service URL from platform credentials."""
    from database import async_session
    from models import Setting
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(Setting).where(Setting.key == "cloud_service_url")
        )
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            return str(setting.value)
    return None


def _get_jwks_url_from_issuer(issuer: str) -> str:
    """Derive JWKS URL from the JWT issuer claim (Keycloak realm URL)."""
    # Keycloak issuer is like: https://keycloak.example.com/realms/myrealm
    # JWKS is at: https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs
    return f"{issuer.rstrip('/')}/protocol/openid-connect/certs"


def _ensure_jwks_client(issuer: str) -> PyJWKClient:
    """Get or create a cached JWKS client for the given issuer."""
    global _jwks_client, _jwks_issuer, _jwks_fetched_at

    now = time.time()
    if (
        _jwks_client is not None
        and _jwks_issuer == issuer
        and (now - _jwks_fetched_at) < JWKS_CACHE_TTL
    ):
        return _jwks_client

    jwks_url = _get_jwks_url_from_issuer(issuer)
    _jwks_client = PyJWKClient(jwks_url)
    _jwks_issuer = issuer
    _jwks_fetched_at = now
    logger.info("Cloud JWKS client initialized for issuer: %s", issuer)
    return _jwks_client


def validate_cloud_jwt(token: str) -> dict:
    """Validate a cloud JWT token. Returns claims dict.

    Raises jwt.InvalidTokenError on failure.

    The token's ``iss`` claim MUST match the ``CLOUD_KEYCLOAK_URL`` env var
    before any JWKS fetch is attempted. This prevents an attacker-forged
    token from coercing the server into calling an arbitrary URL (SSRF) and
    accepting a signature from an untrusted key source.
    """
    # Pin the expected issuer from configuration, not from the token itself.
    expected_issuer = _expected_cloud_issuer()
    if expected_issuer is None:
        raise jwt.InvalidTokenError(
            f"Cloud JWT validation not configured: {CLOUD_KEYCLOAK_URL_ENV} env var is unset"
        )

    # Peek at the issuer without verification
    unverified = jwt.decode(token, options={"verify_signature": False})
    issuer = unverified.get("iss", "")
    if not issuer:
        raise jwt.InvalidTokenError("Missing issuer claim")
    if issuer.rstrip("/") != expected_issuer:
        raise jwt.InvalidTokenError(
            "JWT issuer does not match configured cloud Keycloak URL"
        )

    jwks_client = _ensure_jwks_client(issuer)

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except jwt.exceptions.PyJWKClientError:
        # Key not found — refresh JWKS and retry once
        global _jwks_fetched_at
        _jwks_fetched_at = 0
        jwks_client = _ensure_jwks_client(issuer)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
    )
    return claims


# Request state key for marking proxy-originated requests
PROXY_REQUEST_MARKER = "_cloud_proxy_request"

# Per-process secret used by the proxy handler to prove a request originated
# from the cloud WebSocket client (not from an external caller).
PROXY_SECRET = secrets.token_urlsafe(32)
PROXY_SECRET_HEADER = "X-Proxy-Secret"
