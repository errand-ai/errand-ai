"""Tests for execute_command's Google-token 401 detection and refresh path.

Covers `_is_google_token_expired` (legacy UNAUTHENTICATED + Google raw 401
conjunction) and the one-retry cap inside `_execute_command_impl`.
"""

from unittest.mock import AsyncMock, patch

import pytest

from main import (
    _execute_command_impl,
    _is_google_token_expired,
)


# ---------------------------------------------------------------------------
# 4.6 — _is_google_token_expired
# ---------------------------------------------------------------------------


def test_detects_legacy_unauthenticated_substring():
    body = '{"error": {"status": "UNAUTHENTICATED", "message": "token expired"}}'
    assert _is_google_token_expired(body) is True


def test_detects_raw_401_conjunction():
    body = (
        'HTTP/1.1 401 Unauthorized\n'
        '{"error": {"code": 401, "message": "Request had invalid '
        'authentication credentials. Expected OAuth 2 access token..."}}'
    )
    assert _is_google_token_expired(body) is True


def test_partial_match_code_only_returns_false():
    body = '{"error": {"code": 401, "message": "Some other error"}}'
    assert _is_google_token_expired(body) is False


def test_partial_match_message_only_returns_false():
    body = 'Request had invalid authentication credentials, but no code'
    assert _is_google_token_expired(body) is False


def test_unrelated_output_returns_false():
    body = "ls: cannot access '/foo': No such file or directory"
    assert _is_google_token_expired(body) is False


# ---------------------------------------------------------------------------
# 4.6 — one-retry cap inside _execute_command_impl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_retry_cap_on_repeated_raw_401(monkeypatch):
    """If the rerun also produces a raw 401, no second refresh fires."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "old-token")

    raw_401_output = (
        '{"error": {"code": 401, "message": "Request had invalid '
        'authentication credentials"}}'
    )

    # Each subprocess call returns the same raw 401 body.
    call_log: list[str] = []

    def _fake_run_subprocess(command, cwd):
        call_log.append(command)
        return 1, raw_401_output

    refresh_mock = AsyncMock(return_value="new-token")

    with patch("main._run_subprocess", side_effect=_fake_run_subprocess), \
         patch("main._refresh_google_workspace_token", refresh_mock):
        await _execute_command_impl("gws drive files list")

    # Subprocess invoked exactly twice: original + one retry post-refresh.
    assert len(call_log) == 2
    # Refresh helper invoked exactly once — the second 401 must NOT trigger
    # another refresh inside the same execute_command invocation.
    refresh_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_unauthenticated_path_unchanged(monkeypatch):
    """Existing UNAUTHENTICATED substring still triggers refresh exactly once."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "old-token")

    auth_failed_output = (
        '{"error": {"status": "UNAUTHENTICATED", "message": "Token expired"}}'
    )
    success_output = '{"files": []}'

    counter = {"n": 0}

    def _fake_run_subprocess(command, cwd):
        counter["n"] += 1
        if counter["n"] == 1:
            return 1, auth_failed_output
        return 0, success_output

    refresh_mock = AsyncMock(return_value="new-token")

    with patch("main._run_subprocess", side_effect=_fake_run_subprocess), \
         patch("main._refresh_google_workspace_token", refresh_mock):
        result = await _execute_command_impl("gws drive files list")

    refresh_mock.assert_awaited_once()
    assert "files" in result
