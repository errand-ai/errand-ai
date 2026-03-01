"""Tests for cloud webhook dispatcher."""
import pytest
from unittest.mock import AsyncMock, patch

from cloud_dispatch import dispatch_cloud_webhook


class TestDispatchRouting:
    @pytest.mark.asyncio
    async def test_slack_events_routed_correctly(self):
        with patch("platforms.slack.routes.process_slack_event", new_callable=AsyncMock) as mock_handler:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-1",
                "integration": "slack",
                "endpoint_type": "events",
                "body": '{"type": "event_callback", "event": {"type": "app_mention"}}',
            })
            mock_handler.assert_called_once()
            body = mock_handler.call_args[0][0]
            assert b"event_callback" in body

    @pytest.mark.asyncio
    async def test_slack_commands_routed_correctly(self):
        with patch("platforms.slack.routes.process_slack_command", new_callable=AsyncMock) as mock_handler, \
             patch("cloud_dispatch.async_session") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-2",
                "integration": "slack",
                "endpoint_type": "commands",
                "body": "text=new+Buy+groceries&user_id=U123",
            })
            mock_handler.assert_called_once()
            # Should pass response_url_callback="cloud"
            assert mock_handler.call_args.kwargs["response_url_callback"] == "cloud"

    @pytest.mark.asyncio
    async def test_slack_interactivity_routed_correctly(self):
        with patch("platforms.slack.routes.process_slack_interaction", new_callable=AsyncMock) as mock_handler, \
             patch("cloud_dispatch.async_session") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-3",
                "integration": "slack",
                "endpoint_type": "interactivity",
                "body": "payload={}",
            })
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_integration_logs_warning(self):
        with patch("cloud_dispatch.logger") as mock_logger:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-4",
                "integration": "github",
                "endpoint_type": "events",
                "body": "{}",
            })
            mock_logger.warning.assert_called_once()
            assert "Unknown" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_slack_events_passes_body_as_bytes(self):
        """Cloud dispatcher converts string body to bytes for handler compatibility."""
        with patch("platforms.slack.routes.process_slack_event", new_callable=AsyncMock) as mock_handler:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-bytes",
                "integration": "slack",
                "endpoint_type": "events",
                "body": '{"type": "event_callback"}',
            })
            body_arg = mock_handler.call_args[0][0]
            assert isinstance(body_arg, bytes)
            assert b"event_callback" in body_arg

    @pytest.mark.asyncio
    async def test_slack_commands_creates_session_for_handler(self):
        """Cloud dispatcher creates a database session for command handlers."""
        with patch("platforms.slack.routes.process_slack_command", new_callable=AsyncMock) as mock_handler, \
             patch("cloud_dispatch.async_session") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-session",
                "integration": "slack",
                "endpoint_type": "commands",
                "body": "text=test&user_id=U123",
            })

            # Verify session was passed to handler
            assert mock_handler.call_args[0][1] == mock_session

    @pytest.mark.asyncio
    async def test_unknown_slack_endpoint_type_logs_warning(self):
        """Unknown Slack endpoint types should log a warning."""
        with patch("cloud_dispatch.logger") as mock_logger:
            await dispatch_cloud_webhook({
                "type": "webhook",
                "id": "msg-unknown",
                "integration": "slack",
                "endpoint_type": "oauth",
                "body": "{}",
            })
            mock_logger.warning.assert_called_once()
            assert "Unknown Slack" in mock_logger.warning.call_args[0][0]
