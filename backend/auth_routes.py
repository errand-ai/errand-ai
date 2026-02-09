from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

import auth as auth_module

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    base_url = str(request.base_url).rstrip("/")
    params = {
        "client_id": auth_module.oidc.client_id,
        "redirect_uri": f"{base_url}/auth/callback",
        "response_type": "code",
        "scope": "openid",
    }
    return RedirectResponse(
        url=f"{auth_module.oidc.authorization_endpoint}?{urlencode(params)}"
    )


@router.get("/callback")
async def callback(request: Request, code: str = "", error: str = "", error_description: str = ""):
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

    return RedirectResponse(url=f"/#{fragment}")


@router.get("/logout")
async def logout(request: Request, id_token_hint: str = ""):
    base_url = str(request.base_url).rstrip("/")
    params = {
        "post_logout_redirect_uri": f"{base_url}/",
    }
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return RedirectResponse(
        url=f"{auth_module.oidc.end_session_endpoint}?{urlencode(params)}"
    )
