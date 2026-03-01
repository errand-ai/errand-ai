"""Tests for cloud auth module (token exchange and refresh via errand-cloud)."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from cloud_auth import exchange_code, refresh_token


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_exchanges_code_for_tokens(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "at-123",
            "refresh_token": "rt-123",
            "expires_in": 300,
            "token_type": "Bearer",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            tokens = await exchange_code("https://cloud.test", "test-code")

        assert tokens["access_token"] == "at-123"
        assert tokens["refresh_token"] == "rt-123"
        mock_client.post.assert_called_once_with(
            "https://cloud.test/auth/tenant/token",
            json={"code": "test-code"},
        )

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("400 Bad Request")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="400"):
                await exchange_code("https://cloud.test", "bad-code")


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refreshes_token(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 300,
            "token_type": "Bearer",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            tokens = await refresh_token("https://cloud.test", "old-rt")

        assert tokens["access_token"] == "new-at"
        mock_client.post.assert_called_once_with(
            "https://cloud.test/auth/tenant/refresh",
            json={"refresh_token": "old-rt"},
        )

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("cloud_auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="401"):
                await refresh_token("https://cloud.test", "expired-rt")
