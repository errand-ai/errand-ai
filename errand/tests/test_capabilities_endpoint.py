"""Tests for GET /api/capabilities (server capability advertisement)."""
import pytest

# Wave 1 settings cards gate on these snake_case keys.
WAVE1_ALWAYS_ON = [
    "system_prompt",
    "mcp_servers",
    "skills_git_repo",
    "task_management",
    "telemetry",
]

# Wave 2 settings cards gate on these snake_case keys (all always-on;
# google_workspace is conditional and tested separately).
WAVE2_ALWAYS_ON = [
    "llm_providers",
    "llm_models",
    "platforms",
    "task_profiles",
]


@pytest.fixture(autouse=True)
def _clean_conditional_env(monkeypatch):
    """Ensure env-gated conditional capabilities start disabled for each test."""
    monkeypatch.delenv("ONEDRIVE_MCP_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)


@pytest.mark.asyncio
async def test_capabilities_public_and_always_on(unauth_client):
    """Endpoint is public and always advertises the Wave 1 keys in snake_case."""
    resp = await unauth_client.get("/api/capabilities")

    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    caps = data["capabilities"]
    for key in WAVE1_ALWAYS_ON + WAVE2_ALWAYS_ON:
        assert key in caps
    # The endpoint returns the same set as cloud registration; Wave 1 keys are
    # snake_case, so the legacy kebab spelling must not appear.
    assert "mcp-servers" not in caps


class _FakeRegistry:
    """Minimal platform registry stub: reports the given platform ids as registered."""

    def __init__(self, registered: set[str] | None = None):
        self._registered = registered or set()

    def get(self, platform_id: str):
        return object() if platform_id in self._registered else None


@pytest.mark.asyncio
async def test_conditional_capabilities_omitted_when_disabled(unauth_client, monkeypatch):
    """cloud_storage, litellm_mcp and jira are absent when their features are off."""
    import platforms

    monkeypatch.setattr(platforms, "get_registry", _FakeRegistry)

    resp = await unauth_client.get("/api/capabilities")
    caps = resp.json()["capabilities"]

    assert "cloud_storage" not in caps
    assert "litellm_mcp" not in caps
    assert "jira" not in caps
    assert "google_workspace" not in caps


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


@pytest.mark.asyncio
async def test_google_workspace_advertised_when_oauth_configured(unauth_client, monkeypatch):
    """google_workspace is advertised when Google OAuth client credentials are set."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")

    resp = await unauth_client.get("/api/capabilities")
    caps = resp.json()["capabilities"]

    assert "google_workspace" in caps


@pytest.mark.asyncio
async def test_jira_advertised_when_registered(unauth_client, monkeypatch):
    """jira is advertised when the Jira platform integration is registered."""
    import platforms

    monkeypatch.setattr(platforms, "get_registry", lambda: _FakeRegistry({"jira"}))

    resp = await unauth_client.get("/api/capabilities")
    caps = resp.json()["capabilities"]

    assert "jira" in caps
