"""Tests for Slack user email resolution with caching."""
import time
from unittest.mock import AsyncMock, patch

import pytest

from platforms.slack import identity


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the module-level identity caches before each test."""
    identity._email_cache.clear()
    identity._channel_name_cache.clear()
    identity._user_name_cache.clear()
    identity._dm_channel_cache.clear()
    yield
    identity._email_cache.clear()
    identity._channel_name_cache.clear()
    identity._user_name_cache.clear()
    identity._dm_channel_cache.clear()


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


# --- resolve_slack_target tests --------------------------------------------


def _patch_client(**method_returns):
    """Build a mock AsyncWebClient where each kwarg method is an AsyncMock."""
    client = AsyncMock()
    for name, value in method_returns.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


@pytest.mark.asyncio
async def test_target_channel_id_passes_through():
    # No client should be needed for ID pass-through
    with patch("platforms.slack.identity.AsyncWebClient") as ctor:
        kind, resolved = await identity.resolve_slack_target("C0123ABCDEF", "xoxb-token")
    assert (kind, resolved) == ("channel", "C0123ABCDEF")
    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_target_user_id_passes_through():
    with patch("platforms.slack.identity.AsyncWebClient") as ctor:
        kind, resolved = await identity.resolve_slack_target("U0123ABCDEF", "xoxb-token")
    assert (kind, resolved) == ("user", "U0123ABCDEF")
    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_target_email_resolves_to_user():
    client = _patch_client(users_lookupByEmail={"user": {"id": "U999"}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        kind, resolved = await identity.resolve_slack_target("rob@example.com", "xoxb-token")
    assert (kind, resolved) == ("user", "U999")
    client.users_lookupByEmail.assert_called_once_with(email="rob@example.com")


@pytest.mark.asyncio
async def test_target_channel_name_resolves():
    client = _patch_client(conversations_list={
        "channels": [{"id": "C111", "name": "general"}, {"id": "C222", "name": "ai-agent"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        kind, resolved = await identity.resolve_slack_target("#ai-agent", "xoxb-token")
    assert (kind, resolved) == ("channel", "C222")


@pytest.mark.asyncio
async def test_target_username_resolves():
    client = _patch_client(users_list={
        "members": [{"id": "U001", "name": "alice"}, {"id": "U002", "name": "rob"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        kind, resolved = await identity.resolve_slack_target("@rob", "xoxb-token")
    assert (kind, resolved) == ("user", "U002")


@pytest.mark.asyncio
async def test_target_bare_name_ambiguous_raises():
    # Bare name matches both a channel and a user
    client = AsyncMock()
    client.conversations_list = AsyncMock(return_value={
        "channels": [{"id": "C123", "name": "rob"}],
        "response_metadata": {"next_cursor": ""},
    })
    client.users_list = AsyncMock(return_value={
        "members": [{"id": "U777", "name": "rob"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        with pytest.raises(identity.TargetResolutionError, match="Ambiguous"):
            await identity.resolve_slack_target("rob", "xoxb-token")


@pytest.mark.asyncio
async def test_target_bare_name_channel_only():
    client = AsyncMock()
    client.conversations_list = AsyncMock(return_value={
        "channels": [{"id": "C500", "name": "release-notes"}],
        "response_metadata": {"next_cursor": ""},
    })
    client.users_list = AsyncMock(return_value={
        "members": [],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        kind, resolved = await identity.resolve_slack_target("release-notes", "xoxb-token")
    assert (kind, resolved) == ("channel", "C500")


@pytest.mark.asyncio
async def test_target_no_match_raises():
    client = AsyncMock()
    client.conversations_list = AsyncMock(return_value={"channels": [], "response_metadata": {"next_cursor": ""}})
    client.users_list = AsyncMock(return_value={"members": [], "response_metadata": {"next_cursor": ""}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        with pytest.raises(identity.TargetResolutionError, match="No Slack channel or user"):
            await identity.resolve_slack_target("nonexistent", "xoxb-token")


@pytest.mark.asyncio
async def test_channel_name_cache_hit_skips_api():
    identity._channel_name_cache["ai-agent"] = ("C222", time.time())
    with patch("platforms.slack.identity.AsyncWebClient") as ctor:
        kind, resolved = await identity.resolve_slack_target("#ai-agent", "xoxb-token")
    assert (kind, resolved) == ("channel", "C222")
    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_evict_channel_cache_entry_clears_by_id():
    identity._channel_name_cache["old-name"] = ("C123", time.time())
    identity._channel_name_cache["other"] = ("C999", time.time())
    identity.evict_channel_cache_entry("C123")
    assert "old-name" not in identity._channel_name_cache
    assert "other" in identity._channel_name_cache


@pytest.mark.asyncio
async def test_evict_channel_cache_entry_clears_by_name():
    identity._channel_name_cache["ai-agent"] = ("C222", time.time())
    identity.evict_channel_cache_entry("#ai-agent")
    assert "ai-agent" not in identity._channel_name_cache


# --- Cache-on-exception behavior (transient errors must not poison cache) ---


@pytest.mark.asyncio
async def test_email_lookup_does_not_cache_on_exception():
    client = AsyncMock()
    client.users_lookupByEmail = AsyncMock(side_effect=Exception("Slack down"))
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await identity._resolve_user_by_email("a@example.com", "xoxb")
    assert result is None
    assert "email:a@example.com" not in identity._email_cache


@pytest.mark.asyncio
async def test_email_lookup_exception_log_redacts_email(caplog):
    import logging
    client = AsyncMock()
    client.users_lookupByEmail = AsyncMock(side_effect=Exception("Slack down"))
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client), \
            caplog.at_level(logging.ERROR, logger="platforms.slack.identity"):
        await identity._resolve_user_by_email("leaky.user@example.com", "xoxb")

    msgs = [r.getMessage() for r in caplog.records]
    assert msgs, "expected an error log"
    # Local part of the email must NOT appear in operational logs
    assert all("leaky.user" not in m for m in msgs)
    # Domain is logged for triage — assert against the full redacted token
    # (`domain=…`) rather than a bare substring so this is unambiguously a
    # log-format check, not something a static analyzer would treat as a
    # hostname allowlist.
    assert any("domain=example.com" in m for m in msgs)


@pytest.mark.asyncio
async def test_channel_name_lookup_does_not_cache_on_exception():
    client = AsyncMock()
    client.conversations_list = AsyncMock(side_effect=Exception("Slack down"))
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await identity._resolve_channel_by_name("ai-agent", "xoxb")
    assert result is None
    assert "ai-agent" not in identity._channel_name_cache


@pytest.mark.asyncio
async def test_username_lookup_does_not_cache_on_exception():
    client = AsyncMock()
    client.users_list = AsyncMock(side_effect=Exception("Slack down"))
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await identity._resolve_user_by_username("rob", "xoxb")
    assert result is None
    assert "rob" not in identity._user_name_cache


@pytest.mark.asyncio
async def test_email_not_found_is_cached():
    """Successful 'not found' replies SHOULD cache so we don't keep asking."""
    client = AsyncMock()
    client.users_lookupByEmail = AsyncMock(return_value={"user": {}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        await identity._resolve_user_by_email("ghost@example.com", "xoxb")
        await identity._resolve_user_by_email("ghost@example.com", "xoxb")
    assert client.users_lookupByEmail.call_count == 1


# --- open_dm_channel ------------------------------------------------------


@pytest.mark.asyncio
async def test_open_dm_channel_returns_channel_id():
    identity._dm_channel_cache.clear()
    client = AsyncMock()
    client.conversations_open = AsyncMock(return_value={"channel": {"id": "D999"}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await identity.open_dm_channel("U999", "xoxb")
    assert result == "D999"
    client.conversations_open.assert_awaited_once_with(users="U999")


@pytest.mark.asyncio
async def test_open_dm_channel_cached():
    identity._dm_channel_cache.clear()
    identity._dm_channel_cache["U999"] = ("D999", time.time())
    with patch("platforms.slack.identity.AsyncWebClient") as ctor:
        result = await identity.open_dm_channel("U999", "xoxb")
    assert result == "D999"
    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_open_dm_channel_does_not_cache_on_exception():
    identity._dm_channel_cache.clear()
    client = AsyncMock()
    client.conversations_open = AsyncMock(side_effect=Exception("Slack down"))
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await identity.open_dm_channel("U999", "xoxb")
    assert result is None
    assert "U999" not in identity._dm_channel_cache
