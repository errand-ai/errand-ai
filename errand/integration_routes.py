"""Cloud storage integration routes.

OAuth 2.0 Authorization Code flow for Google Drive and OneDrive.
Credentials stored encrypted in PlatformCredential.
"""

import logging
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from events import get_valkey
from models import PlatformCredential, Setting
from platforms.credentials import encrypt, load_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

OAUTH_STATE_TTL = 600  # 10 minutes


async def _require_user(request: Request):
    """Auth dependency — late import to avoid circular import with main.py."""
    from main import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    security = HTTPBearer(auto_error=True)
    credentials = await security(request)
    return await get_current_user(request, credentials)


@dataclass
class ProviderConfig:
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: str
    client_id_env: str
    client_secret_env: str
    extra_auth_params: dict


def _init_providers():
    """Build provider configs. Microsoft tenant_id is resolved at call time."""
    tenant_id = os.environ.get("MICROSOFT_TENANT_ID", "common")
    return {
        "google_drive": ProviderConfig(
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://www.googleapis.com/oauth2/v2/userinfo",
            scopes="openid email profile https://www.googleapis.com/auth/drive",
            client_id_env="GOOGLE_CLIENT_ID",
            client_secret_env="GOOGLE_CLIENT_SECRET",
            extra_auth_params={"access_type": "offline", "prompt": "consent"},
        ),
        "onedrive": ProviderConfig(
            authorize_url=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
            token_url=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            userinfo_url="https://graph.microsoft.com/v1.0/me",
            scopes="User.Read Files.ReadWrite.All offline_access",
            client_id_env="MICROSOFT_CLIENT_ID",
            client_secret_env="MICROSOFT_CLIENT_SECRET",
            extra_auth_params={},
        ),
    }


def _get_provider(provider: str) -> ProviderConfig:
    providers = _init_providers()
    if provider not in providers:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    return providers[provider]


def _get_client_credentials(config: ProviderConfig) -> tuple[str, str]:
    client_id = os.environ.get(config.client_id_env, "")
    client_secret = os.environ.get(config.client_secret_env, "")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=404,
            detail="Provider not configured — client credentials not set",
        )
    return client_id, client_secret


async def _cloud_available(session: AsyncSession) -> bool:
    """Check if cloud PlatformCredential exists with status 'connected'."""
    result = await session.execute(
        select(PlatformCredential).where(
            PlatformCredential.platform_id == "cloud",
            PlatformCredential.status == "connected",
        )
    )
    return result.scalar_one_or_none() is not None


def _has_local_credentials(config: ProviderConfig) -> bool:
    """Check if local OAuth client credentials are configured."""
    client_id = os.environ.get(config.client_id_env, "")
    client_secret = os.environ.get(config.client_secret_env, "")
    return bool(client_id and client_secret)


def _has_mcp_url(provider: str) -> bool:
    """Check if the provider's MCP URL is configured."""
    url_env = "GDRIVE_MCP_URL" if provider == "google_drive" else "ONEDRIVE_MCP_URL"
    return bool(os.environ.get(url_env, ""))


async def _provider_available(provider: str, session: AsyncSession) -> tuple[bool, str | None]:
    """Check provider availability, returning (available, mode).

    Mode is "direct" (local credentials), "cloud" (cloud proxy), or None.
    """
    providers = _init_providers()
    if provider not in providers:
        return False, None
    config = providers[provider]
    if not _has_mcp_url(provider):
        return False, None
    if _has_local_credentials(config):
        return True, "direct"
    if await _cloud_available(session):
        return True, "cloud"
    return False, None


