import logging
import os
from unittest.mock import patch

import pytest
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


async def test_max_concurrent_tasks_is_editable_when_env_unset(
    admin_client_with_session,
):
    """The default-install half of the helm-deployment scenario.

    With no MAX_CONCURRENT_TASKS in the environment — which is what a default
    chart render now produces — the key must be writable and report itself as
    such, so the settings UI renders it editable.
    """
    client, _ = admin_client_with_session
    env = {k: v for k, v in os.environ.items() if k != "MAX_CONCURRENT_TASKS"}
    with patch.dict(os.environ, env, clear=True):
        before = (await client.get("/api/settings")).json()["max_concurrent_tasks"]
        assert before["readonly"] is False, before

        resp = await client.put("/api/settings", json={"max_concurrent_tasks": 7})
        assert resp.status_code == 200
        after = resp.json()["max_concurrent_tasks"]

    assert after["value"] == 7
    assert after["source"] == "database"
    assert after["readonly"] is False


# --- Deployment default agent limits: max_turns / reasoning_effort ---


def _env_without(*names):
    return {k: v for k, v in os.environ.items() if k not in names}


async def test_agent_defaults_resolve_to_registry_defaults(admin_client_with_session):
    client, _ = admin_client_with_session
    with patch.dict(os.environ, _env_without("MAX_TURNS", "REASONING_EFFORT"), clear=True):
        data = (await client.get("/api/settings")).json()

    assert data["max_turns"]["value"] == 200
    assert data["max_turns"]["source"] == "default"
    assert data["reasoning_effort"]["value"] == "medium"
    assert data["reasoning_effort"]["source"] == "default"


async def test_agent_defaults_are_editable(admin_client_with_session):
    client, _ = admin_client_with_session
    with patch.dict(os.environ, _env_without("MAX_TURNS", "REASONING_EFFORT"), clear=True):
        resp = await client.put(
            "/api/settings", json={"max_turns": 50, "reasoning_effort": "high"}
        )
        data = (await client.get("/api/settings")).json()

    assert resp.status_code == 200
    for key, value in (("max_turns", 50), ("reasoning_effort", "high")):
        assert data[key]["value"] == value
        assert data[key]["source"] == "database"
        assert data[key]["readonly"] is False


async def test_max_turns_env_locks_the_value(admin_client_with_session):
    client, session_maker = admin_client_with_session
    with patch.dict(os.environ, {"MAX_TURNS": "300"}):
        resp = await client.put("/api/settings", json={"max_turns": 50})

    entry = resp.json()["max_turns"]
    assert entry == {**entry, "value": 300, "source": "env", "readonly": True}
    async with session_maker() as session:
        row = (await session.execute(select(Setting).where(Setting.key == "max_turns"))).scalar_one_or_none()
        assert row is None


@pytest.mark.parametrize("value", [0, -1, "ten", True, 1.5])
async def test_invalid_max_turns_rejected(admin_client_with_session, value):
    client, session_maker = admin_client_with_session
    resp = await client.put("/api/settings", json={"max_turns": value})

    assert resp.status_code == 422
    async with session_maker() as session:
        row = (await session.execute(select(Setting).where(Setting.key == "max_turns"))).scalar_one_or_none()
        assert row is None


@pytest.mark.parametrize("value", ["extreme", "HIGH", "", 3])
async def test_invalid_reasoning_effort_rejected(admin_client, value):
    resp = await admin_client.put("/api/settings", json={"reasoning_effort": value})
    assert resp.status_code == 422


async def test_null_clears_stored_override(admin_client_with_session):
    client, session_maker = admin_client_with_session
    with patch.dict(os.environ, _env_without("MAX_TURNS", "REASONING_EFFORT"), clear=True):
        await client.put("/api/settings", json={"max_turns": 50, "reasoning_effort": "low"})
        resp = await client.put(
            "/api/settings", json={"max_turns": None, "reasoning_effort": None}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["max_turns"]["value"] == 200
    assert data["max_turns"]["source"] == "default"
    assert data["reasoning_effort"]["value"] == "medium"
    assert data["reasoning_effort"]["source"] == "default"
    async with session_maker() as session:
        rows = (await session.execute(
            select(Setting).where(Setting.key.in_(["max_turns", "reasoning_effort"]))
        )).scalars().all()
        assert rows == []


async def test_null_for_env_sourced_key_is_refused(admin_client_with_session):
    client, _ = admin_client_with_session
    with patch.dict(os.environ, {"REASONING_EFFORT": "high"}):
        resp = await client.put("/api/settings", json={"reasoning_effort": None})

    assert resp.status_code == 200
    entry = resp.json()["reasoning_effort"]
    assert entry["value"] == "high"
    assert entry["source"] == "env"
    assert entry["readonly"] is True


# --- task_runner_log_level / timezone validation ---


async def test_log_level_and_timezone_valid_values_stored(admin_client):
    resp = await admin_client.put(
        "/api/settings",
        json={"task_runner_log_level": "DEBUG", "timezone": "Europe/London"},
    )

    assert resp.status_code == 200
    data = (await admin_client.get("/api/settings")).json()
    assert data["task_runner_log_level"]["value"] == "DEBUG"
    # Also guards the image: a missing tz database would reject this zone.
    assert data["timezone"]["value"] == "Europe/London"


@pytest.mark.parametrize("value", ["TRACE", "debug", None])
async def test_unknown_log_level_rejected(admin_client, value):
    resp = await admin_client.put("/api/settings", json={"task_runner_log_level": value})
    assert resp.status_code == 422


@pytest.mark.parametrize("value", ["Mars/Olympus", "", "../etc/passwd", None, 5])
async def test_unknown_timezone_rejected(admin_client, value):
    resp = await admin_client.put("/api/settings", json={"timezone": value})
    assert resp.status_code == 422


# --- GET /api/worker/defaults ---


async def test_worker_defaults_when_nothing_configured(admin_client):
    with patch.dict(os.environ, _env_without("MAX_TURNS", "REASONING_EFFORT"), clear=True):
        resp = await admin_client.get("/api/worker/defaults")

    assert resp.status_code == 200
    assert resp.json() == {"max_turns": "200", "reasoning_effort": "medium"}


async def test_worker_defaults_report_database_value(admin_client):
    with patch.dict(os.environ, _env_without("MAX_TURNS", "REASONING_EFFORT"), clear=True):
        await admin_client.put("/api/settings", json={"max_turns": 75})
        resp = await admin_client.get("/api/worker/defaults")

    assert resp.json()["max_turns"] == "75"


async def test_worker_defaults_report_env_value(admin_client):
    await admin_client.put("/api/settings", json={"reasoning_effort": "low"})
    with patch.dict(os.environ, {"REASONING_EFFORT": "high"}):
        resp = await admin_client.get("/api/worker/defaults")

    assert resp.json()["reasoning_effort"] == "high"


async def test_invalid_env_value_echoed_back_does_not_block_other_keys(admin_client_with_session):
    """Env values are never validated, so a client echoing one back must not 422
    the whole save; the env-sourced key is refused and the others are stored."""
    client, _ = admin_client_with_session
    with patch.dict(os.environ, {"REASONING_EFFORT": "High"}):
        resp = await client.put(
            "/api/settings", json={"reasoning_effort": "High", "archive_after_days": 9}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["archive_after_days"]["value"] == 9
    assert data["reasoning_effort"]["readonly"] is True
