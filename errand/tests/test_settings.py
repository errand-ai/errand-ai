import logging
import os
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select

from main import generate_ssh_keypair
from models import Setting


# --- GET /api/settings ---


async def test_get_settings_empty(admin_client: AsyncClient):
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    # New format returns metadata-enriched settings from registry
    assert isinstance(data, dict)
    # Should have registry keys with metadata
    assert "system_prompt" in data
    assert "value" in data["system_prompt"]
    assert "source" in data["system_prompt"]


async def test_get_settings_non_admin(client: AsyncClient):
    resp = await client.get("/api/settings")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"


# --- PUT /api/settings ---


async def test_put_settings_create(admin_client: AsyncClient):
    resp = await admin_client.put(
        "/api/settings", json={"system_prompt": "You are a helpful assistant"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["system_prompt"]["value"] == "You are a helpful assistant"
    assert data["system_prompt"]["source"] == "database"


async def test_put_settings_update(admin_client: AsyncClient):
    await admin_client.put(
        "/api/settings", json={"system_prompt": "Original prompt"}
    )
    resp = await admin_client.put(
        "/api/settings", json={"system_prompt": "Updated prompt"}
    )
    assert resp.status_code == 200
    assert resp.json()["system_prompt"]["value"] == "Updated prompt"


async def test_put_settings_partial_preserves_other_keys(admin_client: AsyncClient):
    await admin_client.put(
        "/api/settings",
        json={"system_prompt": "My prompt", "mcp_servers": [{"name": "test"}]},
    )
    resp = await admin_client.put(
        "/api/settings", json={"system_prompt": "New prompt"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["system_prompt"]["value"] == "New prompt"
    assert data["mcp_servers"]["value"] == [{"name": "test"}]
    assert data["mcp_servers"]["source"] == "database"


async def test_put_settings_non_admin(client: AsyncClient):
    resp = await client.put(
        "/api/settings", json={"system_prompt": "Nope"}
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"


# --- Skills excluded from settings (managed via /api/skills) ---


async def test_get_settings_excludes_skills(admin_client: AsyncClient):
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    assert "skills" not in resp.json()


async def test_put_settings_ignores_skills(admin_client: AsyncClient):
    resp = await admin_client.put(
        "/api/settings",
        json={"skills": [{"name": "test"}], "system_prompt": "hello"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" not in data
    assert data["system_prompt"]["value"] == "hello"


# --- SSH keypair generation ---


def test_generate_ssh_keypair():
    private_pem, public_openssh = generate_ssh_keypair()
    assert private_pem.startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert public_openssh.startswith("ssh-ed25519 ")
    assert public_openssh.endswith(" errand")


def test_generate_ssh_keypair_unique():
    _, pub1 = generate_ssh_keypair()
    _, pub2 = generate_ssh_keypair()
    assert pub1 != pub2


# --- SSH private key excluded from GET /api/settings ---


async def test_get_settings_excludes_ssh_private_key(admin_client: AsyncClient):
    # Store both keys via PUT
    await admin_client.put(
        "/api/settings",
        json={"ssh_private_key": "PRIVATE", "ssh_public_key": "PUBLIC"},
    )
    resp = await admin_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "ssh_public_key" in data
    assert data["ssh_public_key"]["value"] == "PUBLIC"
    assert "ssh_private_key" not in data


# --- POST /api/settings/regenerate-ssh-key ---


async def test_regenerate_ssh_key(admin_client: AsyncClient):
    resp = await admin_client.post("/api/settings/regenerate-ssh-key")
    assert resp.status_code == 200
    data = resp.json()
    assert "ssh_public_key" in data
    assert data["ssh_public_key"].startswith("ssh-ed25519 ")
    # Verify the key is persisted
    resp2 = await admin_client.get("/api/settings")
    assert resp2.json()["ssh_public_key"]["value"] == data["ssh_public_key"]


async def test_regenerate_ssh_key_replaces_existing(admin_client: AsyncClient):
    resp1 = await admin_client.post("/api/settings/regenerate-ssh-key")
    key1 = resp1.json()["ssh_public_key"]
    resp2 = await admin_client.post("/api/settings/regenerate-ssh-key")
    key2 = resp2.json()["ssh_public_key"]
    assert key1 != key2


async def test_regenerate_ssh_key_non_admin(client: AsyncClient):
    resp = await client.post("/api/settings/regenerate-ssh-key")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"


# --- PUT /api/settings: env-shadowed (readonly) keys ---


async def test_put_settings_env_shadowed_key_is_refused(admin_client_with_session):
    """An env-sourced key is neither persisted nor reported as accepted."""
    client, session_maker = admin_client_with_session
    with patch.dict(os.environ, {"MAX_CONCURRENT_TASKS": "3"}):
        resp = await client.put("/api/settings", json={"max_concurrent_tasks": 9})

    assert resp.status_code == 200
    entry = resp.json()["max_concurrent_tasks"]
    assert entry["readonly"] is True
    assert entry["source"] == "env"
    assert entry["value"] == 3

    # No settings row was written, so unsetting the env var must not reveal a 9.
    async with session_maker() as session:
        result = await session.execute(
            select(Setting).where(Setting.key == "max_concurrent_tasks")
        )
        assert result.scalar_one_or_none() is None


async def test_put_settings_saves_editable_key_alongside_refused_key(
    admin_client_with_session,
):
    """A mixed body must not fail wholesale — cards PUT several keys at once."""
    client, session_maker = admin_client_with_session
    with patch.dict(os.environ, {"MAX_CONCURRENT_TASKS": "3"}):
        resp = await client.put(
            "/api/settings",
            json={"archive_after_days": 14, "max_concurrent_tasks": 9},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["archive_after_days"]["value"] == 14
    assert data["archive_after_days"]["source"] == "database"
    assert data["max_concurrent_tasks"]["readonly"] is True

    async with session_maker() as session:
        result = await session.execute(
            select(Setting).where(Setting.key == "archive_after_days")
        )
        assert result.scalar_one().value == 14


async def test_put_settings_logs_warning_per_refused_key(
    admin_client_with_session, caplog
):
    """The refusal must be findable in the logs, naming key and env var."""
    client, _ = admin_client_with_session
    with caplog.at_level(logging.WARNING, logger="main"):
        with patch.dict(os.environ, {"MAX_CONCURRENT_TASKS": "3"}):
            await client.put(
                "/api/settings",
                json={"archive_after_days": 14, "max_concurrent_tasks": 9},
            )

    refusals = [
        r for r in caplog.records
        if "max_concurrent_tasks" in r.getMessage()
        and "MAX_CONCURRENT_TASKS" in r.getMessage()
    ]
    assert len(refusals) == 1
    assert refusals[0].levelno == logging.WARNING
    # The editable key in the same body must not be reported as refused.
    assert not [
        r for r in caplog.records if "archive_after_days" in r.getMessage()
    ]
