"""Tests for Jira cloud dispatch routing."""

import pytest

from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")
from cloud_dispatch import dispatch_cloud_webhook


@pytest.mark.asyncio
class TestCloudDispatchJira:
    async def test_jira_webhook_dispatched(self):
        with patch("cloud_dispatch._dispatch_jira_webhook", new_callable=AsyncMock) as mock:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-1",
                "integration": "jira",
                "endpoint_type": "webhook",
                "body": '{"webhookEvent": "issue_created"}',
                "headers": {"X-Hub-Signature": "sha256=abc"},
                "trigger_id": "trigger-uuid",
            })
            mock.assert_called_once()
            args = mock.call_args[0]
            assert isinstance(args[0], bytes)  # body
            assert args[2] == "trigger-uuid"  # trigger_id

    async def test_slack_events_still_routed(self):
        with patch("cloud_dispatch._dispatch_slack", new_callable=AsyncMock) as mock:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-2",
                "integration": "slack",
                "endpoint_type": "events",
                "body": '{"type": "event_callback"}',
            })
            mock.assert_called_once()

    async def test_unknown_integration_logged(self):
        with patch("cloud_dispatch.logger") as mock_logger:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-3",
                "integration": "unknown",
                "endpoint_type": "webhook",
                "body": "{}",
            })
            mock_logger.warning.assert_called()

    async def test_jira_relay_with_missing_trigger(self):
        """Cloud relay discards message when trigger_id not found in DB."""
        from cloud_dispatch import _dispatch_jira_webhook
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("cloud_dispatch.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            # Should return without error (no jira handler called)
            await _dispatch_jira_webhook(
                b'{"test": true}',
                {"X-Hub-Signature": "sha256=abc"},
                "00000000-0000-0000-0000-000000000000",
            )

    async def test_jira_relay_with_disabled_trigger(self):
        """Cloud relay discards message when trigger is disabled."""
        from cloud_dispatch import _dispatch_jira_webhook
        mock_trigger = MagicMock()
        mock_trigger.enabled = False

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trigger
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("cloud_dispatch.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            # Should return without error (no jira handler called)
            await _dispatch_jira_webhook(
                b'{"test": true}',
                {"X-Hub-Signature": "sha256=abc"},
                "00000000-0000-0000-0000-000000000000",
            )

    async def test_jira_relay_with_invalid_uuid(self):
        """Cloud relay discards message when trigger_id is not a valid UUID."""
        from cloud_dispatch import _dispatch_jira_webhook
        # Should return without error — invalid UUID logged and discarded
        await _dispatch_jira_webhook(b'{}', {}, "not-a-uuid")


@pytest.mark.asyncio
class TestCloudEndpointRegistration:
    async def test_register_webhook_trigger_endpoint(self):
        from cloud_endpoints import register_webhook_trigger_endpoint

        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.json.return_value = {"trigger_id": "t1", "url": "https://cloud/webhooks/jira"}

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await register_webhook_trigger_endpoint(
                cloud_creds={"access_token": "tok"},
                cloud_service_url="https://cloud.example.com",
                trigger_id="t1",
                integration="jira",
                webhook_secret="secret",
                label="My Trigger",
            )

        assert result is not None
        assert result["trigger_id"] == "t1"

    async def test_deregister_webhook_trigger_endpoint(self):
        from cloud_endpoints import deregister_webhook_trigger_endpoint

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("cloud_endpoints.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                delete=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            await deregister_webhook_trigger_endpoint(
                cloud_creds={"access_token": "tok"},
                cloud_service_url="https://cloud.example.com",
                trigger_id="t1",
                integration="jira",
            )
            # No exception = success
