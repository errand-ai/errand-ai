"""Tests for GitHub cloud dispatch routing."""

import pytest

from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture(autouse=True)
def _ensure_encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "QqXQtnJMYRkG519FlL64LIGn3R_DvpZfeGgrWcHJV_w=")


from cloud_dispatch import dispatch_cloud_webhook, _dispatch_github_webhook


@pytest.mark.asyncio
class TestCloudDispatchGitHub:
    async def test_github_webhook_dispatched(self):
        """2.1 GitHub webhook relay dispatches to handler with valid trigger_id and signature."""
        with patch("cloud_dispatch._dispatch_github_webhook", new_callable=AsyncMock) as mock:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-1",
                "integration": "github",
                "endpoint_type": "webhook",
                "body": '{"action": "opened"}',
                "headers": {"x-hub-signature-256": "sha256=abc"},
                "trigger_id": "00000000-0000-0000-0000-000000000001",
            })
            mock.assert_called_once()
            args = mock.call_args[0]
            assert isinstance(args[0], bytes)  # body
            assert args[2] == "00000000-0000-0000-0000-000000000001"  # trigger_id

    async def test_missing_trigger_id(self):
        """2.2 Missing trigger_id logs warning and discards."""
        with patch("cloud_dispatch.logger") as mock_logger:
            await _dispatch_github_webhook(b'{}', {}, None)
            mock_logger.warning.assert_called()
            assert "missing trigger_id" in mock_logger.warning.call_args[0][0].lower()

    async def test_invalid_uuid_trigger_id(self):
        """2.3 Invalid (non-UUID) trigger_id logs warning and discards."""
        with patch("cloud_dispatch.logger") as mock_logger:
            await _dispatch_github_webhook(b'{}', {}, "not-a-uuid")
            mock_logger.warning.assert_called()
            assert "invalid trigger_id" in mock_logger.warning.call_args[0][0].lower()

    async def test_trigger_not_found(self):
        """2.4 Trigger not found logs warning and discards."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("cloud_dispatch.async_session") as mock_session_ctx, \
             patch("cloud_dispatch.logger") as mock_logger:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await _dispatch_github_webhook(
                b'{"test": true}',
                {"x-hub-signature-256": "sha256=abc"},
                "00000000-0000-0000-0000-000000000000",
            )
            mock_logger.warning.assert_called()
            assert "not found" in mock_logger.warning.call_args[0][0].lower()

    async def test_disabled_trigger(self):
        """2.5 Disabled trigger logs warning and discards."""
        mock_trigger = MagicMock()
        mock_trigger.enabled = False

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trigger
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("cloud_dispatch.async_session") as mock_session_ctx, \
             patch("cloud_dispatch.logger") as mock_logger:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await _dispatch_github_webhook(
                b'{"test": true}',
                {"x-hub-signature-256": "sha256=abc"},
                "00000000-0000-0000-0000-000000000000",
            )
            mock_logger.warning.assert_called()
            assert "disabled" in mock_logger.warning.call_args[0][0].lower()

    async def test_hmac_reverification_failure(self):
        """2.6 HMAC re-verification failure discards message."""
        mock_trigger = MagicMock()
        mock_trigger.enabled = True
        mock_trigger.webhook_secret = "encrypted-secret"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trigger
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("cloud_dispatch.async_session") as mock_session_ctx, \
             patch("cloud_dispatch.logger") as mock_logger, \
             patch("platforms.credentials.decrypt", return_value={"secret": "the-secret"}), \
             patch("webhook_receiver._verify_hmac", return_value=False):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await _dispatch_github_webhook(
                b'{"test": true}',
                {"x-hub-signature-256": "sha256=bad"},
                "00000000-0000-0000-0000-000000000000",
            )
            mock_logger.warning.assert_called()
            assert "hmac" in mock_logger.warning.call_args[0][0].lower()

    async def test_missing_signature_header_with_secret(self):
        """2.7 Missing signature header with secret-bearing trigger discards message."""
        mock_trigger = MagicMock()
        mock_trigger.enabled = True
        mock_trigger.webhook_secret = "encrypted-secret"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_trigger
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("cloud_dispatch.async_session") as mock_session_ctx, \
             patch("cloud_dispatch.logger") as mock_logger:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await _dispatch_github_webhook(
                b'{"test": true}',
                {},  # no signature header
                "00000000-0000-0000-0000-000000000000",
            )
            mock_logger.warning.assert_called()
            assert "no signature" in mock_logger.warning.call_args[0][0].lower()
