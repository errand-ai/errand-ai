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
async def test_no_base_url_returns_unavailable(admin_client: AsyncClient):
    """When openai_base_url is empty, returns available: false."""
    resp = await admin_client.get("/api/litellm/mcp-servers")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"available": False, "servers": {}, "enabled": []}


@pytest.mark.asyncio
async def test_litellm_detected_with_servers(admin_client: AsyncClient):
    """When LiteLLM responds with servers and tools, returns merged data."""
    # Seed openai_base_url setting
    await admin_client.put(
        "/api/settings",
        json={"openai_base_url": "https://litellm.example.com", "openai_api_key": "test-key"},
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
    await admin_client.put(
        "/api/settings",
        json={"openai_base_url": "https://api.openai.com"},
    )

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
    await admin_client.put(
        "/api/settings",
        json={"openai_base_url": "https://litellm.example.com"},
    )

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
    await admin_client.put(
        "/api/settings",
        json={"openai_base_url": "https://litellm.example.com", "openai_api_key": "key"},
    )

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
    await admin_client.put(
        "/api/settings",
        json={
            "openai_base_url": "https://litellm.example.com",
            "openai_api_key": "key",
            "litellm_mcp_servers": ["argocd"],
        },
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
    await admin_client.put(
        "/api/settings",
        json={"openai_base_url": "https://litellm.example.com"},
    )

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
    await admin_client.put(
        "/api/settings",
        json={"openai_base_url": "https://litellm.example.com"},
    )

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
