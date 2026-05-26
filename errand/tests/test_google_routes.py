"""Tests for the Google Workspace HTTP routes.

Covers `POST /api/google/refresh-token` — the mid-task refresh endpoint
exercised by task-runner pods when they observe an UNAUTHENTICATED response.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import Response
from sqlalchemy import select

from models import PlatformCredential, Setting
from platforms.credentials import encrypt, decrypt


_MCP_KEY = "mcp-key-for-tests"


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")


def _make_credentials(expires_in: int = 3600) -> dict:
    return {
        "access_token": "old-access-token",
        "refresh_token": "refresh-token-value",
        "expires_at": int(time.time()) + expires_in,
        "token_type": "Bearer",
        "user_email": "user@example.com",
        "user_name": "Test User",
    }


async def _seed_mcp_key(session_maker) -> None:
    async with session_maker() as session:
        session.add(Setting(key="mcp_api_key", value=_MCP_KEY))
        await session.commit()


async def _seed_google_credentials(session_maker, creds: dict) -> None:
    async with session_maker() as session:
        session.add(PlatformCredential(
            platform_id="google_drive",
            encrypted_data=encrypt(creds),
            status="connected",
        ))
        await session.commit()


@pytest.mark.anyio
async def test_refresh_unauthorised_without_bearer(admin_client_with_session):
    client, session_maker = admin_client_with_session
    await _seed_mcp_key(session_maker)
    await _seed_google_credentials(session_maker, _make_credentials())

    resp = await client.post("/api/google/refresh-token")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_unauthorised_with_wrong_bearer(admin_client_with_session):
    client, session_maker = admin_client_with_session
    await _seed_mcp_key(session_maker)
    await _seed_google_credentials(session_maker, _make_credentials())

    resp = await client.post(
        "/api/google/refresh-token",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_returns_404_when_no_google_credentials(admin_client_with_session):
    client, session_maker = admin_client_with_session
    await _seed_mcp_key(session_maker)
    # No Google credentials seeded.

    resp = await client.post(
        "/api/google/refresh-token",
        headers={"Authorization": f"Bearer {_MCP_KEY}"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_refresh_returns_502_on_upstream_failure(admin_client_with_session):
    client, session_maker = admin_client_with_session
    await _seed_mcp_key(session_maker)
    await _seed_google_credentials(session_maker, _make_credentials())

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(400, json={"error": "invalid_grant"})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/google/refresh-token",
            headers={"Authorization": f"Bearer {_MCP_KEY}"},
        )

    assert resp.status_code == 502

    # Original credential not mutated.
    async with session_maker() as session:
        row = await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == "google_drive")
        )
        stored = decrypt(row.scalar_one().encrypted_data)
        assert stored["access_token"] == "old-access-token"


@pytest.mark.anyio
async def test_refresh_happy_path_returns_new_token_and_persists(admin_client_with_session):
    client, session_maker = admin_client_with_session
    await _seed_mcp_key(session_maker)
    # Credential has plenty of life left — force-refresh should ignore the buffer.
    await _seed_google_credentials(session_maker, _make_credentials(expires_in=3600))

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(200, json={
        "access_token": "shiny-new-token",
        "expires_in": 3600,
    })
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/google/refresh-token",
            headers={"Authorization": f"Bearer {_MCP_KEY}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "shiny-new-token"
    assert isinstance(body["expires_at"], int)
    assert body["expires_at"] > int(time.time())

    # Persisted in DB.
    async with session_maker() as session:
        row = await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == "google_drive")
        )
        stored = decrypt(row.scalar_one().encrypted_data)
        assert stored["access_token"] == "shiny-new-token"
