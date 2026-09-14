"""Tests for cloud endpoint management."""
import asyncio
import uuid

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
from sqlalchemy import select

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


@pytest.fixture(autouse=True)
def _reset_post_connect_cooldown():
    """Clear the post-connect cooldown between tests.

    It is module-level mutable state: a test that runs a pass leaves the next
    one inside the cooldown window, which silently turns its pass into a no-op
    and makes the outcome depend on test order.
    """
    import cloud_endpoints
    cloud_endpoints._last_post_connect_at = 0.0
    yield
    cloud_endpoints._last_post_connect_at = 0.0


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
    async def test_check_queries_the_requested_integration(self):
        """1.1 — the helper can ask about an integration other than slack."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{"token": "jira-1", "type": "webhook"}]

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_existing_endpoints(
                cloud_creds={"access_token": "test-token"},
                cloud_service_url="https://cloud.test",
                integration="jira",
            )

            called_url = mock_client.get.call_args.args[0]

        assert called_url == "https://cloud.test/api/endpoints?integration=jira"
        assert result == [{"token": "jira-1", "type": "webhook"}]

    @pytest.mark.asyncio
    async def test_check_defaults_to_slack(self):
        """1.3 — existing callers are unchanged: no integration argument means slack."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await check_existing_endpoints(
                cloud_creds={"access_token": "test-token"},
                cloud_service_url="https://cloud.test",
            )

            called_url = mock_client.get.call_args.args[0]

        assert called_url == "https://cloud.test/api/endpoints?integration=slack"

    @pytest.mark.asyncio
    async def test_check_returns_none_on_failure(self):
        """1.2 — a failed call is None, NOT an empty list.

        Conflating the two is the hazard the reconciliation pass turns on: an
        unreachable cloud read as "no endpoints exist" would re-register every
        trigger and change every URL.
        """
        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_existing_endpoints(
                cloud_creds={"access_token": "test-token"},
                cloud_service_url="https://cloud.test",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_check_returns_empty_list_when_cloud_has_none(self):
        """1.2 — an affirmative "nothing here" stays distinguishable from failure."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_existing_endpoints(
                cloud_creds={"access_token": "test-token"},
                cloud_service_url="https://cloud.test",
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_check_returns_none_without_access_token(self):
        """No token means we never asked, which is not evidence of emptiness."""
        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            result = await check_existing_endpoints(
                cloud_creds={"access_token": ""},
                cloud_service_url="https://cloud.test",
            )
            mock_client_cls.assert_not_called()

        assert result is None


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
        """5.1 — trigger create with cloud connected: helper called with correct body; URL+token persisted.

        The cloud returns the URL/token inside an `endpoints` array (the same
        envelope it uses for Slack registration). The helper must extract them
        from there.
        """
        trigger = _make_trigger(source="jira", name="My Jira Trigger")
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting("https://cloud.test"),
        )

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "integration": "jira",
            "label": "My Jira Trigger",
            "endpoints": [
                {"type": "webhook", "url": "https://cloud.test/hook/abc123", "token": "abc123"},
            ],
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
        """5.7 — GitHub variant of the success case (nested-endpoints response shape)."""
        trigger = _make_trigger(source="github", name="GH Trigger")
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "integration": "github",
            "label": "GH Trigger",
            "endpoints": [
                {"type": "webhook", "url": "https://cloud.test/hook/gh1", "token": "gh1"},
            ],
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
    async def test_backfills_missing_webhook_secret_on_legacy_trigger(self):
        """Legacy trigger rows pre-date server-side secret generation and may
        have webhook_secret == NULL. The helper should generate, encrypt, and
        persist a secret on first attempt rather than silently skipping forever.
        """
        trigger = _make_trigger()
        trigger.webhook_secret = None  # legacy row
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "endpoints": [{"type": "webhook", "url": "https://cloud.test/hook/bf", "token": "bf"}],
        }

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await register_webhook_trigger_with_cloud(trigger, session)

        # Secret was backfilled (encrypted) and registration completed
        assert trigger.webhook_secret is not None
        assert trigger.cloud_webhook_url == "https://cloud.test/hook/bf"
        assert trigger.cloud_endpoint_token == "bf"
        # And the body sent to cloud carried the freshly-generated plaintext
        sent_body = mock_client.post.call_args.kwargs["json"]
        assert sent_body["webhook_secret"]  # not empty

    @pytest.mark.asyncio
    async def test_accepts_top_level_url_token_for_forward_compat(self):
        """If a future cloud version flattens the response (`{url, token}` at top
        level instead of nested under `endpoints[]`), we still extract correctly."""
        trigger = _make_trigger(source="jira")
        session = _FakeAsyncSession(
            cloud_cred=_connected_cloud_cred(),
            url_setting=_url_setting(),
        )

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "url": "https://cloud.test/hook/flat",
            "token": "flat",
        }

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await register_webhook_trigger_with_cloud(trigger, session)

        assert trigger.cloud_webhook_url == "https://cloud.test/hook/flat"
        assert trigger.cloud_endpoint_token == "flat"

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


# ---------------------------------------------------------------------------
# Reconciliation of webhook trigger endpoints on cloud connect
# ---------------------------------------------------------------------------


def _listing_response(endpoints):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = endpoints
    return resp


def _registration_response(url, token, integration="jira"):
    resp = MagicMock()
    resp.is_success = True
    resp.json.return_value = {
        "integration": integration,
        "endpoints": [{"type": "webhook", "url": url, "token": token}],
    }
    return resp


def _failed_registration_response(status_code=403, detail="Active subscription required"):
    resp = MagicMock()
    resp.is_success = False
    resp.status_code = status_code
    resp.reason_phrase = "Forbidden"
    resp.text = detail
    resp.json.return_value = {"detail": detail}
    return resp


class _FakeCloud:
    """Stands in for httpx.AsyncClient, recording every call it is asked to make."""

    def __init__(self, get_responses=None, post_responses=None):
        self._get_responses = list(get_responses or [])
        self._post_responses = list(post_responses or [])
        self.get_urls: list[str] = []
        self.post_bodies: list[dict] = []

    async def get(self, url, **kwargs):
        self.get_urls.append(url)
        response = self._get_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def post(self, url, **kwargs):
        self.post_bodies.append(kwargs.get("json", {}))
        response = self._post_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _patch_cloud(fake):
    patcher = patch("cloud_endpoints.httpx.AsyncClient")
    mock_client_cls = patcher.start()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=fake)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return patcher


async def _seed_cloud_credentials(session_factory, status="connected"):
    from models import PlatformCredential, Setting
    from platforms.credentials import encrypt

    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id="cloud",
            encrypted_data=encrypt({"access_token": "test-token"}),
            status=status,
        ))
        session.add(Setting(key="cloud_service_url", value="https://cloud.test"))
        await session.commit()


async def _add_trigger(session_factory, *, name, source, url, token, secret="plaintext-secret"):
    from models import WebhookTrigger
    from platforms.credentials import encrypt

    async with session_factory() as session:
        trigger = WebhookTrigger(
            name=name,
            source=source,
            filters={},
            actions={},
            webhook_secret=encrypt({"secret": secret}) if secret else None,
            cloud_webhook_url=url,
            cloud_endpoint_token=token,
        )
        session.add(trigger)
        await session.commit()
        return trigger.id


async def _reload(session_factory, trigger_id):
    from models import WebhookTrigger
    async with session_factory() as session:
        result = await session.execute(
            select(WebhookTrigger).where(WebhookTrigger.id == trigger_id)
        )
        return result.scalar_one()


async def _run_reconcile(session_factory):
    from cloud_endpoints import reconcile_webhook_trigger_endpoints
    async with session_factory() as session:
        await reconcile_webhook_trigger_endpoints(session)


class TestReconcileWebhookTriggerEndpoints:
    @pytest.mark.asyncio
    async def test_revoked_jira_endpoint_is_reregistered(self, db_session):
        """2.1 — a stored token absent from the cloud listing is re-registered."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira T", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([{"token": "someone-else", "type": "webhook"}])],
            post_responses=[_registration_response("https://cloud.test/hook/fresh", "fresh-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url == "https://cloud.test/hook/fresh"
        assert trigger.cloud_endpoint_token == "fresh-token"
        assert fake.get_urls == ["https://cloud.test/api/endpoints?integration=jira"]
        assert len(fake.post_bodies) == 1

    @pytest.mark.asyncio
    async def test_revoked_github_endpoint_is_reregistered(self, db_session):
        """2.2 — the same for GitHub."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="GH T", source="github",
            url="https://cloud.test/hook/dead", token="dead-token",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[
                _registration_response("https://cloud.test/hook/gh", "gh-token", integration="github")
            ],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url == "https://cloud.test/hook/gh"
        assert trigger.cloud_endpoint_token == "gh-token"
        assert fake.get_urls == ["https://cloud.test/api/endpoints?integration=github"]
        assert fake.post_bodies[0]["integration"] == "github"

    @pytest.mark.asyncio
    async def test_live_endpoint_is_left_untouched(self, db_session):
        """2.3 — a token present in the listing means no POST and no change."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Live", source="jira",
            url="https://cloud.test/hook/live", token="live-token",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([{"token": "live-token", "type": "webhook"}])],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url == "https://cloud.test/hook/live"
        assert trigger.cloud_endpoint_token == "live-token"
        assert fake.post_bodies == []

    @pytest.mark.asyncio
    async def test_reregistration_reuses_the_stored_secret(self, db_session):
        """2.4 — the already-configured third-party secret must not be regenerated."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Secret", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token",
            secret="configured-in-jira",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/new", "new-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert fake.post_bodies[0]["webhook_secret"] == "configured-in-jira"
        assert fake.post_bodies[0]["trigger_id"] == str(trigger_id)

    @pytest.mark.asyncio
    async def test_never_registered_trigger_is_registered(self, db_session):
        """2.6 — a null token means registration never succeeded; connect is the retry."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Never", source="jira", url=None, token=None,
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/first", "first-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url == "https://cloud.test/hook/first"
        assert trigger.cloud_endpoint_token == "first-token"

    @pytest.mark.asyncio
    async def test_one_listing_call_per_integration(self, db_session):
        """2.7 — three Jira triggers produce one GET, not three."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        for n in range(3):
            await _add_trigger(
                session_factory, name=f"Jira {n}", source="jira",
                url="https://cloud.test/hook/live", token="live-token",
            )

        fake = _FakeCloud(
            get_responses=[_listing_response([{"token": "live-token", "type": "webhook"}])],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert fake.get_urls == ["https://cloud.test/api/endpoints?integration=jira"]

    @pytest.mark.asyncio
    async def test_gone_endpoint_with_failed_reregistration_clears_url(self, db_session):
        """3.1 — a dead URL must stop being displayed as live."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Gone", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_failed_registration_response()],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url is None

        from models import Setting
        async with session_factory() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_endpoint_error")
            )
            error = result.scalar_one_or_none()
        assert error is not None
        assert error.value["detail"] == "Active subscription required"

    @pytest.mark.asyncio
    async def test_unreachable_cloud_clears_nothing(self, db_session):
        """3.2 — a failed listing is not evidence the endpoint is gone."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Cached", source="jira",
            url="https://cloud.test/hook/cached", token="cached-token",
        )

        fake = _FakeCloud(get_responses=[httpx.HTTPError("cloud down")])
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url == "https://cloud.test/hook/cached"
        assert trigger.cloud_endpoint_token == "cached-token"
        assert fake.post_bodies == []

    @pytest.mark.asyncio
    async def test_reconciliation_never_raises(self, db_session):
        """3.4 — an exception anywhere must not abort the cloud connect flow."""
        from cloud_endpoints import reconcile_webhook_trigger_endpoints

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=RuntimeError("boom"))

        await reconcile_webhook_trigger_endpoints(session)

    @pytest.mark.asyncio
    async def test_skipped_when_cloud_not_connected(self, db_session):
        """4.3 — no credential, or a credential that is not connected, means no pass."""
        _, session_factory = db_session
        trigger_id = await _add_trigger(
            session_factory, name="Jira Orphan", source="jira",
            url="https://cloud.test/hook/cached", token="cached-token",
        )

        fake = _FakeCloud()
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert fake.get_urls == []

        await _seed_cloud_credentials(session_factory, status="disconnected")
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert fake.get_urls == []
        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url == "https://cloud.test/hook/cached"


class TestTryRegisterEndpointsSlackUnchanged:
    """1.5 — generalising the helper must not move the Slack path."""

    @staticmethod
    async def _seed(session_factory):
        from models import PlatformCredential, Setting
        from platforms.credentials import encrypt

        async with session_factory() as session:
            session.add(PlatformCredential(
                platform_id="cloud",
                encrypted_data=encrypt({"access_token": "test-token"}),
                status="connected",
            ))
            session.add(PlatformCredential(
                platform_id="slack",
                encrypted_data=encrypt({"signing_secret": "sign-me"}),
                status="connected",
            ))
            session.add(Setting(key="cloud_service_url", value="https://cloud.test"))
            await session.commit()

    @staticmethod
    async def _run(session_factory):
        from cloud_endpoints import try_register_endpoints
        async with session_factory() as session:
            await try_register_endpoints(session)

    @staticmethod
    async def _stored_endpoints(session_factory):
        from models import Setting
        async with session_factory() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_endpoints")
            )
            setting = result.scalar_one_or_none()
        return setting.value if setting else None

    @pytest.mark.asyncio
    async def test_existing_endpoints_are_cached_without_reregistering(self, db_session):
        _, session_factory = db_session
        await self._seed(session_factory)

        fake = _FakeCloud(get_responses=[_listing_response([
            {"integration": "slack", "type": "events", "url": "https://cloud.test/hook/e", "token": "e"},
        ])])
        patcher = _patch_cloud(fake)
        try:
            await self._run(session_factory)
        finally:
            patcher.stop()

        assert fake.post_bodies == []
        assert fake.get_urls == ["https://cloud.test/api/endpoints?integration=slack"]
        assert await self._stored_endpoints(session_factory) == [
            {"integration": "slack", "endpoint_type": "events",
             "url": "https://cloud.test/hook/e", "token": "e"},
        ]

    @pytest.mark.asyncio
    async def test_previously_revoked_endpoints_are_recreated(self, db_session):
        """The re-create path: the cloud holds nothing, so Slack endpoints are made again."""
        _, session_factory = db_session
        await self._seed(session_factory)

        registration = MagicMock()
        registration.is_success = True
        registration.status_code = 200
        registration.json.return_value = {
            "integration": "slack",
            "endpoints": [{"type": "events", "url": "https://cloud.test/hook/new", "token": "new"}],
        }
        fake = _FakeCloud(get_responses=[_listing_response([])], post_responses=[registration])
        patcher = _patch_cloud(fake)
        try:
            await self._run(session_factory)
        finally:
            patcher.stop()

        assert len(fake.post_bodies) == 1
        assert fake.post_bodies[0]["integration"] == "slack"
        assert fake.post_bodies[0]["signing_secret"] == "sign-me"
        assert await self._stored_endpoints(session_factory) == [
            {"integration": "slack", "endpoint_type": "events",
             "url": "https://cloud.test/hook/new", "token": "new"},
        ]

    @pytest.mark.asyncio
    async def test_failed_listing_still_registers(self, db_session):
        """Unchanged from before None existed: Slack registration is an idempotent upsert."""
        _, session_factory = db_session
        await self._seed(session_factory)

        registration = MagicMock()
        registration.is_success = True
        registration.status_code = 200
        registration.json.return_value = {"integration": "slack", "endpoints": []}
        fake = _FakeCloud(
            get_responses=[httpx.HTTPError("cloud down")],
            post_responses=[registration],
        )
        patcher = _patch_cloud(fake)
        try:
            await self._run(session_factory)
        finally:
            patcher.stop()

        assert len(fake.post_bodies) == 1


class TestPostConnectEndpointPasses:
    """Review follow-up: the two passes are independent, and every connect runs them."""

    @pytest.mark.asyncio
    async def test_slack_failure_does_not_cost_reconciliation_its_attempt(self):
        """A raising try_register_endpoints must not skip reconciliation."""
        import cloud_endpoints

        with patch.object(cloud_endpoints, "try_register_endpoints",
                          new=AsyncMock(side_effect=RuntimeError("slack blew up"))), \
             patch.object(cloud_endpoints, "reconcile_webhook_trigger_endpoints",
                          new=AsyncMock()) as reconcile, \
             patch("database.async_session") as session_cls:
            session_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await cloud_endpoints.run_post_connect_endpoint_passes()

        reconcile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_an_in_flight_pass_suppresses_a_duplicate(self):
        """A flapping connection must not pile passes up."""
        import cloud_endpoints

        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def slow_register(session):
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()

        with patch.object(cloud_endpoints, "try_register_endpoints", new=slow_register), \
             patch.object(cloud_endpoints, "reconcile_webhook_trigger_endpoints",
                          new=AsyncMock()), \
             patch("database.async_session") as session_cls:
            session_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            first = asyncio.create_task(cloud_endpoints.run_post_connect_endpoint_passes())
            await asyncio.wait_for(started.wait(), timeout=5)
            await cloud_endpoints.run_post_connect_endpoint_passes()  # should be suppressed
            release.set()
            await first

        assert calls == 1

    @pytest.mark.asyncio
    async def test_websocket_connect_runs_the_passes(self):
        """Spec: reconciliation runs on each successful cloud connect, reconnects included.

        Drives the real connect path rather than inspecting its source, so an
        unreachable or commented-out call would fail here.
        """
        import cloud_client
        import websockets.exceptions

        ran = asyncio.Event()

        async def fake_passes():
            ran.set()

        class _FakeWS:
            async def recv(self):
                raise websockets.exceptions.ConnectionClosed(None, None)

            async def close(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        client = cloud_client.CloudWebSocketClient()
        client._running = True

        with patch("cloud_endpoints.run_post_connect_endpoint_passes", new=fake_passes), \
             patch.object(client, "_load_credentials",
                          new=AsyncMock(return_value={"access_token": "t"})), \
             patch.object(client, "_get_cloud_ws_url",
                          new=AsyncMock(return_value="wss://cloud.test/ws")), \
             patch.object(client, "_send_register", new=AsyncMock()), \
             patch.object(client, "_wait_for_registered", new=AsyncMock(return_value=True)), \
             patch.object(client, "_handle_close", new=AsyncMock()), \
             patch.object(client, "_cleanup_subscriptions", new=AsyncMock()), \
             patch("cloud_client.publish_event", new=AsyncMock()), \
             patch("cloud_client.websockets.connect", return_value=_FakeWS()):
            await client._connect_and_receive()
            # The pass is dispatched as a task so it cannot stall the receive loop.
            await asyncio.wait_for(ran.wait(), timeout=2)

        assert ran.is_set()
        await cloud_client.cancel_endpoint_tasks()

    @pytest.mark.asyncio
    async def test_disconnect_cancels_an_in_flight_pass(self):
        """A pass still running would POST after disconnect's bulk revoke."""
        import cloud_client

        started = asyncio.Event()
        completed = False

        async def slow_pass():
            nonlocal completed
            started.set()
            await asyncio.sleep(30)
            completed = True

        task = asyncio.create_task(slow_pass())
        cloud_client._track_endpoint_task(task)
        await asyncio.wait_for(started.wait(), timeout=5)

        await cloud_client.cancel_endpoint_tasks()

        assert task.cancelled() or task.done()
        assert completed is False
        assert cloud_client._endpoint_tasks == set()


