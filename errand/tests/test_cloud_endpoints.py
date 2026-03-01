"""Tests for cloud endpoint management."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from cloud_endpoints import (
    check_existing_endpoints,
    register_cloud_endpoints,
    revoke_cloud_endpoints,
)


class TestRegisterEndpoints:
    @pytest.mark.asyncio
    async def test_register_calls_cloud_api(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "integration": "slack",
            "endpoints": [
                {"type": "events", "url": "https://cloud.test/hook/t1", "token": "t1"},
                {"type": "commands", "url": "https://cloud.test/hook/t2", "token": "t2"},
                {"type": "interactivity", "url": "https://cloud.test/hook/t3", "token": "t3"},
            ],
        }

        session = AsyncMock()
        # Mock the Setting query to return None (no existing endpoints)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await register_cloud_endpoints(
                cloud_creds={"access_token": "test-token"},
                slack_creds={"signing_secret": "test-secret"},
                cloud_service_url="https://cloud.test",
                session=session,
            )

        assert result is not None
        assert len(result) == 3
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "Bearer test-token" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_register_returns_none_on_missing_token(self):
        session = AsyncMock()
        result = await register_cloud_endpoints(
            cloud_creds={"access_token": ""},
            slack_creds={"signing_secret": "test-secret"},
            cloud_service_url="https://cloud.test",
            session=session,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_register_returns_none_on_api_failure(self):
        session = AsyncMock()

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await register_cloud_endpoints(
                cloud_creds={"access_token": "test-token"},
                slack_creds={"signing_secret": "test-secret"},
                cloud_service_url="https://cloud.test",
                session=session,
            )

        assert result is None


class TestRevokeEndpoints:
    @pytest.mark.asyncio
    async def test_revoke_calls_cloud_api(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await revoke_cloud_endpoints(
                cloud_creds={"access_token": "test-token"},
                cloud_service_url="https://cloud.test",
            )

        mock_client.delete.assert_called_once()
        call_args = mock_client.delete.call_args
        assert "integration=slack" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_revoke_noop_without_token(self):
        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            await revoke_cloud_endpoints(
                cloud_creds={"access_token": ""},
                cloud_service_url="https://cloud.test",
            )
            mock_client_cls.assert_not_called()


class TestCheckExistingEndpoints:
    @pytest.mark.asyncio
    async def test_check_returns_endpoints(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"token": "t1", "type": "events"},
        ]

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_existing_endpoints(
                cloud_creds={"access_token": "test-token"},
                cloud_service_url="https://cloud.test",
            )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_check_returns_empty_on_failure(self):
        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_existing_endpoints(
                cloud_creds={"access_token": "test-token"},
                cloud_service_url="https://cloud.test",
            )

        assert result == []
