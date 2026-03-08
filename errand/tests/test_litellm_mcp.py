"""Tests for GET /api/litellm/mcp-servers discovery endpoint."""

from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest
from httpx import AsyncClient


# --- Helpers ---

def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


async def _create_litellm_provider(admin_client: AsyncClient, base_url: str = "https://litellm.example.com", api_key: str = "test-key") -> dict:
    """Create a LiteLLM provider via API for testing."""
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="litellm"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": "litellm-test",
            "base_url": base_url,
            "api_key": api_key,
        })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Set CREDENTIAL_ENCRYPTION_KEY for provider creation."""
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "_26HOOIDUcxDH7fkoqI39DZulVPVK-hZe5THhiVLxIs=")


SAMPLE_SERVERS = [
    {
        "alias": "argocd",
        "server_name": "argocd-mcp",
        "description": "DevOps ArgoCD",
        "env": {"ARGOCD_TOKEN": "secret123"},
        "credentials": {"token": "xyz"},
        "command": "/usr/bin/argocd",
        "args": ["--server"],
        "static_headers": {"X-Custom": "val"},
        "authorization_url": "https://auth.example.com",
        "token_url": "https://token.example.com",
        "registration_url": "https://reg.example.com",
        "extra_headers": {"X-Extra": "val"},
    },
    {
        "alias": "perplexity",
        "server_name": "perplexity-mcp",
        "description": "Perplexity Search",
    },
]

SAMPLE_TOOLS = [
    {"name": "argocd-list_applications"},
    {"name": "argocd-get_application"},
    {"name": "argocd-sync_application"},
    {"name": "perplexity-search"},
    {"name": "unknown-some_tool"},  # No matching server
]


# --- Tests ---

@pytest.mark.asyncio
async def test_non_admin_rejected(client: AsyncClient):
    resp = await client.get("/api/litellm/mcp-servers")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_no_litellm_provider_returns_unavailable(admin_client: AsyncClient):
    """When no LiteLLM provider exists, returns available: false."""
    resp = await admin_client.get("/api/litellm/mcp-servers")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"available": False, "servers": {}, "enabled": []}


@pytest.mark.asyncio
async def test_litellm_detected_with_servers(admin_client: AsyncClient):
    """When LiteLLM responds with servers and tools, returns merged data."""
    await _create_litellm_provider(admin_client)

    server_resp = _mock_response(SAMPLE_SERVERS)
    tools_resp = _mock_response(SAMPLE_TOOLS)

    async def mock_gather(*coros, return_exceptions=False):
        return [server_resp, tools_resp]

    with patch("main.httpx.AsyncClient") as MockClient, \
         patch("main.asyncio.gather", side_effect=mock_gather):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        resp = await admin_client.get("/api/litellm/mcp-servers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True

    # Check argocd server
    assert "argocd" in data["servers"]
    argocd = data["servers"]["argocd"]
    assert argocd["description"] == "DevOps ArgoCD"
    assert sorted(argocd["tools"]) == ["get_application", "list_applications", "sync_application"]

    # Sensitive fields must be stripped
    for field in ["env", "credentials", "command", "args", "static_headers",
                  "authorization_url", "token_url", "registration_url", "extra_headers"]:
        assert field not in argocd

    # Check perplexity server
    assert "perplexity" in data["servers"]
    assert data["servers"]["perplexity"]["tools"] == ["search"]

    # Unknown tool should not create a server entry
    assert "unknown" not in data["servers"]

    assert data["enabled"] == []


@pytest.mark.asyncio
async def test_litellm_not_detected_404(admin_client: AsyncClient):
    """When LiteLLM probe returns 404, returns unavailable."""
    await _create_litellm_provider(admin_client, base_url="https://api.openai.com")

    server_resp = _mock_response({"error": "not found"}, status_code=404)
    tools_resp = _mock_response([], status_code=404)

    async def mock_gather(*coros, return_exceptions=False):
        return [server_resp, tools_resp]

    with patch("main.httpx.AsyncClient") as MockClient, \
         patch("main.asyncio.gather", side_effect=mock_gather):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        resp = await admin_client.get("/api/litellm/mcp-servers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False


@pytest.mark.asyncio
async def test_litellm_timeout(admin_client: AsyncClient):
    """When LiteLLM probe times out, returns unavailable."""
    await _create_litellm_provider(admin_client)

    async def mock_gather(*coros, return_exceptions=False):
        return [httpx.TimeoutException("timed out"), httpx.TimeoutException("timed out")]

    with patch("main.httpx.AsyncClient") as MockClient, \
         patch("main.asyncio.gather", side_effect=mock_gather):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        resp = await admin_client.get("/api/litellm/mcp-servers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False


@pytest.mark.asyncio
async def test_empty_server_list(admin_client: AsyncClient):
    """When LiteLLM has no MCP servers, returns available with empty servers."""
    await _create_litellm_provider(admin_client)

    server_resp = _mock_response([])
    tools_resp = _mock_response([])

    async def mock_gather(*coros, return_exceptions=False):
        return [server_resp, tools_resp]

    with patch("main.httpx.AsyncClient") as MockClient, \
         patch("main.asyncio.gather", side_effect=mock_gather):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        resp = await admin_client.get("/api/litellm/mcp-servers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["servers"] == {}


@pytest.mark.asyncio
async def test_enabled_servers_from_db(admin_client: AsyncClient):
    """Enabled list reflects stored litellm_mcp_servers setting."""
    await _create_litellm_provider(admin_client)
    await admin_client.put(
        "/api/settings",
        json={"litellm_mcp_servers": ["argocd"]},
    )

    server_resp = _mock_response(SAMPLE_SERVERS)
    tools_resp = _mock_response(SAMPLE_TOOLS)

    async def mock_gather(*coros, return_exceptions=False):
        return [server_resp, tools_resp]

    with patch("main.httpx.AsyncClient") as MockClient, \
         patch("main.asyncio.gather", side_effect=mock_gather):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        resp = await admin_client.get("/api/litellm/mcp-servers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] == ["argocd"]


@pytest.mark.asyncio
async def test_non_json_response_returns_unavailable(admin_client: AsyncClient):
    """When LiteLLM returns non-JSON, returns unavailable."""
    await _create_litellm_provider(admin_client)

    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.json.side_effect = ValueError("not JSON")
    tools_resp = _mock_response([])

    async def mock_gather(*coros, return_exceptions=False):
        return [bad_resp, tools_resp]

    with patch("main.httpx.AsyncClient") as MockClient, \
         patch("main.asyncio.gather", side_effect=mock_gather):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        resp = await admin_client.get("/api/litellm/mcp-servers")

    assert resp.status_code == 200
    assert resp.json()["available"] is False


@pytest.mark.asyncio
async def test_non_list_server_response_returns_unavailable(admin_client: AsyncClient):
    """When LiteLLM returns a non-list JSON, returns unavailable."""
    await _create_litellm_provider(admin_client)

    bad_resp = _mock_response({"error": "something"})
    tools_resp = _mock_response([])

    async def mock_gather(*coros, return_exceptions=False):
        return [bad_resp, tools_resp]

    with patch("main.httpx.AsyncClient") as MockClient, \
         patch("main.asyncio.gather", side_effect=mock_gather):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        resp = await admin_client.get("/api/litellm/mcp-servers")

    assert resp.status_code == 200
    assert resp.json()["available"] is False
