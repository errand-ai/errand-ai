"""Tests for the Slack outbound-message allowlist."""
from unittest.mock import AsyncMock, patch

import pytest

from platforms.slack import allowlist, identity


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


@pytest.mark.asyncio
async def test_empty_allowlist_permits_all():
    assert await allowlist.check_outbound_allowlist("xoxb", "C123", []) is True
    assert await allowlist.check_outbound_allowlist("xoxb", "U456", None) is True


@pytest.mark.asyncio
async def test_allowlist_with_id_permits_matching_id():
    # No Slack call needed when allowlist entry is itself an ID
    with patch("platforms.slack.identity.AsyncWebClient") as ctor:
        result = await allowlist.check_outbound_allowlist(
            "xoxb", "C0123ABCDEF", ["C0123ABCDEF"],
        )
    assert result is True
    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_allowlist_rejects_unlisted_target():
    with patch("platforms.slack.identity.AsyncWebClient") as ctor:
        result = await allowlist.check_outbound_allowlist(
            "xoxb", "C9999AAAAA", ["C0123ABCDEF"],
        )
    assert result is False
    ctor.assert_not_called()


@pytest.mark.asyncio
async def test_allowlist_authored_with_name_matches_target_supplied_as_id():
    # Allowlist contains "#ai-agent"; target is the ID it resolves to
    client = AsyncMock()
    client.conversations_list = AsyncMock(return_value={
        "channels": [{"id": "C222", "name": "ai-agent"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await allowlist.check_outbound_allowlist(
            "xoxb", "C222", ["#ai-agent"],
        )
    assert result is True


@pytest.mark.asyncio
async def test_allowlist_skips_unresolvable_entries():
    # Allowlist entry that cannot be resolved doesn't crash; non-matching id rejected
    client = AsyncMock()
    client.conversations_list = AsyncMock(return_value={"channels": [], "response_metadata": {"next_cursor": ""}})
    client.users_list = AsyncMock(return_value={"members": [], "response_metadata": {"next_cursor": ""}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await allowlist.check_outbound_allowlist(
            "xoxb", "C9999", ["nonexistent-channel-or-user"],
        )
    assert result is False


def test_redact_for_log_passes_safe_identifiers():
    assert allowlist._redact_for_log("#ai-agent") == "#ai-agent"
    assert allowlist._redact_for_log("@rob") == "@rob"
    assert allowlist._redact_for_log("C0123ABCDE") == "C0123ABCDE"
    assert allowlist._redact_for_log("U0123ABCDE") == "U0123ABCDE"


def test_redact_for_log_strips_email_local_part():
    out = allowlist._redact_for_log("rob@example.com")
    assert "rob" not in out
    assert "<email:example.com>" == out


def test_redact_for_log_opaque_for_bare_strings():
    # Bare strings (could be a username or anything) — never log raw
    out = allowlist._redact_for_log("possibly-pii-bare-string")
    assert out.startswith("<opaque:")
    assert "possibly-pii" not in out


def test_redact_for_log_handles_empty():
    assert allowlist._redact_for_log("") == "<empty>"


@pytest.mark.asyncio
async def test_unresolvable_entry_warning_does_not_leak_email(caplog):
    import logging
    client = AsyncMock()
    # Force resolution to fail (no match)
    client.users_lookupByEmail = AsyncMock(return_value={"user": {}})
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client), \
            caplog.at_level(logging.WARNING, logger="platforms.slack.allowlist"):
        await allowlist.check_outbound_allowlist(
            "xoxb", "C9999", ["leaky.user@example.com"],
        )
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs, "expected a warning log"
    assert all("leaky.user" not in m for m in msgs)
    # Assert against the full redacted token (not just the bare domain) so this
    # check is a log-format assertion, not something a static analyzer could
    # mistake for a hostname allowlist check.
    assert any("<email:example.com>" in m for m in msgs)


@pytest.mark.asyncio
async def test_allowlist_user_match_by_username():
    client = AsyncMock()
    client.users_list = AsyncMock(return_value={
        "members": [{"id": "U777", "name": "rob"}],
        "response_metadata": {"next_cursor": ""},
    })
    with patch("platforms.slack.identity.AsyncWebClient", return_value=client):
        result = await allowlist.check_outbound_allowlist(
            "xoxb", "U777", ["@rob"],
        )
    assert result is True
