"""Tests for the slack_message and slack_reply MCP tool handlers."""
import json
import logging
from unittest.mock import AsyncMock, patch

import pytest

import mcp_server
from platforms.slack import identity


@pytest.fixture(autouse=True)
def clear_caches():
    identity._email_cache.clear()
    identity._channel_name_cache.clear()
    identity._user_name_cache.clear()
    identity._dm_channel_cache.clear()
    yield
    identity._email_cache.clear()
    identity._channel_name_cache.clear()
    identity._user_name_cache.clear()
    identity._dm_channel_cache.clear()


@pytest.fixture
def patched_token():
    """Patch the bot-token loader to return a fixed token."""
    with patch.object(mcp_server, "_load_slack_bot_token", AsyncMock(return_value="xoxb-test")):
        yield


@pytest.fixture
def patched_empty_allowlist():
    with patch.object(mcp_server, "_load_slack_outbound_allowlist", AsyncMock(return_value=[])):
        yield


def _patch_post(return_value):
    """Patch post_message_with_policy to return the given dict."""
    return patch(
        "platforms.slack.outbound.post_message_with_policy",
        AsyncMock(return_value=return_value),
    )


# --- slack_message ---------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_message_post_by_channel_id(patched_token, patched_empty_allowlist):
    with _patch_post({"ok": True, "channel": "C123", "ts": "1.1"}) as mock_post:
        result = await mcp_server.slack_message(target="C0123ABCDE", text="hi")
    parsed = json.loads(result)
    assert parsed == {"ok": True, "channel": "C123", "ts": "1.1"}
    # Resolved id should be the input id, no client construction needed
    args, kwargs = mock_post.await_args
    assert args[2] == "C0123ABCDE"
    assert kwargs["text"] == "hi"


