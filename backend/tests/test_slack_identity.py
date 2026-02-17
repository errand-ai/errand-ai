"""Tests for Slack user email resolution with caching."""
import time
from unittest.mock import AsyncMock, patch

import pytest

from platforms.slack import identity


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the module-level email cache before each test."""
    identity._email_cache.clear()
    yield
    identity._email_cache.clear()


def _mock_client(email: str | None = "user@example.com"):
    """Create a mock AsyncWebClient that returns the given email."""
    mock_client = AsyncMock()
    mock_client.users_info = AsyncMock(return_value={
        "user": {
            "profile": {"email": email} if email else {"display_name": "test"}
        }
    })
    return mock_client


@pytest.mark.asyncio
async def test_cache_miss_calls_api():
    mock = _mock_client("alice@example.com")
    with patch("platforms.slack.identity.AsyncWebClient", return_value=mock):
        result = await identity.resolve_slack_email("U123", "xoxb-token")

    assert result == "alice@example.com"
    mock.users_info.assert_called_once_with(user="U123")


@pytest.mark.asyncio
async def test_cache_hit_skips_api():
    identity._email_cache["U123"] = ("cached@example.com", time.time())

    mock = _mock_client()
    with patch("platforms.slack.identity.AsyncWebClient", return_value=mock):
        result = await identity.resolve_slack_email("U123", "xoxb-token")

    assert result == "cached@example.com"
    mock.users_info.assert_not_called()


@pytest.mark.asyncio
async def test_none_values_are_cached():
    mock = _mock_client(email=None)
    with patch("platforms.slack.identity.AsyncWebClient", return_value=mock):
        result1 = await identity.resolve_slack_email("U456", "xoxb-token")
        result2 = await identity.resolve_slack_email("U456", "xoxb-token")

    assert result1 is None
    assert result2 is None
    # API should only be called once — second call uses cache
    assert mock.users_info.call_count == 1


@pytest.mark.asyncio
async def test_cache_expiry_triggers_fresh_call():
    # Seed cache with expired entry
    identity._email_cache["U789"] = ("old@example.com", time.time() - 3700)

    mock = _mock_client("new@example.com")
    with patch("platforms.slack.identity.AsyncWebClient", return_value=mock):
        result = await identity.resolve_slack_email("U789", "xoxb-token")

    assert result == "new@example.com"
    mock.users_info.assert_called_once_with(user="U789")


@pytest.mark.asyncio
async def test_api_error_returns_none():
    mock = AsyncMock()
    mock.users_info = AsyncMock(side_effect=Exception("Slack API down"))
    with patch("platforms.slack.identity.AsyncWebClient", return_value=mock):
        result = await identity.resolve_slack_email("UERR", "xoxb-token")

    assert result is None
    # Errors should NOT be cached (no entry in cache)
    assert "UERR" not in identity._email_cache