class TestReconcileSkipsRowsDeletedMidPass:
    @pytest.mark.asyncio
    async def test_trigger_deleted_during_the_pass_is_not_recreated(self, db_session):
        """A row deleted between the listing call and the POST must not come back."""
        from models import WebhookTrigger
        from sqlalchemy import delete

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Doomed", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token",
        )

        class _DeletingCloud(_FakeCloud):
            async def get(self, url, **kwargs):
                # The user deletes the trigger while we are asking the cloud.
                async with session_factory() as s:
                    await s.execute(delete(WebhookTrigger).where(WebhookTrigger.id == trigger_id))
                    await s.commit()
                return await super().get(url, **kwargs)

        fake = _DeletingCloud(get_responses=[_listing_response([])])
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert fake.post_bodies == [], "a deleted trigger must not be re-created on the cloud"


class TestSecretFailuresRecordADetail:
    @pytest.mark.asyncio
    async def test_undecryptable_secret_records_an_error(self, db_session):
        """The cleared URL must come with a reason, as every other failure does."""
        from models import Setting
        from cloud_endpoints import register_webhook_trigger_with_cloud, reconcile_webhook_trigger_endpoints

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        await _add_trigger(
            session_factory, name="Jira Corrupt", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token", secret=None,
        )
        # A secret that is present but not decryptable with this key.
        from models import WebhookTrigger
        async with session_factory() as s:
            trig = (await s.execute(select(WebhookTrigger))).scalars().one()
            trig.webhook_secret = "not-a-valid-fernet-token"
            await s.commit()

        fake = _FakeCloud(get_responses=[_listing_response([])])
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        async with session_factory() as s:
            err = (await s.execute(
                select(Setting).where(Setting.key == "cloud_endpoint_error")
            )).scalar_one_or_none()
        assert err is not None
        assert "webhook secret" in err.value["detail"]
        assert fake.post_bodies == []


