"""Tests for version_checker: tag filtering, semver comparison, GHCR error handling."""
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

import version_checker as vc


class TestStripPrSuffix:
    def test_strips_pr_suffix(self):
        assert vc._strip_pr_suffix("0.65.0-pr66") == "0.65.0"

    def test_no_suffix(self):
        assert vc._strip_pr_suffix("0.65.0") == "0.65.0"

    def test_dev(self):
        assert vc._strip_pr_suffix("dev") == "dev"


class TestIsPrTag:
    def test_pr_tag(self):
        assert vc._is_pr_tag("0.65.0-pr66") is True

    def test_release_tag(self):
        assert vc._is_pr_tag("0.65.0") is False

    def test_non_pr_suffix(self):
        assert vc._is_pr_tag("0.65.0-beta1") is False


class TestFindLatestRelease:
    def test_filters_pr_tags(self):
        tags = ["0.64.0", "0.65.0", "0.65.0-pr66", "0.66.0-pr67"]
        assert vc._find_latest_release(tags) == "0.65.0"

    def test_finds_latest(self):
        tags = ["0.63.0", "0.64.0", "0.65.0"]
        assert vc._find_latest_release(tags) == "0.65.0"

    def test_only_pr_tags(self):
        tags = ["0.65.0-pr1", "0.66.0-pr2"]
        assert vc._find_latest_release(tags) is None

    def test_empty_tags(self):
        assert vc._find_latest_release([]) is None

    def test_non_semver_tags_ignored(self):
        tags = ["latest", "main", "0.65.0"]
        assert vc._find_latest_release(tags) == "0.65.0"


class TestCheckGhcr:
    @pytest.mark.asyncio
    async def test_update_available(self):
        with patch.object(vc, "APP_VERSION", "0.65.0"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            token_resp = MagicMock()
            token_resp.raise_for_status = MagicMock()
            token_resp.json.return_value = {"token": "fake-token"}

            tags_resp = MagicMock()
            tags_resp.raise_for_status = MagicMock()
            tags_resp.json.return_value = {"tags": ["0.64.0", "0.65.0", "0.66.0", "0.66.0-pr1"]}

            mock_client.get = AsyncMock(side_effect=[token_resp, tags_resp])

            with patch("httpx.AsyncClient", return_value=mock_client):
                latest, update = await vc._check_ghcr()

            assert latest == "0.66.0"
            assert update is True

    @pytest.mark.asyncio
    async def test_no_update(self):
        with patch.object(vc, "APP_VERSION", "0.65.0"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            token_resp = MagicMock()
            token_resp.raise_for_status = MagicMock()
            token_resp.json.return_value = {"token": "fake-token"}

            tags_resp = MagicMock()
            tags_resp.raise_for_status = MagicMock()
            tags_resp.json.return_value = {"tags": ["0.64.0", "0.65.0"]}

            mock_client.get = AsyncMock(side_effect=[token_resp, tags_resp])

            with patch("httpx.AsyncClient", return_value=mock_client):
                latest, update = await vc._check_ghcr()

            assert latest == "0.65.0"
            assert update is False

    @pytest.mark.asyncio
    async def test_pr_build_same_base(self):
        with patch.object(vc, "APP_VERSION", "0.65.0-pr66"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            token_resp = MagicMock()
            token_resp.raise_for_status = MagicMock()
            token_resp.json.return_value = {"token": "fake-token"}

            tags_resp = MagicMock()
            tags_resp.raise_for_status = MagicMock()
            tags_resp.json.return_value = {"tags": ["0.64.0", "0.65.0"]}

            mock_client.get = AsyncMock(side_effect=[token_resp, tags_resp])

            with patch("httpx.AsyncClient", return_value=mock_client):
                latest, update = await vc._check_ghcr()

            assert latest == "0.65.0"
            assert update is False

    @pytest.mark.asyncio
    async def test_pr_build_newer_available(self):
        with patch.object(vc, "APP_VERSION", "0.65.0-pr66"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            token_resp = MagicMock()
            token_resp.raise_for_status = MagicMock()
            token_resp.json.return_value = {"token": "fake-token"}

            tags_resp = MagicMock()
            tags_resp.raise_for_status = MagicMock()
            tags_resp.json.return_value = {"tags": ["0.65.0", "0.66.0"]}

            mock_client.get = AsyncMock(side_effect=[token_resp, tags_resp])

            with patch("httpx.AsyncClient", return_value=mock_client):
                latest, update = await vc._check_ghcr()

            assert latest == "0.66.0"
            assert update is True

    @pytest.mark.asyncio
    async def test_dev_version(self):
        with patch.object(vc, "APP_VERSION", "dev"):
            latest, update = await vc._check_ghcr()
            assert latest is None
            assert update is False

    @pytest.mark.asyncio
    async def test_ghcr_error_propagates(self):
        with patch.object(vc, "APP_VERSION", "0.65.0"):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(httpx.ConnectError):
                    await vc._check_ghcr()


class TestGetVersionInfo:
    def test_default_state(self):
        with patch.object(vc, "APP_VERSION", "0.65.0"), \
             patch.object(vc, "_cached_latest", None), \
             patch.object(vc, "_cached_update_available", False):
            info = vc.get_version_info()
            assert info == {"current": "0.65.0", "latest": None, "update_available": False}

    def test_with_cached_state(self):
        with patch.object(vc, "APP_VERSION", "0.65.0"), \
             patch.object(vc, "_cached_latest", "0.66.0"), \
             patch.object(vc, "_cached_update_available", True):
            info = vc.get_version_info()
            assert info == {"current": "0.65.0", "latest": "0.66.0", "update_available": True}
