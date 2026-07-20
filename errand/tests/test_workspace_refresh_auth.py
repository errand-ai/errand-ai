"""Tests for the workspace-scoped refresh bearer (`workspace_refresh_auth`).

Two layers:
  * unit tests for issue / renew / invalidate / invalidate_all / resolve helpers
    against the `fake_valkey` fixture;
  * integration tests confirming the workspace bearer is accepted on BOTH cloud
    refresh endpoints and rejected on a non-refresh (admin) endpoint — i.e. it is
    usable only for token refresh, never as a general credential.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import Response

from models import PlatformCredential
from platforms.credentials import encrypt
import workspace_refresh_auth as wra


# --------------------------------------------------------------------------- #
# Unit tests: bearer lifecycle helpers
# --------------------------------------------------------------------------- #

@pytest.mark.anyio
async def test_issue_and_resolve_workspace_bearer(fake_valkey):
    bearer = await wra.issue_workspace_bearer(fake_valkey)
    assert bearer
    # Stored under the workspace prefix.
    assert await fake_valkey.get(f"{wra.WORKSPACE_BEARER_KEY_PREFIX}{bearer}") == "workspace"
    # Resolves as the workspace caller on any refresh endpoint prefix.
    caller = await wra.resolve_refresh_caller(fake_valkey, bearer, wra.GOOGLE_TASK_BEARER_PREFIX)
    assert caller == "workspace"


@pytest.mark.anyio
async def test_resolve_prefers_task_bearer_when_not_workspace(fake_valkey):
    await fake_valkey.set(f"{wra.ONEDRIVE_TASK_BEARER_PREFIX}tb", "task-77", ex=60)
    caller = await wra.resolve_refresh_caller(fake_valkey, "tb", wra.ONEDRIVE_TASK_BEARER_PREFIX)
    assert caller == "task-77"


@pytest.mark.anyio
async def test_resolve_unknown_bearer_returns_none(fake_valkey):
    assert await wra.resolve_refresh_caller(fake_valkey, "nope", wra.GOOGLE_TASK_BEARER_PREFIX) is None


@pytest.mark.anyio
async def test_renew_extends_ttl(fake_valkey):
    bearer = await wra.issue_workspace_bearer(fake_valkey, ttl=100)
    key = f"{wra.WORKSPACE_BEARER_KEY_PREFIX}{bearer}"
    assert await fake_valkey.ttl(key) <= 100
    assert await wra.renew_workspace_bearer(fake_valkey, bearer, ttl=5000) is True
    assert await fake_valkey.ttl(key) > 100


@pytest.mark.anyio
async def test_renew_missing_bearer_returns_false(fake_valkey):
    assert await wra.renew_workspace_bearer(fake_valkey, "ghost") is False


@pytest.mark.anyio
async def test_resolve_renews_workspace_bearer_ttl(fake_valkey):
    bearer = await wra.issue_workspace_bearer(fake_valkey, ttl=100)
    key = f"{wra.WORKSPACE_BEARER_KEY_PREFIX}{bearer}"
    await wra.resolve_refresh_caller(fake_valkey, bearer, wra.GOOGLE_TASK_BEARER_PREFIX)
    # TTL bumped back up to the default on use.
    assert await fake_valkey.ttl(key) > 100


@pytest.mark.anyio
async def test_register_operator_supplied_bearer(fake_valkey):
    await wra.register_workspace_bearer(fake_valkey, "operator-value")
    caller = await wra.resolve_refresh_caller(fake_valkey, "operator-value", wra.GOOGLE_TASK_BEARER_PREFIX)
    assert caller == "workspace"


@pytest.mark.anyio
async def test_invalidate_single_bearer(fake_valkey):
    bearer = await wra.issue_workspace_bearer(fake_valkey)
    await wra.invalidate_workspace_bearer(fake_valkey, bearer)
    assert await fake_valkey.get(f"{wra.WORKSPACE_BEARER_KEY_PREFIX}{bearer}") is None


@pytest.mark.anyio
async def test_invalidate_all_bearers(fake_valkey):
    b1 = await wra.issue_workspace_bearer(fake_valkey)
    b2 = await wra.issue_workspace_bearer(fake_valkey)
    removed = await wra.invalidate_all_workspace_bearers(fake_valkey)
    assert removed == 2
    assert await fake_valkey.get(f"{wra.WORKSPACE_BEARER_KEY_PREFIX}{b1}") is None
    assert await fake_valkey.get(f"{wra.WORKSPACE_BEARER_KEY_PREFIX}{b2}") is None


# --------------------------------------------------------------------------- #
# Integration: accepted on refresh endpoints, rejected elsewhere
# --------------------------------------------------------------------------- #

@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")


def _creds() -> dict:
    return {
        "access_token": "old",
        "refresh_token": "r",
        "expires_at": int(time.time()) + 3600,
        "token_type": "Bearer",
    }


def _mock_httpx(new_token: str):
    mock_client = AsyncMock()
    mock_client.post.return_value = Response(200, json={"access_token": new_token, "expires_in": 3600})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def _seed_cred(session_maker, provider: str) -> None:
    async with session_maker() as session:
        session.add(PlatformCredential(
            platform_id=provider, encrypted_data=encrypt(_creds()), status="connected",
        ))
        await session.commit()


@pytest.mark.anyio
async def test_workspace_bearer_accepted_on_google_endpoint(admin_client_with_session, fake_valkey, _env):
    client, session_maker = admin_client_with_session
    bearer = await wra.issue_workspace_bearer(fake_valkey)
    await _seed_cred(session_maker, "google_drive")

    with patch("cloud_storage.httpx.AsyncClient", return_value=_mock_httpx("g-new")):
        resp = await client.post(
            "/api/google/refresh-token",
            headers={"Authorization": f"Bearer {bearer}"},
        )
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "g-new"


@pytest.mark.anyio
async def test_workspace_bearer_accepted_on_onedrive_endpoint(admin_client_with_session, fake_valkey, _env):
    client, session_maker = admin_client_with_session
    bearer = await wra.issue_workspace_bearer(fake_valkey)
    await _seed_cred(session_maker, "onedrive")

    with patch("cloud_storage.httpx.AsyncClient", return_value=_mock_httpx("od-new")):
        resp = await client.post(
            "/api/onedrive/refresh-token",
            headers={"Authorization": f"Bearer {bearer}"},
        )
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "od-new"


@pytest.mark.anyio
async def test_workspace_bearer_rejected_on_non_refresh_endpoint(unauth_client, fake_valkey, _env):
    """The workspace bearer must NOT authorize a general (admin) endpoint."""
    bearer = await wra.issue_workspace_bearer(fake_valkey)
    resp = await unauth_client.get(
        "/api/task-profiles",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert resp.status_code in (401, 403)