class TestListingPayloadValidation:
    """A 2xx body that is not a list of records must not read as 'nothing exists'."""

    @staticmethod
    def _resp(payload):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    @pytest.mark.parametrize("payload", [
        {"detail": "gateway error"},
        "not json at all",
        [{"token": "ok"}, "stray string"],
        None,
    ])
    @pytest.mark.asyncio
    async def test_non_list_body_is_a_failure_not_an_empty_listing(self, payload):
        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=self._resp(payload))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_existing_endpoints(
                cloud_creds={"access_token": "t"},
                cloud_service_url="https://cloud.test",
                integration="jira",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_listing_reregisters_nothing(self, db_session):
        """The mass-churn hazard: every trigger must not look revoked at once."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        for n in range(3):
            await _add_trigger(
                session_factory, name=f"Jira {n}", source="jira",
                url=f"https://cloud.test/hook/{n}", token=f"token-{n}",
            )

        fake = _FakeCloud(get_responses=[self._resp({"detail": "bad gateway"})])
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert fake.post_bodies == []
        from models import WebhookTrigger
        async with session_factory() as s:
            rows = (await s.execute(select(WebhookTrigger))).scalars().all()
        assert all(r.cloud_webhook_url is not None for r in rows)


class TestReconcileEdgeCases:
    @pytest.mark.asyncio
    async def test_trigger_that_changed_integration_is_skipped(self, db_session):
        """It was never in this integration's listing, so it must not be acted on here."""
        from models import WebhookTrigger

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Mover", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token",
        )

        class _MovingCloud(_FakeCloud):
            async def get(self, url, **kwargs):
                async with session_factory() as s:
                    row = (await s.execute(
                        select(WebhookTrigger).where(WebhookTrigger.id == trigger_id)
                    )).scalar_one()
                    row.source = "github"
                    await s.commit()
                return await super().get(url, **kwargs)

        fake = _MovingCloud(get_responses=[_listing_response([])])
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert fake.post_bodies == []

    @pytest.mark.asyncio
    async def test_one_triggers_failure_does_not_end_the_pass(self, db_session):
        """A raise on the first trigger must not cost the second its attempt."""
        import cloud_endpoints

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        await _add_trigger(session_factory, name="Jira A", source="jira",
                           url="https://cloud.test/hook/a", token="dead-a")
        await _add_trigger(session_factory, name="Jira B", source="jira",
                           url="https://cloud.test/hook/b", token="dead-b")

        calls = 0
        real = cloud_endpoints.register_webhook_trigger_with_cloud

        async def flaky(trigger, session):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("first one explodes")
            return await real(trigger, session)

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/new", "new-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            with patch.object(cloud_endpoints, "register_webhook_trigger_with_cloud", new=flaky):
                await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert calls == 2, "the pass must continue past a failing trigger"

    @pytest.mark.asyncio
    async def test_delete_path_and_reconciliation_share_the_trigger_lock(self):
        """The lock registry is the coordination; both sides must reach the same object."""
        from cloud_endpoints import forget_trigger_lock, trigger_endpoint_lock

        tid = uuid.uuid4()
        first = trigger_endpoint_lock(tid)
        assert trigger_endpoint_lock(str(tid)) is first, "uuid and str must map to one lock"

        forget_trigger_lock(tid)
        assert trigger_endpoint_lock(tid) is not first, "a deleted trigger's lock is dropped"
        forget_trigger_lock(tid)

    @pytest.mark.asyncio
    async def test_reconciliation_waits_for_a_held_trigger_lock(self, db_session):
        """A delete in progress must finish before reconciliation registers."""
        from cloud_endpoints import trigger_endpoint_lock

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Locked", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token",
        )

        lock = trigger_endpoint_lock(trigger_id)
        await lock.acquire()

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/new", "new-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            pass_task = asyncio.create_task(_run_reconcile(session_factory))
            await asyncio.sleep(0.05)
            assert fake.post_bodies == [], "must not register while the lock is held"
            lock.release()
            await asyncio.wait_for(pass_task, timeout=2)
        finally:
            patcher.stop()

        assert len(fake.post_bodies) == 1, "and must proceed once it is released"


