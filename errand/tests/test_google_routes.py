"""Tests for the Google Workspace HTTP routes.

Covers `POST /api/google/refresh-token` — the mid-task refresh endpoint
exercised by task-runner pods when they observe an UNAUTHENTICATED response.

The endpoint authenticates against a *task-scoped* bearer token stored in
Valkey under `google_refresh_token:<bearer>` → `<task_id>`. These tests
seed that key directly via the `fake_valkey` fixture and confirm a valid
bearer succeeds, a missing/wrong bearer is rejected, and the underlying
Valkey lookup is required.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import Response
from sqlalchemy import select

from models import PlatformCredential
from platforms.credentials import encrypt, decrypt


_TASK_ID = "task-abcdef"
_VALID_BEARER = "task-scoped-refresh-bearer"


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


async def _seed_refresh_bearer(fake_valkey, bearer: str = _VALID_BEARER, task_id: str = _TASK_ID) -> None:
    await fake_valkey.set(f"google_refresh_token:{bearer}", task_id, ex=28800)


async def _seed_google_credentials(session_maker, creds: dict) -> None:
    async with session_maker() as session:
        session.add(PlatformCredential(
            platform_id="google_drive",
            encrypted_data=encrypt(creds),
            status="connected",
        ))
        await session.commit()


@pytest.mark.anyio
async def test_refresh_unauthorised_without_bearer(admin_client_with_session, fake_valkey):
    client, session_maker = admin_client_with_session
    await _seed_refresh_bearer(fake_valkey)
    await _seed_google_credentials(session_maker, _make_credentials())

    resp = await client.post("/api/google/refresh-token")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_unauthorised_with_wrong_bearer(admin_client_with_session, fake_valkey):
    client, session_maker = admin_client_with_session
    await _seed_refresh_bearer(fake_valkey)
    await _seed_google_credentials(session_maker, _make_credentials())

    resp = await client.post(
        "/api/google/refresh-token",
        headers={"Authorization": "Bearer not-the-stored-token"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_rejects_mcp_api_key(admin_client_with_session, fake_valkey):
    """The global mcp_api_key MUST NOT authenticate this endpoint; only the
    per-task `google_refresh_token:<bearer>` bearer does."""
    from models import Setting

    client, session_maker = admin_client_with_session
    # No matching google_refresh_token in Valkey.
    async with session_maker() as session:
        session.add(Setting(key="mcp_api_key", value="some-mcp-key"))
        await session.commit()
    await _seed_google_credentials(session_maker, _make_credentials())

    resp = await client.post(
        "/api/google/refresh-token",
        headers={"Authorization": "Bearer some-mcp-key"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_refresh_returns_404_when_no_google_credentials(admin_client_with_session, fake_valkey):
    client, _ = admin_client_with_session
    await _seed_refresh_bearer(fake_valkey)
    # No Google credentials seeded.

    resp = await client.post(
        "/api/google/refresh-token",
        headers={"Authorization": f"Bearer {_VALID_BEARER}"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_refresh_returns_502_on_upstream_failure(admin_client_with_session, fake_valkey):
    client, session_maker = admin_client_with_session
    await _seed_refresh_bearer(fake_valkey)
    await _seed_google_credentials(session_maker, _make_credentials())

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(400, json={"error": "invalid_grant"})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cloud_storage.httpx.AsyncClient", return_value=mock_client):
        resp = await client.post(
            "/api/google/refresh-token",
            headers={"Authorization": f"Bearer {_VALID_BEARER}"},
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
async def test_refresh_happy_path_returns_new_token_and_persists(admin_client_with_session, fake_valkey):
    client, session_maker = admin_client_with_session
    await _seed_refresh_bearer(fake_valkey)
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
            headers={"Authorization": f"Bearer {_VALID_BEARER}"},
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
