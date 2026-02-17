"""Tests for SlackClient (httpx-based Slack API wrapper)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from platforms.slack.client import SlackClient


@pytest.fixture
def slack_client():
    return SlackClient()


def _mock_httpx_response(json_data, status_code=200):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


class TestPostMessage:
    @pytest.mark.asyncio
    async def test_post_message_success(self, slack_client):
        mock_resp = _mock_httpx_response({"ok": True, "channel": "C123", "ts": "111.222"})

        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await slack_client.post_message("xoxb-token", "C123", [{"type": "section"}])

        assert result["ok"] is True
        assert result["ts"] == "111.222"
        instance.post.assert_called_once()
        call_kwargs = instance.post.call_args
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer xoxb-token"
        assert call_kwargs[1]["json"]["channel"] == "C123"

    @pytest.mark.asyncio
    async def test_post_message_sends_correct_blocks(self, slack_client):
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": "Hello"}}]
        mock_resp = _mock_httpx_response({"ok": True, "channel": "C456", "ts": "333.444"})

        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await slack_client.post_message("xoxb-token", "C456", blocks)

        body = instance.post.call_args[1]["json"]
        assert body["channel"] == "C456"
        assert body["blocks"] == blocks

    @pytest.mark.asyncio
    async def test_post_message_api_error_logged(self, slack_client):
        mock_resp = _mock_httpx_response({"ok": False, "error": "channel_not_found"})

        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await slack_client.post_message("xoxb-token", "C999", [])

        assert result["ok"] is False
        assert result["error"] == "channel_not_found"


class TestUpdateMessage:
    @pytest.mark.asyncio
    async def test_update_message_success(self, slack_client):
        mock_resp = _mock_httpx_response({"ok": True, "channel": "C123", "ts": "111.222"})

        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await slack_client.update_message("xoxb-token", "C123", "111.222", [{"type": "section"}])

        assert result["ok"] is True
        call_kwargs = instance.post.call_args
        assert call_kwargs[1]["headers"]["Authorization"] == "Bearer xoxb-token"

    @pytest.mark.asyncio
    async def test_update_message_sends_correct_body(self, slack_client):
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Updated"}}]
        mock_resp = _mock_httpx_response({"ok": True, "channel": "C123", "ts": "111.222"})

        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await slack_client.update_message("xoxb-token", "C123", "111.222", blocks)

        body = instance.post.call_args[1]["json"]
        assert body["channel"] == "C123"
        assert body["ts"] == "111.222"
        assert body["blocks"] == blocks

    @pytest.mark.asyncio
    async def test_update_message_api_error_logged(self, slack_client):
        mock_resp = _mock_httpx_response({"ok": False, "error": "message_not_found"})

        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await slack_client.update_message("xoxb-token", "C123", "999.999", [])

        assert result["ok"] is False
        assert result["error"] == "message_not_found"


class TestPostResponseUrl:
    @pytest.mark.asyncio
    async def test_post_response_url_sends_ephemeral(self, slack_client):
        mock_resp = _mock_httpx_response({})
        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await slack_client.post_response_url(
                "https://hooks.slack.com/actions/T1/B1/test",
                [{"type": "section", "text": {"type": "mrkdwn", "text": "hello"}}],
            )

        call_args = instance.post.call_args
        assert call_args[0][0] == "https://hooks.slack.com/actions/T1/B1/test"
        body = call_args[1]["json"]
        assert body["response_type"] == "ephemeral"
        assert body["replace_original"] is False
        assert len(body["blocks"]) == 1

    @pytest.mark.asyncio
    async def test_post_response_url_in_channel(self, slack_client):
        mock_resp = _mock_httpx_response({})
        with patch("platforms.slack.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await slack_client.post_response_url(
                "https://hooks.slack.com/actions/T1/B1/test",
                [{"type": "section"}],
                ephemeral=False,
            )

        body = instance.post.call_args[1]["json"]
        assert body["response_type"] == "in_channel"
