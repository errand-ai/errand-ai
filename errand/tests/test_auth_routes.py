from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from main import app

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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as ac:
        yield ac


async def test_login_redirect_includes_offline_access(route_client: AsyncClient):
    resp = await route_client.get("/auth/login")
    assert resp.status_code == 307
    location = resp.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert "openid" in params["scope"][0]
    assert "offline_access" in params["scope"][0]


async def test_callback_includes_refresh_token_in_fragment(route_client: AsyncClient):
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

        resp = await route_client.get("/auth/callback?code=valid_code")

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "access_token=at_123" in location
    assert "id_token=id_456" in location
    assert "refresh_token=rt_789" in location


async def test_callback_omits_refresh_token_when_absent(route_client: AsyncClient):
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

        resp = await route_client.get("/auth/callback?code=valid_code")

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
