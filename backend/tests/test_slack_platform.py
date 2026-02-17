"""Tests for SlackPlatform class."""
from unittest.mock import AsyncMock, patch

import pytest

from platforms.base import PlatformCapability
from platforms.slack import SlackPlatform


def test_slack_info():
    slack = SlackPlatform()
    info = slack.info()
    assert info.id == "slack"
    assert info.label == "Slack"
    assert PlatformCapability.COMMANDS in info.capabilities
    assert PlatformCapability.WEBHOOKS in info.capabilities
    schema_keys = [f["key"] for f in info.credential_schema]
    assert schema_keys == ["bot_token", "signing_secret"]
    for field in info.credential_schema:
        assert field["type"] == "password"
        assert field["required"] is True


@pytest.mark.asyncio
async def test_verify_credentials_success():
    slack = SlackPlatform()

    with patch("slack_sdk.web.async_client.AsyncWebClient") as MockClient:
        MockClient.return_value.auth_test = AsyncMock(return_value={"ok": True})
        result = await slack.verify_credentials({
            "bot_token": "xoxb-test-token",
            "signing_secret": "test-secret",
        })

    assert result is True
    MockClient.assert_called_once_with(token="xoxb-test-token")


@pytest.mark.asyncio
async def test_verify_credentials_failure():
    slack = SlackPlatform()

    with patch("slack_sdk.web.async_client.AsyncWebClient") as MockClient:
        MockClient.return_value.auth_test = AsyncMock(side_effect=Exception("invalid_auth"))
        result = await slack.verify_credentials({
            "bot_token": "xoxb-bad-token",
            "signing_secret": "test-secret",
        })

    assert result is False
