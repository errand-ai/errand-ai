"""Tests for the slack outbound posting orchestration (auto-join, error mapping, rate-limit translation)."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from platforms.slack import identity, outbound
from platforms.slack.client import text_to_blocks


def _make_response(status_code=200, headers=None):
    """Build a stub httpx.Response for HTTPStatusError construction."""
    request = httpx.Request("POST", "https://slack.com/api/chat.postMessage")
    return httpx.Response(status_code, headers=headers or {}, request=request)


@pytest.mark.asyncio
async def test_post_success_returns_canonical_shape():
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": True, "channel": "C123", "ts": "1.2"})
    result = await outbound.post_message_with_policy(
        client, "xoxb", "C123", text="hello",
    )
    assert result == {"ok": True, "channel": "C123", "ts": "1.2"}
    # text-only call should produce blocks via the canonical text_to_blocks helper
    args, kwargs = client.post_message.call_args
    assert kwargs["blocks"] == text_to_blocks("hello")
    assert kwargs["text"] == "hello"


@pytest.mark.asyncio
async def test_post_with_explicit_blocks_uses_them():
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": True, "channel": "C123", "ts": "1.2"})
    custom = [{"type": "header", "text": {"type": "plain_text", "text": "hi"}}]
    await outbound.post_message_with_policy(
        client, "xoxb", "C123", text="fallback", blocks=custom,
    )
    args, kwargs = client.post_message.call_args
    assert kwargs["blocks"] == custom


@pytest.mark.asyncio
async def test_thread_ts_passed_through():
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": True, "channel": "C123", "ts": "1.3"})
    await outbound.post_message_with_policy(
        client, "xoxb", "C123", text="reply", thread_ts="1.0",
    )
    args, kwargs = client.post_message.call_args
    assert kwargs["thread_ts"] == "1.0"


@pytest.mark.asyncio
async def test_auto_join_success_path():
    client = MagicMock()
    client.post_message = AsyncMock(side_effect=[
        {"ok": False, "error": "not_in_channel"},
        {"ok": True, "channel": "C123", "ts": "1.5"},
    ])
    client.join_channel = AsyncMock(return_value={"ok": True})
    result = await outbound.post_message_with_policy(
        client, "xoxb", "C123", text="hi",
    )
    assert result == {"ok": True, "channel": "C123", "ts": "1.5"}
    client.join_channel.assert_awaited_once_with("xoxb", "C123")
    assert client.post_message.await_count == 2


@pytest.mark.asyncio
async def test_auto_join_failure_path():
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": False, "error": "not_in_channel"})
    client.join_channel = AsyncMock(return_value={"ok": False, "error": "missing_scope"})
    result = await outbound.post_message_with_policy(
        client, "xoxb", "C123", text="hi",
    )
    assert result["ok"] is False
    assert "auto-join failed" in result["error"]
    assert "missing_scope" in result["error"]


@pytest.mark.asyncio
async def test_private_channel_skip_path():
    # G-prefix (private) channel — must NOT attempt auto-join
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": False, "error": "not_in_channel"})
    client.join_channel = AsyncMock()
    result = await outbound.post_message_with_policy(
        client, "xoxb", "G999", text="hi",
    )
    assert result == {"ok": False, "channel": "G999", "ts": "", "error": "not_in_channel"}
    client.join_channel.assert_not_called()


@pytest.mark.asyncio
async def test_dm_skip_path():
    # D-prefix (DM) — must NOT attempt auto-join
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": False, "error": "not_in_channel"})
    client.join_channel = AsyncMock()
    result = await outbound.post_message_with_policy(
        client, "xoxb", "D777", text="hi",
    )
    assert result["error"] == "not_in_channel"
    client.join_channel.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_translated_to_structured_error():
    client = MagicMock()
    err = httpx.HTTPStatusError(
        "429",
        request=httpx.Request("POST", "https://slack.com/api/chat.postMessage"),
        response=_make_response(429, headers={"Retry-After": "30"}),
    )
    client.post_message = AsyncMock(side_effect=err)
    result = await outbound.post_message_with_policy(
        client, "xoxb", "C123", text="hi",
    )
    assert result == {
        "ok": False,
        "channel": "C123",
        "ts": "",
        "error": "rate_limited; retry after 30 seconds",
    }


@pytest.mark.asyncio
async def test_channel_not_found_evicts_cache(monkeypatch):
    evicted = []

    def fake_evict(name_or_id):
        evicted.append(name_or_id)

    monkeypatch.setattr(outbound, "evict_channel_cache_entry", fake_evict)

    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": False, "error": "channel_not_found"})
    result = await outbound.post_message_with_policy(
        client, "xoxb", "C404", text="hi",
    )
    assert result == {"ok": False, "channel": "C404", "ts": "", "error": "channel_not_found"}
    assert evicted == ["C404"]


@pytest.mark.asyncio
async def test_stale_channel_resolves_after_eviction():
    """End-to-end: first post hits channel_not_found, eviction clears the cache,
    a fresh resolution returns the new id, and the second post succeeds."""
    # Prime the cache with a stale mapping
    identity._channel_name_cache.clear()
    identity._channel_name_cache["ai-agent"] = ("C_OLD", __import__("time").time())

    # First post against the stale id fails with channel_not_found and triggers eviction
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": False, "error": "channel_not_found"})
    result = await outbound.post_message_with_policy(
        client, "xoxb", "C_OLD", text="hi",
    )
    assert result["error"] == "channel_not_found"
    assert "ai-agent" not in identity._channel_name_cache

    # Now a fresh resolve_slack_target call hits Slack and gets the new id
    fake_slack = AsyncMock()
    fake_slack.conversations_list = AsyncMock(return_value={
        "channels": [{"id": "C_NEW", "name": "ai-agent"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=fake_slack):
        kind, resolved = await identity.resolve_slack_target("#ai-agent", "xoxb")
    assert (kind, resolved) == ("channel", "C_NEW")

    identity._channel_name_cache.clear()


@pytest.mark.asyncio
async def test_arbitrary_slack_error_surfaced_verbatim():
    client = MagicMock()
    client.post_message = AsyncMock(return_value={"ok": False, "error": "user_not_found"})
    result = await outbound.post_message_with_policy(
        client, "xoxb", "U999", text="hi",
    )
    assert result["error"] == "user_not_found"
