"""Tests for cloud endpoint management."""
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
