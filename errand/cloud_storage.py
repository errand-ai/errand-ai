"""Cloud storage token refresh utilities.

Handles OAuth token refresh for Google Drive and OneDrive before
injecting credentials into task-runner containers.
"""

import logging
import os
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PlatformCredential
from platforms.credentials import encrypt

logger = logging.getLogger(__name__)

REFRESH_BUFFER_SECONDS = 300  # 5 minutes


def _get_token_url(provider: str) -> str:
    if provider == "google_drive":
        return "https://oauth2.googleapis.com/token"
    tenant_id = os.environ.get("MICROSOFT_TENANT_ID", "common")
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _get_client_credentials(provider: str) -> tuple[str, str] | None:
    if provider == "google_drive":
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    else:
        client_id = os.environ.get("MICROSOFT_CLIENT_ID", "")
        client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


async def refresh_token_if_needed(
    provider: str, credentials: dict, session: AsyncSession
) -> dict | None:
    """Refresh the access token if expired (within 5-min buffer).

    Returns updated credentials dict, or None if refresh failed.
    If token is still valid, returns credentials unchanged.
    """
    expires_at = credentials.get("expires_at", 0)
    now = time.time()

    if now < expires_at - REFRESH_BUFFER_SECONDS:
        return credentials  # still valid

    refresh_token = credentials.get("refresh_token", "")
    if not refresh_token:
        logger.warning("No refresh token for %s, cannot refresh", provider)
        return None

    client_creds = _get_client_credentials(provider)
    if client_creds is not None:
        # Direct refresh — use local client credentials
        return await _direct_refresh(provider, credentials, refresh_token, client_creds, session)

    # Cloud-proxy refresh — delegate to errand-cloud via WebSocket
    return await _cloud_proxy_refresh(provider, credentials, refresh_token, session)


async def _direct_refresh(
    provider: str,
    credentials: dict,
    refresh_token: str,
    client_creds: tuple[str, str],
    session: AsyncSession,
) -> dict | None:
    """Refresh token directly with the provider's token endpoint."""
    client_id, client_secret = client_creds
    token_url = _get_token_url(provider)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
                timeout=10,
            )

        if resp.status_code != 200:
            logger.warning(
                "Token refresh failed for %s: HTTP %d %s",
                provider, resp.status_code, resp.text,
            )
            return None

        tokens = resp.json()
        new_access_token = tokens.get("access_token")
        if not new_access_token:
            logger.warning("Token refresh for %s returned no access_token", provider)
            return None
        credentials["access_token"] = new_access_token
        credentials["expires_at"] = int(time.time()) + tokens.get("expires_in", 3600)
        if "refresh_token" in tokens:
            credentials["refresh_token"] = tokens["refresh_token"]

        result = await session.execute(
            select(PlatformCredential).where(
                PlatformCredential.platform_id == provider
            )
        )
        cred = result.scalar_one_or_none()
        if cred:
            cred.encrypted_data = encrypt(credentials)
            await session.commit()

        logger.info("Refreshed %s access token (direct)", provider)
        return credentials

    except Exception:
        logger.warning("Token refresh error for %s", provider, exc_info=True)
        return None


async def _cloud_proxy_refresh(
    provider: str,
    credentials: dict,
    refresh_token: str,
    session: AsyncSession,
) -> dict | None:
    """Refresh token via cloud proxy over WebSocket."""
    from cloud_client import get_client, is_connected

    if not is_connected():
        logger.warning("Cloud WebSocket not connected, cannot refresh %s token", provider)
        return None

    client = get_client()
    if not client:
        logger.warning("No active cloud client, cannot refresh %s token", provider)
        return None

    result = await client.send_and_await(
        message={
            "type": "oauth_refresh",
            "provider": provider,
            "refresh_token": refresh_token,
        },
        response_type="oauth_refresh_result",
        provider=provider,
        timeout=30.0,
    )

    if result is None:
        logger.warning("Cloud proxy refresh failed for %s", provider)
        return None

    new_access_token = result.get("access_token")
    if not new_access_token:
        logger.warning("Cloud proxy refresh for %s returned no access_token", provider)
        return None

    credentials["access_token"] = new_access_token
    credentials["expires_at"] = int(time.time()) + result.get("expires_in", 3600)
    if "refresh_token" in result:
        credentials["refresh_token"] = result["refresh_token"]

    db_result = await session.execute(
        select(PlatformCredential).where(
            PlatformCredential.platform_id == provider
        )
    )
    cred = db_result.scalar_one_or_none()
    if cred:
        cred.encrypted_data = encrypt(credentials)
        await session.commit()

    logger.info("Refreshed %s access token (cloud proxy)", provider)
    return credentials
