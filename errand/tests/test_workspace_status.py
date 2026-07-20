"""Tests for the shared-workspace status/health endpoints.

  * POST /api/workspace/health — gateway-only (workspace bearer) health ingest.
  * GET  /api/workspace/status — admin read-only config + latest health.
"""

import json

import pytest

import workspace_refresh_auth as wra


@pytest.mark.anyio
async def test_health_requires_workspace_bearer(admin_client_with_session, fake_valkey):
    client, _ = admin_client_with_session
    resp = await client.post("/api/workspace/health", json={"auth_state": "ok"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_health_rejects_unknown_bearer(admin_client_with_session, fake_valkey):
    client, _ = admin_client_with_session
    resp = await client.post(
        "/api/workspace/health",
        json={"auth_state": "ok"},
        headers={"Authorization": "Bearer nope"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_health_ingest_and_status_roundtrip(admin_client_with_session, fake_valkey, monkeypatch):
    client, _ = admin_client_with_session
    bearer = await wra.issue_workspace_bearer(fake_valkey)

    # Gateway reports health with its workspace bearer.
    resp = await client.post(
        "/api/workspace/health",
        json={"auth_state": "ok", "pending_uploads": 2, "last_refresh_ok": True},
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert resp.status_code == 200

    # Stored in Valkey under the health key.
    raw = await fake_valkey.get("workspace_gateway_health")
    assert raw is not None
    stored = json.loads(raw)
    assert stored["auth_state"] == "ok"
    assert "reported_at" in stored

    # Admin status surfaces config + the reported health.
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_PROVIDER", "google_drive")
    monkeypatch.setenv("WORKSPACE_FOLDER", "Errand")
    status = await client.get("/api/workspace/status")
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["provider"] == "google_drive"
    assert body["folder"] == "Errand"
    assert body["health"]["auth_state"] == "ok"
    assert body["health"]["pending_uploads"] == 2


@pytest.mark.anyio
async def test_status_disabled_when_not_configured(admin_client_with_session, fake_valkey, monkeypatch):
    client, _ = admin_client_with_session
    monkeypatch.delenv("WORKSPACE_ENABLED", raising=False)
    # Even if provider/folder env defaults are present (as in compose), a disabled
    # workspace must not report them — that would be a contradictory status.
    monkeypatch.setenv("WORKSPACE_PROVIDER", "google_drive")
    monkeypatch.setenv("WORKSPACE_FOLDER", "Errand")
    resp = await client.get("/api/workspace/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["provider"] is None
    assert body["folder"] is None
    assert body["health"] is None


@pytest.mark.anyio
async def test_status_health_none_when_gateway_silent(admin_client_with_session, fake_valkey, monkeypatch):
    """Config present but no recent gateway report → health is None (degraded)."""
    client, _ = admin_client_with_session
    monkeypatch.setenv("WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_PROVIDER", "onedrive")
    resp = await client.get("/api/workspace/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["provider"] == "onedrive"
    assert body["health"] is None
