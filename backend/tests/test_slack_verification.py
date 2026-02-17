"""Tests for Slack request signature verification."""
import hashlib
import hmac
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, HTTPException

from platforms.slack.verification import verify_slack_request


def _make_signature(signing_secret: str, timestamp: str, body: str) -> str:
    basestring = f"v0:{timestamp}:{body}"
    return "v0=" + hmac.new(
        signing_secret.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()


@pytest.fixture
def mock_credentials():
    """Patch load_credentials to return test signing secret."""
    with patch("platforms.slack.verification.load_credentials") as mock:
        mock.return_value = {"signing_secret": "test_secret", "bot_token": "xoxb-test"}
        yield mock


@pytest.fixture
def mock_no_credentials():
    """Patch load_credentials to return None (no Slack configured)."""
    with patch("platforms.slack.verification.load_credentials") as mock:
        mock.return_value = None
        yield mock


def _make_request(body: str, timestamp: str | None = None, signature: str | None = None):
    """Build a mock Request with the given body, headers."""
    request = AsyncMock()
    request.body = AsyncMock(return_value=body.encode())

    headers = {}
    if timestamp is not None:
        headers["X-Slack-Request-Timestamp"] = timestamp
    if signature is not None:
        headers["X-Slack-Signature"] = signature
    request.headers = headers

    return request


@pytest.mark.asyncio
async def test_valid_signature(mock_credentials):
    ts = str(int(time.time()))
    body = "token=abc&command=%2Ftask"
    sig = _make_signature("test_secret", ts, body)
    request = _make_request(body, timestamp=ts, signature=sig)
    session = AsyncMock()

    result = await verify_slack_request(request, session)
    assert result == body.encode()


@pytest.mark.asyncio
async def test_invalid_signature(mock_credentials):
    ts = str(int(time.time()))
    body = "token=abc&command=%2Ftask"
    request = _make_request(body, timestamp=ts, signature="v0=badsig")
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_request(request, session)
    assert exc_info.value.status_code == 403
    assert "Invalid signature" in exc_info.value.detail


@pytest.mark.asyncio
async def test_missing_headers(mock_credentials):
    request = _make_request("body")
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_request(request, session)
    assert exc_info.value.status_code == 403
    assert "Missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_expired_timestamp(mock_credentials):
    ts = str(int(time.time()) - 600)  # 10 minutes ago
    body = "token=abc"
    sig = _make_signature("test_secret", ts, body)
    request = _make_request(body, timestamp=ts, signature=sig)
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_request(request, session)
    assert exc_info.value.status_code == 403
    assert "timestamp too old" in exc_info.value.detail


@pytest.mark.asyncio
async def test_no_credentials_configured(mock_no_credentials):
    ts = str(int(time.time()))
    request = _make_request("body", timestamp=ts, signature="v0=whatever")
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_request(request, session)
    assert exc_info.value.status_code == 503
    assert "not configured" in exc_info.value.detail