class TestPostConnectCooldown:
    """A reconnect storm must not become a request storm against errand-cloud."""

    @staticmethod
    def _patched(register, reconcile):
        import cloud_endpoints
        return (
            patch.object(cloud_endpoints, "try_register_endpoints", new=register),
            patch.object(cloud_endpoints, "reconcile_webhook_trigger_endpoints", new=reconcile),
            patch("database.async_session"),
        )

    @pytest.mark.asyncio
    async def test_a_burst_of_reconnects_runs_one_pass(self):
        import cloud_endpoints

        register, reconcile = AsyncMock(), AsyncMock()
        p1, p2, p3 = self._patched(register, reconcile)
        with p1, p2, p3 as session_cls:
            session_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            for _ in range(20):
                await cloud_endpoints.run_post_connect_endpoint_passes()

        assert reconcile.await_count == 1, "the cooldown must absorb the burst"

    @pytest.mark.asyncio
    async def test_a_deliberate_connect_is_never_swallowed(self):
        """The user waiting on device authorization must not lose their pass."""
        import cloud_endpoints

        register, reconcile = AsyncMock(), AsyncMock()
        p1, p2, p3 = self._patched(register, reconcile)
        with p1, p2, p3 as session_cls:
            session_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await cloud_endpoints.run_post_connect_endpoint_passes()          # reconnect
            await cloud_endpoints.run_post_connect_endpoint_passes(force=True)  # device auth

        assert reconcile.await_count == 2

    @pytest.mark.asyncio
    async def test_the_cooldown_expires(self):
        import cloud_endpoints

        register, reconcile = AsyncMock(), AsyncMock()
        p1, p2, p3 = self._patched(register, reconcile)
        with p1, p2, p3 as session_cls:
            session_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await cloud_endpoints.run_post_connect_endpoint_passes()
            # Wind the clock past the cooldown rather than waiting it out.
            cloud_endpoints._last_post_connect_at -= (
                cloud_endpoints.POST_CONNECT_COOLDOWN_SECS + 1
            )
            await cloud_endpoints.run_post_connect_endpoint_passes()

        assert reconcile.await_count == 2, "a later reconnect must still reconcile"