@pytest.mark.asyncio
async def test_slack_message_post_by_channel_name(patched_token, patched_empty_allowlist):
    client = AsyncMock()
    client.conversations_list = AsyncMock(return_value={
        "channels": [{"id": "C500", "name": "ai-agent"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client), \
            _patch_post({"ok": True, "channel": "C500", "ts": "2.2"}) as mock_post:
        result = await mcp_server.slack_message(target="#ai-agent", text="hello")
    assert json.loads(result)["channel"] == "C500"
    args, _ = mock_post.await_args
    assert args[2] == "C500"


@pytest.mark.asyncio
async def test_slack_message_dm_by_user_id_opens_dm_channel(patched_token, patched_empty_allowlist):
    """User targets must be posted to a D… DM channel, opened via conversations.open."""
    with patch("platforms.slack.identity.open_dm_channel", AsyncMock(return_value="D999IM")), \
            _patch_post({"ok": True, "channel": "D999IM", "ts": "3.3"}) as mock_post:
        result = await mcp_server.slack_message(target="U0123ABCDE", text="dm")
    assert json.loads(result)["ok"] is True
    # Post must target the DM channel, not the user ID directly
    args, _ = mock_post.await_args
    assert args[2] == "D999IM"


@pytest.mark.asyncio
async def test_slack_message_dm_open_failure_returns_error(patched_token, patched_empty_allowlist):
    with patch("platforms.slack.identity.open_dm_channel", AsyncMock(return_value=None)), \
            _patch_post({"ok": True}) as mock_post:
        result = await mcp_server.slack_message(target="U0123ABCDE", text="dm")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "could not open DM channel" in parsed["error"]
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_slack_message_dm_by_username(patched_token, patched_empty_allowlist):
    client = AsyncMock()
    client.users_list = AsyncMock(return_value={
        "members": [{"id": "U777", "name": "rob"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client), \
            patch("platforms.slack.identity.open_dm_channel", AsyncMock(return_value="D777")), \
            _patch_post({"ok": True, "channel": "D777", "ts": "4.4"}) as mock_post:
        result = await mcp_server.slack_message(target="@rob", text="hi")
    assert json.loads(result)["channel"] == "D777"
    args, _ = mock_post.await_args
    assert args[2] == "D777"


@pytest.mark.asyncio
async def test_slack_message_dm_by_email(patched_token, patched_empty_allowlist):
    client = AsyncMock()
    client.users_lookupByEmail = AsyncMock(return_value={"user": {"id": "U999"}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client), \
            patch("platforms.slack.identity.open_dm_channel", AsyncMock(return_value="D999")), \
            _patch_post({"ok": True, "channel": "D999", "ts": "5.5"}):
        result = await mcp_server.slack_message(target="rob@example.com", text="hi")
    assert json.loads(result)["channel"] == "D999"


@pytest.mark.asyncio
async def test_slack_message_blocks_only_payload_uses_blocks(patched_token, patched_empty_allowlist):
    custom = [{"type": "header", "text": {"type": "plain_text", "text": "Done"}}]
    with _patch_post({"ok": True, "channel": "C123", "ts": "6.6"}) as mock_post:
        await mcp_server.slack_message(target="C0123ABCDE", text="fallback", blocks=custom)
    _, kwargs = mock_post.await_args
    assert kwargs["blocks"] == custom


@pytest.mark.asyncio
async def test_slack_message_allowlist_rejection(patched_token):
    with patch.object(mcp_server, "_load_slack_outbound_allowlist", AsyncMock(return_value=["C0000AAAAA"])), \
            _patch_post({"ok": True, "channel": "C123", "ts": "x"}) as mock_post:
        result = await mcp_server.slack_message(target="C0123ABCDE", text="hi")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "slack_outbound_allowlist" in parsed["error"]
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_slack_message_no_credentials_returns_error():
    with patch.object(mcp_server, "_load_slack_bot_token", AsyncMock(return_value=None)):
        result = await mcp_server.slack_message(target="C0123ABCDE", text="hi")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "Slack credentials not configured" in parsed["error"]


@pytest.mark.asyncio
async def test_slack_message_resolution_failure_returns_error(patched_token, patched_empty_allowlist):
    client = AsyncMock()
    client.conversations_list = AsyncMock(return_value={"channels": [], "response_metadata": {"next_cursor": ""}})
    client.users_list = AsyncMock(return_value={"members": [], "response_metadata": {"next_cursor": ""}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await mcp_server.slack_message(target="nonexistent", text="hi")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "No Slack channel or user" in parsed["error"]


@pytest.mark.asyncio
async def test_slack_message_empty_target_returns_error():
    result = await mcp_server.slack_message(target="", text="hi")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "target is required" in parsed["error"]


@pytest.mark.asyncio
async def test_slack_message_empty_text_returns_error():
    result = await mcp_server.slack_message(target="C0123ABCDE", text="")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "text is required" in parsed["error"]


# --- slack_reply -----------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_reply_thread_success(patched_token, patched_empty_allowlist):
    with _patch_post({"ok": True, "channel": "C123", "ts": "10.0"}) as mock_post:
        result = await mcp_server.slack_reply(
            channel="C0123ABCDE", thread_ts="9.9", text="part 2",
        )
    parsed = json.loads(result)
    assert parsed == {"ok": True, "channel": "C123", "ts": "10.0"}
    _, kwargs = mock_post.await_args
    assert kwargs["thread_ts"] == "9.9"


@pytest.mark.asyncio
async def test_slack_reply_allowlist_check_on_channel(patched_token):
    with patch.object(mcp_server, "_load_slack_outbound_allowlist", AsyncMock(return_value=["C0000AAAAA"])), \
            _patch_post({"ok": True}) as mock_post:
        result = await mcp_server.slack_reply(
            channel="C0123ABCDE", thread_ts="9.9", text="hi",
        )
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "slack_outbound_allowlist" in parsed["error"]
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_slack_reply_missing_thread_ts_returns_error():
    result = await mcp_server.slack_reply(channel="C0123ABCDE", thread_ts="", text="hi")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "thread_ts is required" in parsed["error"]


@pytest.mark.asyncio
async def test_slack_reply_missing_channel_returns_error():
    result = await mcp_server.slack_reply(channel="", thread_ts="9.9", text="hi")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "channel is required" in parsed["error"]


@pytest.mark.asyncio
async def test_slack_reply_no_credentials_returns_error():
    with patch.object(mcp_server, "_load_slack_bot_token", AsyncMock(return_value=None)):
        result = await mcp_server.slack_reply(channel="C0123ABCDE", thread_ts="9.9", text="hi")
    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "Slack credentials not configured" in parsed["error"]


# --- Token never leaves the server ----------------------------------------


@pytest.mark.asyncio
async def test_bot_token_never_in_tool_response(patched_token, patched_empty_allowlist):
    """The returned JSON must never include the bot token in any field."""
    with _patch_post({"ok": True, "channel": "C123", "ts": "1.1"}):
        result = await mcp_server.slack_message(target="C0123ABCDE", text="hi")
    assert "xoxb-test" not in result
    assert "xoxb" not in result


# --- Audit logging --------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_post_emits_audit_log(patched_token, patched_empty_allowlist, caplog):
    with caplog.at_level(logging.INFO, logger="mcp_server"), \
            _patch_post({"ok": True, "channel": "C500", "ts": "1700000000.000100"}):
        await mcp_server.slack_message(target="C0123ABCDE", text="hi")

    audit = [r for r in caplog.records if "slack outbound" in r.getMessage()]
    assert audit, "expected an audit log entry for the successful post"
    msg = audit[-1].getMessage()
    assert "tool=slack_message" in msg
    assert "kind=channel" in msg
    assert "resolved=C0123ABCDE" in msg
    assert "ts=1700000000.000100" in msg


@pytest.mark.asyncio
async def test_audit_log_does_not_leak_email_target(patched_token, patched_empty_allowlist, caplog):
    """Email targets must not appear in audit logs (PII)."""
    client = AsyncMock()
    client.users_lookupByEmail = AsyncMock(return_value={"user": {"id": "U999"}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client), \
            patch("platforms.slack.identity.open_dm_channel", AsyncMock(return_value="D999")), \
            caplog.at_level(logging.INFO, logger="mcp_server"), \
            _patch_post({"ok": True, "channel": "D999", "ts": "1.1"}):
        await mcp_server.slack_message(target="rob@example.com", text="hi")

    audit_msgs = [r.getMessage() for r in caplog.records if "slack outbound" in r.getMessage()]
    assert audit_msgs, "expected an audit log entry"
    # Resolved id is safe to log; raw email is not
    assert any("resolved=U999" in m for m in audit_msgs)
    assert all("rob@example.com" not in m for m in audit_msgs)


@pytest.mark.asyncio
async def test_failed_post_emits_audit_log(patched_token, patched_empty_allowlist, caplog):
    with caplog.at_level(logging.INFO, logger="mcp_server"), \
            _patch_post({"ok": False, "channel": "C0123ABCDE", "ts": "", "error": "channel_not_found"}):
        await mcp_server.slack_message(target="C0123ABCDE", text="hi")

    audit = [r for r in caplog.records if "slack outbound" in r.getMessage()]
    assert audit, "expected an audit log entry for the failed post"
    msg = audit[-1].getMessage()
    assert "tool=slack_message" in msg
    assert "error=channel_not_found" in msg


@pytest.mark.asyncio
async def test_slack_reply_emits_audit_log_with_thread_ts(patched_token, patched_empty_allowlist, caplog):
    with caplog.at_level(logging.INFO, logger="mcp_server"), \
            _patch_post({"ok": True, "channel": "C123", "ts": "10.0"}):
        await mcp_server.slack_reply(channel="C0123ABCDE", thread_ts="9.9", text="hi")

    audit = [r for r in caplog.records if "slack outbound" in r.getMessage()]
    assert audit
    msg = audit[-1].getMessage()
    assert "tool=slack_reply" in msg
    assert "thread_ts=9.9" in msg
    assert "ts=10.0" in msg


# --- Fail-closed allowlist load + sanitized resolution audit + slack_reply ID validation ---


@pytest.mark.asyncio
async def test_slack_message_fails_closed_when_allowlist_load_fails(patched_token, caplog):
    """If the allowlist setting can't be loaded, refuse to send (don't fall back to unrestricted)."""
    with patch.object(
        mcp_server, "_load_slack_outbound_allowlist",
        AsyncMock(side_effect=mcp_server.AllowlistLoadError("db down")),
    ), caplog.at_level(logging.INFO, logger="mcp_server"), \
            _patch_post({"ok": True}) as mock_post:
        result = await mcp_server.slack_message(target="C0123ABCDE", text="hi")

    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "allowlist unavailable" in parsed["error"]
    mock_post.assert_not_called()
    audit = [r.getMessage() for r in caplog.records if "slack outbound" in r.getMessage()]
    assert any("error=allowlist_load_failed" in m for m in audit)


@pytest.mark.asyncio
async def test_slack_reply_fails_closed_when_allowlist_load_fails(patched_token, caplog):
    with patch.object(
        mcp_server, "_load_slack_outbound_allowlist",
        AsyncMock(side_effect=mcp_server.AllowlistLoadError("db down")),
    ), caplog.at_level(logging.INFO, logger="mcp_server"), \
            _patch_post({"ok": True}) as mock_post:
        result = await mcp_server.slack_reply(channel="C0123ABCDE", thread_ts="9.9", text="hi")

    parsed = json.loads(result)
    assert parsed["ok"] is False
    assert "allowlist unavailable" in parsed["error"]
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_resolution_failure_audit_log_redacts_email(patched_token, patched_empty_allowlist, caplog):
    """A failed email resolution emits a sanitized audit code, not the raw email."""
    client = AsyncMock()
    client.users_lookupByEmail = AsyncMock(return_value={"user": {}})  # successful "not found"
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client), \
            caplog.at_level(logging.INFO, logger="mcp_server"):
        result = await mcp_server.slack_message(target="ghost@example.com", text="hi")

    parsed = json.loads(result)
    assert parsed["ok"] is False
    # Detailed message goes to the runner
    assert "ghost@example.com" in parsed["error"] or "No Slack user found" in parsed["error"]
    # Audit log must NOT contain the email
    audit = [r.getMessage() for r in caplog.records if "slack outbound" in r.getMessage()]
    assert audit
    assert all("ghost@example.com" not in m for m in audit)
    assert any("error=resolution_failed" in m for m in audit)


@pytest.mark.asyncio
async def test_slack_reply_rejects_non_id_channel():
    """slack_reply requires a conversation ID; #name or @user would silently fail downstream."""
    for bad in ("#general", "@rob", "general", "rob@example.com"):
        result = await mcp_server.slack_reply(channel=bad, thread_ts="9.9", text="hi")
        parsed = json.loads(result)
        assert parsed["ok"] is False, f"expected rejection for channel={bad!r}"
        assert "conversation ID" in parsed["error"]


@pytest.mark.asyncio
async def test_slack_reply_accepts_dm_and_private_channel_ids(patched_token, patched_empty_allowlist):
    """D… (DM) and G… (private) IDs must also be accepted, not just C… ."""
    for chan in ("C0123ABCDE", "D0123ABCDE", "G0123ABCDE"):
        with _patch_post({"ok": True, "channel": chan, "ts": "1.1"}):
            result = await mcp_server.slack_reply(channel=chan, thread_ts="9.9", text="hi")
        assert json.loads(result)["ok"] is True, f"expected acceptance for channel={chan!r}"


@pytest.mark.asyncio
async def test_audit_log_includes_client_id_from_header(patched_token, patched_empty_allowlist, caplog):
    """When ctx supplies an X-Client-Id header (e.g. from task-runner), audit log
    records it so per-task attribution is possible."""
    fake_request = type("R", (), {"headers": {"x-client-id": "task:abc-123"}})()
    fake_ctx = type("Ctx", (), {
        "request_context": type("RC", (), {"request": fake_request})(),
    })()

    with caplog.at_level(logging.INFO, logger="mcp_server"), \
            _patch_post({"ok": True, "channel": "C123", "ts": "1.1"}):
        await mcp_server.slack_message(target="C0123ABCDE", text="hi", ctx=fake_ctx)

    audit = [r for r in caplog.records if "slack outbound" in r.getMessage()]
    assert audit
    assert "client=task:abc-123" in audit[-1].getMessage()
