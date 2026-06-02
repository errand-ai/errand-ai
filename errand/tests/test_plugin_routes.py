"""Smoke tests for /api/marketplaces and /api/plugins endpoints."""

import json
import uuid
from pathlib import Path


async def test_marketplace_list_empty_admin(admin_client):
    resp = await admin_client.get("/api/marketplaces")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_marketplace_list_non_admin_rejected(client):
    resp = await client.get("/api/marketplaces")
    assert resp.status_code == 403


async def test_marketplace_create_with_invalid_source_type(admin_client):
    resp = await admin_client.post("/api/marketplaces", json={
        "name": "x", "source_type": "ftp", "source_url": "ftp://example.com",
    })
    assert resp.status_code == 422


async def test_marketplace_create_and_delete_local(admin_client_with_session, tmp_path, monkeypatch):
    client, session_maker = admin_client_with_session
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "9hH-fpyt0HRP4_g-Tt2j6_FzJD9Vqz2vIo5SXmlAEHE=")
    src_root = tmp_path / "src"
    (src_root / ".claude-plugin").mkdir(parents=True)
    (src_root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({
        "name": "t", "plugins": [],
    }))

    resp = await client.post("/api/marketplaces", json={
        "name": "tmp1", "source_type": "local", "source_url": str(src_root),
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "tmp1"
    assert body["last_sync_status"] == "ok"
    mp_id = body["id"]

    resp = await client.delete(f"/api/marketplaces/{mp_id}")
    assert resp.status_code == 204


async def test_marketplace_duplicate_name_rejected(admin_client_with_session, tmp_path):
    client, _ = admin_client_with_session
    src_root = tmp_path / "src"
    (src_root / ".claude-plugin").mkdir(parents=True)
    (src_root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"name": "t", "plugins": []}))

    resp = await client.post("/api/marketplaces", json={
        "name": "dup", "source_type": "local", "source_url": str(src_root),
    })
    assert resp.status_code == 200
    resp = await client.post("/api/marketplaces", json={
        "name": "dup", "source_type": "local", "source_url": str(src_root),
    })
    assert resp.status_code == 409


async def test_predefined_marketplace_delete_refused(admin_client_with_session):
    client, session_maker = admin_client_with_session
    from models import Marketplace
    mp_id = uuid.uuid4()
    async with session_maker() as s:
        s.add(Marketplace(
            id=mp_id, name="anthropics/claude-plugins-official",
            source_type="github", source_url="anthropics/claude-plugins-official",
            enabled=False, predefined=True,
        ))
        await s.commit()
    resp = await client.delete(f"/api/marketplaces/{mp_id}")
    assert resp.status_code == 409


async def test_plugins_list_empty(admin_client):
    resp = await admin_client.get("/api/plugins")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_task_profile_accepts_enabled_plugins(admin_client_with_session):
    client, session_maker = admin_client_with_session
    pid = str(uuid.uuid4())
    resp = await client.post("/api/task-profiles", json={
        "name": "with-plugin", "enabled_plugins": [pid],
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["enabled_plugins"] == [pid]


async def test_task_profile_rejects_invalid_enabled_plugins(admin_client):
    resp = await admin_client.post("/api/task-profiles", json={
        "name": "bad-plugin", "enabled_plugins": ["not-a-uuid"],
    })
    assert resp.status_code == 422


async def test_settings_put_rejects_negative_poll_interval(admin_client):
    resp = await admin_client.put("/api/settings", json={
        "plugin_poll_interval_seconds": -1,
    })
    assert resp.status_code == 422


async def test_settings_put_accepts_zero_poll_interval(admin_client):
    resp = await admin_client.put("/api/settings", json={
        "plugin_poll_interval_seconds": 0,
    })
    assert resp.status_code == 200


async def test_settings_put_accepts_non_negative_poll_interval(admin_client):
    resp = await admin_client.put("/api/settings", json={
        "plugin_poll_interval_seconds": 3600,
    })
    assert resp.status_code == 200
