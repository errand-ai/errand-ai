"""Tests for SearXNGPlatform: info, verify_credentials, search."""
import json
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from platforms.searxng import SearXNGPlatform, DEFAULT_URL
from platforms.base import Platform, PlatformCapability, PlatformInfo


class TestSearXNGInfo:
    def test_info_id(self):
        p = SearXNGPlatform()
        assert p.info().id == "searxng"

    def test_info_label(self):
        p = SearXNGPlatform()
        assert p.info().label == "SearXNG Search"

    def test_info_capabilities(self):
        p = SearXNGPlatform()
        assert PlatformCapability.SEARCH in p.info().capabilities

    def test_credential_schema_fields(self):
        p = SearXNGPlatform()
        schema = p.info().credential_schema
        keys = [f["key"] for f in schema]
        assert keys == ["url", "username", "password"]

    def test_credential_schema_url_required(self):
        p = SearXNGPlatform()
        schema = p.info().credential_schema
        url_field = next(f for f in schema if f["key"] == "url")
        assert url_field["required"] is True

    def test_credential_schema_auth_optional(self):
        p = SearXNGPlatform()
        schema = p.info().credential_schema
        username_field = next(f for f in schema if f["key"] == "username")
        password_field = next(f for f in schema if f["key"] == "password")
        assert username_field["required"] is False
        assert password_field["required"] is False


class TestSearXNGVerifyCredentials:
    async def test_valid_credentials(self):
        p = SearXNGPlatform()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await p.verify_credentials({"url": "https://search.example.com"})

        assert result is True
        mock_client.get.assert_called_once()

    async def test_invalid_url(self):
        p = SearXNGPlatform()

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await p.verify_credentials({"url": "https://bad.example.com"})

        assert result is False

    async def test_non_200_response(self):
        p = SearXNGPlatform()
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await p.verify_credentials({"url": "https://search.example.com"})

        assert result is False

    async def test_with_basic_auth(self):
        p = SearXNGPlatform()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await p.verify_credentials({
                "url": "https://search.example.com",
                "username": "user",
                "password": "pass",
            })

        assert result is True
        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["auth"] is not None


class TestSearXNGSearch:
    async def test_basic_search(self):
        p = SearXNGPlatform()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"title": "Result 1", "url": "https://example.com", "content": "desc", "engines": ["google"], "score": 1.5}
            ],
            "suggestions": ["related"],
            "number_of_results": 100,
        }

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await p.search("python frameworks", credentials={"url": "https://search.example.com"})

        assert result["query"] == "python frameworks"
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Result 1"
        assert result["suggestions"] == ["related"]
        assert result["number_of_results"] == 100

    async def test_search_with_filters(self):
        p = SearXNGPlatform()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": [], "suggestions": [], "number_of_results": 0}

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await p.search(
                "AI news",
                credentials={"url": "https://search.example.com"},
                time_range="day",
                categories="news",
            )

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs["params"]
        assert params["time_range"] == "day"
        assert params["categories"] == "news"

    async def test_search_default_url(self):
        p = SearXNGPlatform()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": [], "suggestions": [], "number_of_results": 0}

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await p.search("test", credentials={})

        call_args = mock_client.get.call_args
        assert DEFAULT_URL in call_args.args[0]

    async def test_search_unreachable(self):
        p = SearXNGPlatform()

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(httpx.ConnectError):
                await p.search("test", credentials={"url": "https://bad.example.com"})

    async def test_search_with_auth(self):
        p = SearXNGPlatform()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": [], "suggestions": [], "number_of_results": 0}

        with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await p.search("test", credentials={
                "url": "https://search.example.com",
                "username": "user",
                "password": "pass",
            })

        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["auth"] is not None


class TestPlatformBaseSearch:
    """Test that the base Platform class raises NotImplementedError for search()."""

    async def test_search_raises_not_implemented(self):
        class MinimalPlatform(Platform):
            def info(self) -> PlatformInfo:
                return PlatformInfo(id="test", label="Test", capabilities=set(), credential_schema=[])

            async def verify_credentials(self, credentials: dict) -> bool:
                return True

        p = MinimalPlatform()
        with pytest.raises(NotImplementedError):
            await p.search("test")