async def _get_cloud_service_url(session: AsyncSession) -> str:
    """Get the cloud service URL from settings."""
    result = await session.execute(
        select(Setting).where(Setting.key == "cloud_service_url")
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting and setting.value else "https://service.errand.cloud"


@router.get("/{provider}/authorize")
async def authorize(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_user),
):
    config = _get_provider(provider)

    if _has_local_credentials(config):
        # Direct flow — use local client credentials
        client_id, _ = _get_client_credentials(config)
        base_url = str(request.base_url).rstrip("/")
        redirect_uri = f"{base_url}/api/integrations/{provider}/callback"

        state = secrets.token_urlsafe(32)
        valkey = get_valkey()
        if valkey:
            await valkey.setex(f"oauth_state:{state}", OAUTH_STATE_TTL, provider)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config.scopes,
            "state": state,
            **config.extra_auth_params,
        }
        return RedirectResponse(url=f"{config.authorize_url}?{urlencode(params)}")

    # Cloud-proxy flow — delegate to errand-cloud
    if not await _cloud_available(session):
        raise HTTPException(
            status_code=404,
            detail="Provider not configured — configure client credentials or connect to errand cloud",
        )

    from cloud_client import is_connected as cloud_ws_connected
    if not cloud_ws_connected():
        raise HTTPException(
            status_code=503,
            detail="Cloud service not connected — try again later",
        )

    state = secrets.token_urlsafe(32)
    valkey = get_valkey()
    if valkey:
        await valkey.setex(f"oauth_state:{state}", OAUTH_STATE_TTL, provider)

    # Send oauth_initiate over WebSocket
    import json as _json
    from cloud_client import get_ws
    ws = get_ws()
    if ws:
        await ws.send(_json.dumps({
            "type": "oauth_initiate",
            "state": state,
            "provider": provider,
        }))

    cloud_service_url = await _get_cloud_service_url(session)
    return RedirectResponse(
        url=f"{cloud_service_url}/oauth/{provider}/authorize?state={state}"
    )


@router.get("/{provider}/callback")
async def callback(
    provider: str,
    request: Request,
    code: str = "",
    error: str = "",
    state: str = "",
    session: AsyncSession = Depends(get_session),
):
    config = _get_provider(provider)

    if error:
        logger.warning("OAuth error for %s: %s", provider, error)
        return RedirectResponse(url="/settings/integrations?error=oauth_denied")

    if not code:
        return RedirectResponse(url="/settings/integrations?error=missing_code")

    # Validate CSRF state token
    valkey = get_valkey()
    if valkey and state:
        stored_provider = await valkey.get(f"oauth_state:{state}")
        if stored_provider != provider:
            logger.warning("OAuth state mismatch for %s", provider)
            return RedirectResponse(url="/settings/integrations?error=invalid_state")
        await valkey.delete(f"oauth_state:{state}")
    elif valkey:
        # State parameter missing — reject
        logger.warning("OAuth callback missing state for %s", provider)
        return RedirectResponse(url="/settings/integrations?error=invalid_state")

    client_id, client_secret = _get_client_credentials(config)
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/integrations/{provider}/callback"

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            config.token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=10,
        )

    if token_resp.status_code != 200:
        logger.error("Token exchange failed for %s: %s", provider, token_resp.text)
        return RedirectResponse(url="/settings/integrations?error=token_exchange_failed")

    tokens = token_resp.json()
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)

    if not access_token:
        return RedirectResponse(url="/settings/integrations?error=no_access_token")

    # Fetch user info
    user_email = ""
    user_name = ""
    try:
        async with httpx.AsyncClient() as client:
            userinfo_resp = await client.get(
                config.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        if userinfo_resp.status_code == 200:
            info = userinfo_resp.json()
            if provider == "google_drive":
                user_email = info.get("email", "")
                user_name = info.get("name", "")
            else:  # onedrive
                user_email = info.get("mail", "") or info.get("userPrincipalName", "")
                user_name = info.get("displayName", "")
    except Exception:
        logger.warning("Failed to fetch user info for %s", provider, exc_info=True)

    # Store credentials
    credential_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": int(time.time()) + expires_in,
        "token_type": tokens.get("token_type", "Bearer"),
        "user_email": user_email,
        "user_name": user_name,
    }

    encrypted = encrypt(credential_data)

    # Upsert: delete existing then insert
    await session.execute(
        delete(PlatformCredential).where(PlatformCredential.platform_id == provider)
    )
    session.add(PlatformCredential(
        platform_id=provider,
        encrypted_data=encrypted,
        status="connected",
    ))
    await session.commit()

    return RedirectResponse(url="/settings/integrations")


@router.delete("/{provider}")
async def disconnect(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_user),
):
    _get_provider(provider)  # validate provider name
    await session.execute(
        delete(PlatformCredential).where(PlatformCredential.platform_id == provider)
    )
    await session.commit()
    return {"status": "ok"}


@router.get("/status")
async def integration_status(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_user),
):
    result = {}
    for provider in ("google_drive", "onedrive"):
        available, mode = await _provider_available(provider, session)
        creds = await load_credentials(provider, session)
        connected = creds is not None
        entry: dict = {
            "available": available,
            "connected": connected,
            "mode": mode,
            "mcp_configured": _has_mcp_url(provider),
        }
        if connected and creds:
            entry["user_email"] = creds.get("user_email", "")
            entry["user_name"] = creds.get("user_name", "")
        result[provider] = entry
    return result
