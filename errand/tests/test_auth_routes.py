import json
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import get_session
from main import app

TEST_SIGNING_SECRET = "test-signing-secret-for-oauth-state"

FAKE_OIDC = {
    "client_id": "test-client",
    "client_secret": "test-secret",
    "authorization_endpoint": "https://keycloak.example/auth",
    "token_endpoint": "https://keycloak.example/token",
    "end_session_endpoint": "https://keycloak.example/logout",
}


@pytest.fixture(autouse=True)
def mock_oidc():
    """Patch auth module's oidc config for all tests in this file."""
    import auth as auth_module

    original = auth_module.oidc
    from dataclasses import dataclass

    @dataclass
    class FakeOIDC:
        client_id: str = FAKE_OIDC["client_id"]
        client_secret: str = FAKE_OIDC["client_secret"]
        authorization_endpoint: str = FAKE_OIDC["authorization_endpoint"]
        token_endpoint: str = FAKE_OIDC["token_endpoint"]
        end_session_endpoint: str = FAKE_OIDC["end_session_endpoint"]

    auth_module.oidc = FakeOIDC()
    yield
    auth_module.oidc = original


@pytest.fixture()
async def route_client():
    """Auth-route client backed by a sqlite DB holding the state-signing secret.

    `/auth/login` and `/auth/callback` both need `jwt_signing_secret` to sign
    and verify the OAuth `state`, so these routes now touch the database.
    """
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS settings ("
                "key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
        )
        await conn.execute(
            text("INSERT INTO settings (key, value) VALUES ('jwt_signing_secret', :v)"),
            {"v": json.dumps(TEST_SIGNING_SECRET)},
        )

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


async def _begin_login(route_client: AsyncClient) -> str:
    """Run /auth/login and return the `state` it issued.

    The matching nonce cookie is left on the client's cookie jar, so a
    subsequent callback on the same client is a genuine same-browser flow.
    """
    resp = await route_client.get("/auth/login")
    params = parse_qs(urlparse(resp.headers["location"]).query)
    return params["state"][0]


async def test_login_redirect_includes_offline_access(route_client: AsyncClient):
    resp = await route_client.get("/auth/login")
    assert resp.status_code == 307
    location = resp.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert "openid" in params["scope"][0]
    assert "offline_access" in params["scope"][0]


async def test_callback_includes_refresh_token_in_fragment(route_client: AsyncClient):
    state = await _begin_login(route_client)
    mock_resp = httpx.Response(
        200,
        json={
            "access_token": "at_123",
            "id_token": "id_456",
            "refresh_token": "rt_789",
        },
    )
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        resp = await route_client.get(f"/auth/callback?code=valid_code&state={state}")

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "access_token=at_123" in location
    assert "id_token=id_456" in location
    assert "refresh_token=rt_789" in location


async def test_callback_omits_refresh_token_when_absent(route_client: AsyncClient):
    state = await _begin_login(route_client)
    mock_resp = httpx.Response(
        200,
        json={
            "access_token": "at_123",
            "id_token": "id_456",
        },
    )
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        resp = await route_client.get(f"/auth/callback?code=valid_code&state={state}")

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "access_token=at_123" in location
    assert "refresh_token" not in location


# --- /auth/refresh tests ---


