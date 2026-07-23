"""Tests for the OneDrive HTTP routes.

Covers `POST /api/onedrive/refresh-token` — the mid-task / gateway refresh
endpoint, the OneDrive parallel of the Google refresh endpoint. It authenticates
against either a task-scoped bearer stored under `onedrive_refresh_token:<bearer>`
or the workspace-scoped gateway bearer. These tests seed those keys via the
`fake_valkey` fixture and confirm auth behaviour, the happy path, and structured
error responses.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import Response
from sqlalchemy import select

from models import PlatformCredential
from platforms.credentials import encrypt, decrypt


_TASK_ID = "task-onedrive-1"
_VALID_BEARER = "onedrive-task-bearer"


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    # Configure local Microsoft client creds so refresh takes the direct path.
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")


def _make_credentials(expires_in: int = 3600) -> dict:
    return {
        "access_token": "old-onedrive-token",
        "refresh_token": "onedrive-refresh-value",
        "expires_at": int(time.time()) + expires_in,
        "token_type": "Bearer",
    }


async def _seed_task_bearer(fake_valkey, bearer: str = _VALID_BEARER, task_id: str = _TASK_ID) -> None:
    await fake_valkey.set(f"onedrive_refresh_token:{bearer}", task_id, ex=28800)


async def _seed_onedrive_credentials(session_maker, creds: dict) -> None:
    async with session_maker() as session:
        session.add(PlatformCredential(
            platform_id="onedrive",
            encrypted_data=encrypt(creds),
            status="connected",
        ))
        await session.commit()


@pytest.mark.anyio
async def test_refresh_unauthorised_without_bearer(admin_client_with_session, fake_valkey):
    client, session_maker = admin_client_with_session
    await _seed_task_bearer(fake_valkey)
    await _seed_onedrive_credentials(session_maker, _make_credentials())

    resp = await client.post("/api/onedrive/refresh-token")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_unauthorised_with_wrong_bearer(admin_client_with_session, fake_valkey):
    client, session_maker = admin_client_with_session
    await _seed_task_bearer(fake_valkey)
    await _seed_onedrive_credentials(session_maker, _make_credentials())

    resp = await client.post(
        "/api/onedrive/refresh-token",
        headers={"Authorization": "Bearer not-the-stored-token"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_rejects_mcp_api_key(admin_client_with_session, fake_valkey):
    """The global mcp_api_key MUST NOT authenticate this endpoint."""
    from models import Setting

    client, session_maker = admin_client_with_session
    async with session_maker() as session:
        session.add(Setting(key="mcp_api_key", value="some-mcp-key"))
        await session.commit()
    await _seed_onedrive_credentials(session_maker, _make_credentials())

    resp = await client.post(
        "/api/onedrive/refresh-token",
        headers={"Authorization": "Bearer some-mcp-key"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_returns_404_when_no_onedrive_credentials(admin_client_with_session, fake_valkey):
    client, _ = admin_client_with_session
    await _seed_task_bearer(fake_valkey)

    resp = await client.post(
        "/api/onedrive/refresh-token",
        headers={"Authorization": f"Bearer {_VALID_BEARER}"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_refresh_returns_502_on_upstream_failure(admin_client_with_session, fake_valkey):
    """Relay/upstream failure surfaces as a structured 502, not a silent success."""
    client, session_maker = admin_client_with_session
    await _seed_task_bearer(fake_valkey)
    await _seed_onedrive_credentials(session_maker, _make_credentials())

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(400, json={"error": "invalid_grant"})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/onedrive/refresh-token",
            headers={"Authorization": f"Bearer {_VALID_BEARER}"},
        )

    assert resp.status_code == 502
    assert "detail" in resp.json()

    # Original credential not mutated.
    async with session_maker() as session:
        row = await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == "onedrive")
        )
        stored = decrypt(row.scalar_one().encrypted_data)
        assert stored["access_token"] == "old-onedrive-token"


@pytest.mark.anyio
async def test_refresh_happy_path_returns_new_token_and_persists(admin_client_with_session, fake_valkey):
    client, session_maker = admin_client_with_session
    await _seed_task_bearer(fake_valkey)
    await _seed_onedrive_credentials(session_maker, _make_credentials(expires_in=3600))

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(200, json={
        "access_token": "shiny-onedrive-token",
        "expires_in": 3600,
    })
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/onedrive/refresh-token",
            headers={"Authorization": f"Bearer {_VALID_BEARER}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "shiny-onedrive-token"
    assert isinstance(body["expires_at"], int)
    assert body["expires_at"] > int(time.time())

    async with session_maker() as session:
        row = await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == "onedrive")
        )
        stored = decrypt(row.scalar_one().encrypted_data)
        assert stored["access_token"] == "shiny-onedrive-token"
