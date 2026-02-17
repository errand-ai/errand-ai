"""Tests for Slack Events API URL verification."""
from platforms.slack.verification import handle_url_verification


def test_url_verification_returns_challenge():
    payload = {
        "type": "url_verification",
        "challenge": "abc123xyz",
        "token": "legacy_token",
    }
    result = handle_url_verification(payload)
    assert result == {"challenge": "abc123xyz"}


def test_url_verification_empty_challenge():
    payload = {"type": "url_verification"}
    result = handle_url_verification(payload)
    assert result == {"challenge": ""}


def test_non_verification_event_returns_none():
    payload = {
        "type": "event_callback",
        "event": {"type": "message", "text": "hello"},
    }
    result = handle_url_verification(payload)
    assert result is None


def test_empty_payload_returns_none():
    result = handle_url_verification({})
    assert result is None