def _mock_httpx_client(mock_resp):
    """Helper to create a patched httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_refresh_success(route_client: AsyncClient):
    mock_resp = httpx.Response(
        200,
        json={
            "access_token": "new_at",
            "id_token": "new_id",
            "refresh_token": "new_rt",
        },
    )
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _mock_httpx_client(mock_resp)
        resp = await route_client.post("/auth/refresh", json={"refresh_token": "old_rt"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "new_at"
    assert data["id_token"] == "new_id"
    assert data["refresh_token"] == "new_rt"


async def test_refresh_success_without_new_refresh_token(route_client: AsyncClient):
    mock_resp = httpx.Response(
        200,
        json={"access_token": "new_at"},
    )
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _mock_httpx_client(mock_resp)
        resp = await route_client.post("/auth/refresh", json={"refresh_token": "old_rt"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "new_at"
    assert "refresh_token" not in data


async def test_refresh_missing_field(route_client: AsyncClient):
    resp = await route_client.post("/auth/refresh", json={})
    assert resp.status_code == 400
    assert "Missing refresh_token" in resp.json()["detail"]


async def test_refresh_expired_token(route_client: AsyncClient):
    mock_resp = httpx.Response(400, json={"error": "invalid_grant"})
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _mock_httpx_client(mock_resp)
        resp = await route_client.post("/auth/refresh", json={"refresh_token": "expired_rt"})

    assert resp.status_code == 401
    assert "expired or revoked" in resp.json()["detail"].lower()


async def test_refresh_upstream_failure(route_client: AsyncClient):
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client
        resp = await route_client.post("/auth/refresh", json={"refresh_token": "some_rt"})

    assert resp.status_code == 502
    assert "Token refresh failed" in resp.json()["detail"]


# --- OAuth `state` (CSRF) tests ---
#
# RFC 6749 §10.12. Without `state`, an attacker can complete an authorization
# flow the victim's browser never started and have the victim's session bound
# to the attacker's identity. Every rejection case below must fail closed:
# no token exchange, no tokens in the response.


def _tracking_client(mock_resp):
    """httpx client stub that records whether a token exchange was attempted."""
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_login_authorization_url_includes_state(route_client: AsyncClient):
    resp = await route_client.get("/auth/login")
    params = parse_qs(urlparse(resp.headers["location"]).query)
    assert params["state"][0]


async def test_login_sets_state_cookie_binding_the_browser(route_client: AsyncClient):
    resp = await route_client.get("/auth/login")
    set_cookie = resp.headers.get("set-cookie", "")
    assert "errand_oauth_state=" in set_cookie
    # The nonce must not be readable by page scripts, and must expire.
    assert "httponly" in set_cookie.lower()
    assert "max-age" in set_cookie.lower()


async def test_callback_with_matching_state_proceeds(route_client: AsyncClient):
    state = await _begin_login(route_client)
    mock_resp = httpx.Response(200, json={"access_token": "at_123"})
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        client = _tracking_client(mock_resp)
        mock_client_cls.return_value = client
        resp = await route_client.get(f"/auth/callback?code=valid_code&state={state}")

    assert client.post.await_count == 1
    assert resp.status_code == 307
    assert "access_token=at_123" in resp.headers["location"]


async def test_callback_missing_state_is_rejected(route_client: AsyncClient):
    await _begin_login(route_client)
    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        client = _tracking_client(httpx.Response(200, json={"access_token": "at_123"}))
        mock_client_cls.return_value = client
        resp = await route_client.get("/auth/callback?code=valid_code")

    assert resp.status_code == 401
    # No permissive fallback: an absent state must fail, not warn and continue.
    assert client.post.await_count == 0
    assert "at_123" not in resp.text


async def test_callback_mismatched_state_is_rejected(route_client: AsyncClient):
    """State issued to a different browser: signature is valid, nonce is not ours."""
    await _begin_login(route_client)
    other = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False)
    async with other:
        foreign_state = await _begin_login(other)

    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        client = _tracking_client(httpx.Response(200, json={"access_token": "at_123"}))
        mock_client_cls.return_value = client
        resp = await route_client.get(f"/auth/callback?code=valid_code&state={foreign_state}")

    assert resp.status_code == 401
    assert client.post.await_count == 0


async def test_callback_forged_state_is_rejected(route_client: AsyncClient):
    """A state the backend never signed."""
    import jwt as pyjwt

    await _begin_login(route_client)
    forged = pyjwt.encode({"nonce": "whatever", "exp": 9999999999}, "not-the-secret", algorithm="HS256")

    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        client = _tracking_client(httpx.Response(200, json={"access_token": "at_123"}))
        mock_client_cls.return_value = client
        resp = await route_client.get(f"/auth/callback?code=valid_code&state={forged}")

    assert resp.status_code == 401
    assert client.post.await_count == 0


async def test_callback_expired_state_is_rejected(route_client: AsyncClient):
    """Correctly signed and matching the cookie, but past its expiry."""
    import jwt as pyjwt

    resp = await route_client.get("/auth/login")
    nonce = route_client.cookies["errand_oauth_state"]
    expired = pyjwt.encode(
        {"nonce": nonce, "exp": 1000000000}, TEST_SIGNING_SECRET, algorithm="HS256"
    )

    with patch("auth_routes.httpx.AsyncClient") as mock_client_cls:
        client = _tracking_client(httpx.Response(200, json={"access_token": "at_123"}))
        mock_client_cls.return_value = client
        resp = await route_client.get(f"/auth/callback?code=valid_code&state={expired}")

    assert resp.status_code == 401
    assert client.post.await_count == 0


async def test_rejected_callback_establishes_no_session(route_client: AsyncClient):
    await _begin_login(route_client)
    resp = await route_client.get("/auth/callback?code=valid_code&state=garbage")

    assert resp.status_code == 401
    assert "access_token" not in resp.text
    # Nothing that could be mistaken for a session is handed back.
    assert "location" not in resp.headers