class TestUrlChangeNotice:
    """A replaced URL leaves the third party posting into a 404 until repointed."""

    @staticmethod
    async def _changes(session_factory):
        from models import Setting
        from cloud_endpoints import URL_CHANGES_SETTING
        async with session_factory() as s:
            setting = (await s.execute(
                select(Setting).where(Setting.key == URL_CHANGES_SETTING)
            )).scalar_one_or_none()
        return setting.value if setting else None

    @pytest.mark.asyncio
    async def test_a_replaced_url_is_recorded(self, db_session):
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Moved", source="jira",
            url="https://cloud.test/hook/old", token="dead-token",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/new", "new-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        value = await self._changes(session_factory)
        assert value is not None
        assert len(value["changes"]) == 1
        change = value["changes"][0]
        assert change["trigger_id"] == str(trigger_id)
        assert change["name"] == "Jira Moved"
        assert change["previous_url"] == "https://cloud.test/hook/old"
        assert change["new_url"] == "https://cloud.test/hook/new"

    @pytest.mark.asyncio
    async def test_a_first_registration_is_not_a_change(self, db_session):
        """Nothing is configured anywhere yet, so there is nothing to correct."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        await _add_trigger(
            session_factory, name="Jira New", source="jira", url=None, token=None,
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/first", "first-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert await self._changes(session_factory) is None

    @pytest.mark.asyncio
    async def test_a_change_survives_the_clearing_gap(self, db_session):
        """The repair usually follows a failed attempt that cleared the URL.

        Without carrying the cleared URL forward the change would go unreported
        precisely in the case that motivated the feature.
        """
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Gap", source="jira",
            url="https://cloud.test/hook/configured-in-jira", token="dead-token",
        )

        # Pass one: endpoint gone, registration refused, URL cleared.
        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_failed_registration_response()],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url is None

        # Pass two, after the cloud-side fix: registration now succeeds.
        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/repaired", "new-token")],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        value = await self._changes(session_factory)
        assert value is not None, "the change must still be reported across the gap"
        assert value["changes"][0]["previous_url"] == "https://cloud.test/hook/configured-in-jira"
        assert value["changes"][0]["new_url"] == "https://cloud.test/hook/repaired"
        assert value["last_known"] == {}, "the carried URL is dropped once reported"

    @pytest.mark.asyncio
    async def test_repeated_passes_do_not_stack_entries(self, db_session):
        """One entry per trigger, or a flapping endpoint becomes a wall of notices."""
        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Flappy", source="jira",
            url="https://cloud.test/hook/v1", token="t1",
        )

        for n in (2, 3, 4):
            fake = _FakeCloud(
                get_responses=[_listing_response([])],
                post_responses=[
                    _registration_response(f"https://cloud.test/hook/v{n}", f"t{n}")
                ],
            )
            patcher = _patch_cloud(fake)
            try:
                await _run_reconcile(session_factory)
            finally:
                patcher.stop()

        value = await self._changes(session_factory)
        assert len(value["changes"]) == 1
        assert value["changes"][0]["trigger_id"] == str(trigger_id)
        assert value["changes"][0]["new_url"] == "https://cloud.test/hook/v4"

    @pytest.mark.asyncio
    async def test_dismissal_clears_the_record(self, db_session):
        from cloud_endpoints import clear_url_changes

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        await _add_trigger(
            session_factory, name="Jira Ack", source="jira",
            url="https://cloud.test/hook/old", token="dead",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[_registration_response("https://cloud.test/hook/new", "new")],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        assert await self._changes(session_factory) is not None
        async with session_factory() as s:
            await clear_url_changes(s)
        assert await self._changes(session_factory) is None


class TestResponseShapeHardening:
    """Review follow-up: malformed 2xx bodies, and not leaking tokens to logs."""

    @staticmethod
    def _post_resp(payload):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = payload
        return resp

    @pytest.mark.parametrize("payload", [
        None,
        ["not", "a", "dict"],
        {"endpoints": "not-a-list"},
        {"endpoints": ["stray string"]},
        {"endpoints": [{"type": "webhook", "url": 123, "token": 456}]},
    ])
    @pytest.mark.asyncio
    async def test_malformed_registration_response_is_a_clean_failure(self, db_session, payload):
        """It must return False, not raise — reconciliation's clearing depends on it."""
        from cloud_endpoints import register_webhook_trigger_with_cloud
        from models import WebhookTrigger

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Shape", source="jira",
            url="https://cloud.test/hook/old", token="dead",
        )

        fake = _FakeCloud(post_responses=[self._post_resp(payload)])
        patcher = _patch_cloud(fake)
        try:
            async with session_factory() as session:
                trigger = (await session.execute(
                    select(WebhookTrigger).where(WebhookTrigger.id == trigger_id)
                )).scalar_one()
                result = await register_webhook_trigger_with_cloud(trigger, session)
        finally:
            patcher.stop()

        assert result is False

    @pytest.mark.asyncio
    async def test_a_malformed_response_still_clears_the_stale_url(self, db_session):
        """The whole point: a URL known not to work must stop being displayed."""
        from models import Setting

        _, session_factory = db_session
        await _seed_cloud_credentials(session_factory)
        trigger_id = await _add_trigger(
            session_factory, name="Jira Shape2", source="jira",
            url="https://cloud.test/hook/dead", token="dead-token",
        )

        fake = _FakeCloud(
            get_responses=[_listing_response([])],
            post_responses=[self._post_resp(["unexpected", "list"])],
        )
        patcher = _patch_cloud(fake)
        try:
            await _run_reconcile(session_factory)
        finally:
            patcher.stop()

        trigger = await _reload(session_factory, trigger_id)
        assert trigger.cloud_webhook_url is None
        async with session_factory() as s:
            err = (await s.execute(
                select(Setting).where(Setting.key == "cloud_endpoint_error")
            )).scalar_one_or_none()
        assert err is not None, "a malformed response must still record a reason"

    @pytest.mark.asyncio
    async def test_a_malformed_listing_does_not_log_endpoint_tokens(self, caplog):
        """Endpoint tokens are capabilities — /hook/<token> is the address."""
        import logging

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = [
            {"token": "super-secret-token", "url": "https://cloud.test/hook/super-secret-token"},
            "malformed entry",
        ]

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with caplog.at_level(logging.ERROR, logger="cloud_endpoints"):
                result = await check_existing_endpoints(
                    cloud_creds={"access_token": "t"},
                    cloud_service_url="https://cloud.test",
                    integration="jira",
                )

        assert result is None
        assert "super-secret-token" not in caplog.text
        assert "jira" in caplog.text
