from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

import auth as auth_module

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_oidc():
    if auth_module.oidc is None:
        raise HTTPException(status_code=503, detail="OIDC authentication is not configured")


@router.get("/login")
async def login(request: Request, next: str = ""):
    _require_oidc()
    base_url = str(request.base_url).rstrip("/")
    params = {
        "client_id": auth_module.oidc.client_id,
        "redirect_uri": f"{base_url}/auth/callback",
        "response_type": "code",
        "scope": "openid offline_access",
    }
    if next:
        params["state"] = next
    return RedirectResponse(
        url=f"{auth_module.oidc.authorization_endpoint}?{urlencode(params)}"
    )


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = "", error_description: str = ""):
    _require_oidc()
    if error:
        raise HTTPException(status_code=401, detail=error_description or error)

    if not code:
        raise HTTPException(status_code=401, detail="Missing authorization code")

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

    # Use state parameter as post-login redirect path
    redirect_path = state if state and state.startswith("/") else "/"

    return RedirectResponse(url=f"{redirect_path}#{fragment}")


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
