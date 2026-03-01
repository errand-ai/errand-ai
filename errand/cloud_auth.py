"""Cloud OAuth authentication module.

Handles authentication with errand-cloud's tenant auth flow.
errand-cloud acts as the OAuth intermediary with Keycloak — this module
only needs to know the cloud service URL.
"""
import logging

import httpx

logger = logging.getLogger(__name__)


async def exchange_code(cloud_url: str, code: str) -> dict:
    """Exchange an authorization code for tokens via errand-cloud.

    Returns the token response dict with access_token, refresh_token, expires_in, etc.
    Raises httpx.HTTPStatusError on failure.
    """
    url = f"{cloud_url.rstrip('/')}/auth/tenant/token"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"code": code})
        resp.raise_for_status()
        return resp.json()


async def refresh_token(cloud_url: str, refresh_token_value: str) -> dict:
    """Refresh an access token via errand-cloud.

    Returns the token response dict with new access_token, refresh_token, expires_in, etc.
    Raises httpx.HTTPStatusError on failure.
    """
    url = f"{cloud_url.rstrip('/')}/auth/tenant/refresh"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"refresh_token": refresh_token_value})
        resp.raise_for_status()
        return resp.json()
