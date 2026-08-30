import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth as auth_module
from database import get_session
from models import Setting
from oauth_state import (
    STATE_COOKIE_NAME,
    STATE_TTL_SECONDS,
    StateValidationError,
    issue_state,
    validate_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_oidc():
    if auth_module.oidc is None:
        raise HTTPException(status_code=503, detail="OIDC authentication is not configured")


async def _state_secret(session: AsyncSession) -> str:
    """The secret the OAuth `state` is signed with.

    Reuses `jwt_signing_secret`, which `main.py` seeds on startup. If it is
    missing we fail rather than fall back to an unsigned flow.
    """
    result = await session.execute(
        select(Setting.value).where(Setting.key == "jwt_signing_secret")
    )
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(status_code=500, detail="JWT signing secret not configured")
    return str(secret)


@router.get("/login")
async def login(request: Request, session: AsyncSession = Depends(get_session)):
    _require_oidc()
    base_url = str(request.base_url).rstrip("/")
    state, nonce = issue_state(await _state_secret(session))
    params = {
        "client_id": auth_module.oidc.client_id,
        "redirect_uri": f"{base_url}/auth/callback",
        "response_type": "code",
        "scope": "openid offline_access",
        "state": state,
    }
    response = RedirectResponse(
        url=f"{auth_module.oidc.authorization_endpoint}?{urlencode(params)}"
    )
    # SameSite=lax so the cookie survives the provider's top-level redirect
    # back to /auth/callback, which strict would drop.
    response.set_cookie(
        STATE_COOKIE_NAME,
        nonce,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/auth",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    session: AsyncSession = Depends(get_session),
):
    _require_oidc()
    if error:
        raise HTTPException(status_code=401, detail=error_description or error)

    if not code:
        raise HTTPException(status_code=401, detail="Missing authorization code")

    # Validated before the token exchange: a callback we cannot tie to a login
    # this browser started must not reach the provider at all.
    try:
        validate_state(
            state, request.cookies.get(STATE_COOKIE_NAME, ""), await _state_secret(session)
        )
    except StateValidationError as exc:
        logger.warning("Rejected OIDC callback: %s", exc)
        raise HTTPException(status_code=401, detail=f"Invalid authorization state: {exc}")

    base_url = str(request.base_url).rstrip("/")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            auth_module.oidc.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": auth_module.oidc.client_id,
                "client_secret": auth_module.oidc.client_secret,
                "code": code,
                "redirect_uri": f"{base_url}/auth/callback",
            },
            timeout=10,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Token exchange failed")

    tokens = resp.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="No access token in response")

    fragment = f"access_token={access_token}"
    id_token = tokens.get("id_token")
    if id_token:
        fragment += f"&id_token={id_token}"
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        fragment += f"&refresh_token={refresh_token}"

    response = RedirectResponse(url=f"/#{fragment}")
    response.delete_cookie(STATE_COOKIE_NAME, path="/auth")
    return response


@router.post("/refresh")
async def refresh(request: Request):
    _require_oidc()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Missing refresh_token")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                auth_module.oidc.token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "client_id": auth_module.oidc.client_id,
                    "client_secret": auth_module.oidc.client_secret,
                    "refresh_token": refresh_token,
                },
                timeout=10,
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Token refresh failed")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")

    tokens = resp.json()
    result = {"access_token": tokens["access_token"]}
    if "id_token" in tokens:
        result["id_token"] = tokens["id_token"]
    if "refresh_token" in tokens:
        result["refresh_token"] = tokens["refresh_token"]
    return result


@router.get("/logout")
async def logout(request: Request, id_token_hint: str = ""):
    _require_oidc()
    base_url = str(request.base_url).rstrip("/")
    params = {
        "post_logout_redirect_uri": f"{base_url}/",
    }
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return RedirectResponse(
        url=f"{auth_module.oidc.end_session_endpoint}?{urlencode(params)}"
    )
