"""Tests for Jira platform credential API routes."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


def _mock_jira_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"displayName": "Errand Bot", "accountId": "xyz"}
    return resp


@pytest.mark.asyncio
class TestJiraCredentials:
    async def test_save_valid_credentials(self, admin_client):
        mock_resp = _mock_jira_response()
        with patch("jira_credential_routes.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = await admin_client.put("/api/credentials/jira", json={
                "cloud_id": "abc-123",
                "api_token": "tok_xxx",
                "site_url": "https://acme.atlassian.net",
                "service_account_email": "bot@acme.com",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform_id"] == "jira"
        assert data["status"] == "connected"
        assert data["display_name"] == "Errand Bot"
        assert data["site_url"] == "https://acme.atlassian.net"

    async def test_save_invalid_token(self, admin_client):
        mock_resp = _mock_jira_response(status_code=401)
        with patch("jira_credential_routes.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = await admin_client.put("/api/credentials/jira", json={
                "cloud_id": "abc-123",
                "api_token": "bad-token",
                "site_url": "https://acme.atlassian.net",
                "service_account_email": "bot@acme.com",
            })
        assert resp.status_code == 400
        assert "verification failed" in resp.json()["detail"].lower()

    async def test_get_status_no_credentials(self, admin_client):
        resp = await admin_client.get("/api/credentials/jira")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disconnected"
        assert data["site_url"] is None

    async def test_get_status_with_credentials(self, admin_client):
        # First save
        mock_resp = _mock_jira_response()
        with patch("jira_credential_routes.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            await admin_client.put("/api/credentials/jira", json={
                "cloud_id": "abc-123",
                "api_token": "tok_xxx",
                "site_url": "https://acme.atlassian.net",
                "service_account_email": "bot@acme.com",
            })
        # Then get status
        resp = await admin_client.get("/api/credentials/jira")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert data["site_url"] == "https://acme.atlassian.net"

    async def test_delete_credentials(self, admin_client):
        # Save first
        mock_resp = _mock_jira_response()
        with patch("jira_credential_routes.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            await admin_client.put("/api/credentials/jira", json={
                "cloud_id": "abc-123",
                "api_token": "tok_xxx",
                "site_url": "https://acme.atlassian.net",
                "service_account_email": "bot@acme.com",
            })
        # Delete
        resp = await admin_client.delete("/api/credentials/jira")
        assert resp.status_code == 204
        # Verify gone
        resp = await admin_client.get("/api/credentials/jira")
        assert resp.json()["status"] == "disconnected"

    async def test_delete_idempotent(self, admin_client):
        resp = await admin_client.delete("/api/credentials/jira")
        assert resp.status_code == 204

    async def test_non_admin_rejected(self, client):
        resp = await client.put("/api/credentials/jira", json={
            "cloud_id": "abc", "api_token": "tok", "site_url": "https://x.atlassian.net", "service_account_email": "e@x.com",
        })
        assert resp.status_code == 403

    async def test_network_error(self, admin_client):
        import httpx as httpx_module
        with patch("jira_credential_routes.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(side_effect=httpx_module.RequestError("Connection refused"))
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = await admin_client.put("/api/credentials/jira", json={
                "cloud_id": "abc-123",
                "api_token": "tok_xxx",
                "site_url": "https://acme.atlassian.net",
                "service_account_email": "bot@acme.com",
            })
        assert resp.status_code == 400
        assert "verification failed" in resp.json()["detail"].lower()
