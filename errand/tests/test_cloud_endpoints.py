"""Tests for cloud endpoint management."""
import os
import uuid

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from cloud_endpoints import (
    check_existing_endpoints,
    register_cloud_endpoints,
    register_webhook_trigger_with_cloud,
    revoke_cloud_endpoints,
    revoke_webhook_trigger_in_cloud,
)


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


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
        # session.execute() must return a result with scalar_one_or_none() -> None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

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


def _make_trigger(source="jira", token=None, encrypted_secret=None, name="Trigger"):
    """Construct a WebhookTrigger-like mock."""
    from platforms.credentials import encrypt
    trigger = MagicMock()
    trigger.id = uuid.uuid4()
    trigger.source = source
    trigger.name = name
    trigger.cloud_webhook_url = None
    trigger.cloud_endpoint_token = token
    trigger.webhook_secret = encrypted_secret if encrypted_secret is not None else encrypt({"secret": "plaintext-secret"})
    return trigger


class _FakeAsyncSession:
    """Minimal session stub for cloud_endpoints helpers.

    register_webhook_trigger_with_cloud calls _resolve_cloud_context, which executes two
    SELECTs (PlatformCredential, Setting), and then _store_endpoint_error/_clear_endpoint_error
    plus session.commit() on success.
    """
    def __init__(self, cloud_cred=None, url_setting=None):
        self._cloud_cred = cloud_cred
        self._url_setting = url_setting
        self._error_setting = None
        self._call = 0
        self.commits = 0
        self.adds: list = []

    async def execute(self, stmt):
        self._call += 1
        # Order: PlatformCredential, then Setting (cloud_service_url),
        # then Setting (cloud_endpoint_error) on store/clear.
        result = MagicMock()
        if self._call == 1:
            result.scalar_one_or_none.return_value = self._cloud_cred
        elif self._call == 2:
            result.scalar_one_or_none.return_value = self._url_setting
        else:
            result.scalar_one_or_none.return_value = self._error_setting
        return result

    def add(self, obj):
        self.adds.append(obj)

    async def commit(self):
        self.commits += 1

    async def delete(self, obj):
        if obj is self._error_setting:
            self._error_setting = None


def _connected_cloud_cred():
    from platforms.credentials import encrypt
    cred = MagicMock()
    cred.status = "connected"
    cred.encrypted_data = encrypt({"access_token": "test-token"})
    return cred


def _url_setting(value="https://cloud.test"):
    setting = MagicMock()
    setting.value = value
    return setting


class TestRegisterWebhookTriggerWithCloud:
    @pytest.mark.asyncio
    async def test_skips_when_cloud_disconnected(self):
        """5.2 — trigger create with cloud disconnected: helper not called, no DB writes."""
        trigger = _make_trigger()
        # cloud_cred=None → _resolve_cloud_context returns None
        session = _FakeAsyncSession(cloud_cred=None, url_setting=_url_setting())

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            await register_webhook_trigger_with_cloud(trigger, session)
            mock_client_cls.assert_not_called()

        assert trigger.cloud_webhook_url is None
        assert trigger.cloud_endpoint_token is None

    @pytest.mark.asyncio
    async def test_persists_url_and_token_on_success(self):
        """5.1 — trigger create with cloud connected: helper called with correct body; URL+token persisted."""
        trigger = _make_trigger(source="jira", name="My Jira Trigger")
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting("https://cloud.test"),
        )

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "url": "https://cloud.test/hook/abc123",
            "token": "abc123",
        }

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await register_webhook_trigger_with_cloud(trigger, session)

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["json"]["integration"] == "jira"
            assert call_kwargs["json"]["endpoint_type"] == "webhook"
            assert call_kwargs["json"]["trigger_id"] == str(trigger.id)
            assert call_kwargs["json"]["webhook_secret"] == "plaintext-secret"
            assert call_kwargs["json"]["label"] == "My Jira Trigger"
            assert "Bearer test-token" in call_kwargs["headers"]["Authorization"]

        assert trigger.cloud_webhook_url == "https://cloud.test/hook/abc123"
        assert trigger.cloud_endpoint_token == "abc123"
        assert session.commits >= 1

    @pytest.mark.asyncio
    async def test_persists_url_and_token_on_success_github(self):
        """5.7 — GitHub variant of the success case."""
        trigger = _make_trigger(source="github", name="GH Trigger")
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "url": "https://cloud.test/hook/gh1",
            "token": "gh1",
        }

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await register_webhook_trigger_with_cloud(trigger, session)
            assert mock_client.post.call_args.kwargs["json"]["integration"] == "github"

        assert trigger.cloud_webhook_url == "https://cloud.test/hook/gh1"
        assert trigger.cloud_endpoint_token == "gh1"

    @pytest.mark.asyncio
    async def test_403_logs_warning_and_stores_subscription_error(self, caplog):
        """Spec scenario: Registration API returns 403 → log at WARNING, store detail in
        cloud_endpoint_error Setting, leave cloud columns unchanged."""
        trigger = _make_trigger()
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 403
        mock_response.reason_phrase = "Forbidden"
        mock_response.text = '{"detail": "Active subscription required"}'
        mock_response.json.return_value = {"detail": "Active subscription required"}

        import logging as _logging
        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls, \
             caplog.at_level(_logging.WARNING, logger="cloud_endpoints"):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await register_webhook_trigger_with_cloud(trigger, session)

        # Trigger cloud columns left unchanged
        assert trigger.cloud_webhook_url is None
        assert trigger.cloud_endpoint_token is None

        # Log emitted at WARNING level (not ERROR) for 403
        warning_records = [r for r in caplog.records if r.levelno == _logging.WARNING]
        assert any("registration failed" in r.message.lower() for r in warning_records)

        # cloud_endpoint_error Setting stored with the subscription detail
        stored = [obj for obj in session.adds if getattr(obj, "key", None) == "cloud_endpoint_error"]
        assert stored, "cloud_endpoint_error Setting should be stored on 403"
        assert stored[0].value["detail"] == "Active subscription required"

    @pytest.mark.asyncio
    async def test_5xx_leaves_columns_unchanged_logs_error(self, caplog):
        """5.3 — trigger create with cloud returning 5xx: trigger persists; cloud columns null; error logged."""
        trigger = _make_trigger()
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.reason_phrase = "Internal Server Error"
        mock_response.text = '{"detail": "boom"}'
        mock_response.json.return_value = {"detail": "boom"}

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls, caplog.at_level("ERROR"):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await register_webhook_trigger_with_cloud(trigger, session)

        assert trigger.cloud_webhook_url is None
        assert trigger.cloud_endpoint_token is None
        assert any("registration failed" in rec.message.lower() for rec in caplog.records)


class TestRevokeWebhookTriggerInCloud:
    @pytest.mark.asyncio
    async def test_uses_token_path_when_token_set(self):
        """5.5 — trigger delete with token populated → uses DELETE /api/endpoints/{token}."""
        trigger = _make_trigger(token="tok-xyz")
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await revoke_webhook_trigger_in_cloud(trigger, session)

            url = mock_client.delete.call_args[0][0]
            assert url.endswith("/api/endpoints/tok-xyz")

    @pytest.mark.asyncio
    async def test_falls_back_to_bulk_query_when_no_token(self):
        """5.5 — trigger delete with token null → uses bulk delete fallback."""
        trigger = _make_trigger(token=None, source="github")
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await revoke_webhook_trigger_in_cloud(trigger, session)

            url = mock_client.delete.call_args[0][0]
            assert "integration=github" in url
            assert f"trigger_id={trigger.id}" in url
