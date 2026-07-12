"""Tests for GET /api/capabilities (settings-UI capability advertisement)."""
import pytest

from capabilities import UI_ALWAYS_ON_CAPABILITIES


@pytest.fixture(autouse=True)
def _clean_conditional_env(monkeypatch):
    """Ensure env-gated conditional capabilities start disabled for each test."""
    monkeypatch.delenv("ONEDRIVE_MCP_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


@pytest.mark.asyncio
async def test_capabilities_public_and_always_on(unauth_client):
    """Endpoint is public and always advertises the five always-on Wave 1 keys."""
    resp = await unauth_client.get("/api/capabilities")

    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    caps = data["capabilities"]
    for key in UI_ALWAYS_ON_CAPABILITIES:
        assert key in caps
    # Sanity: the always-on set is exactly these five keys.
    assert set(UI_ALWAYS_ON_CAPABILITIES) == {
        "system_prompt",
        "mcp_servers",
        "skills_git_repo",
        "task_management",
        "telemetry",
    }


@pytest.mark.asyncio
async def test_conditional_capabilities_omitted_when_disabled(unauth_client):
    """cloud_storage and litellm_mcp are absent when their features are off."""
    resp = await unauth_client.get("/api/capabilities")
    caps = resp.json()["capabilities"]

    assert "cloud_storage" not in caps
    assert "litellm_mcp" not in caps


@pytest.mark.asyncio
async def test_cloud_storage_advertised_when_onedrive_configured(unauth_client, monkeypatch):
    """cloud_storage is advertised when the OneDrive MCP URL is configured."""
    monkeypatch.setenv("ONEDRIVE_MCP_URL", "https://onedrive.example/mcp")

    resp = await unauth_client.get("/api/capabilities")
    caps = resp.json()["capabilities"]

    assert "cloud_storage" in caps


@pytest.mark.asyncio
async def test_litellm_mcp_advertised_when_proxy_detected(unauth_client, monkeypatch):
    """litellm_mcp is advertised when a LiteLLM proxy is detected (legacy env var)."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://litellm.example")

    resp = await unauth_client.get("/api/capabilities")
    caps = resp.json()["capabilities"]

    assert "litellm_mcp" in caps
