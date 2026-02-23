"""Tests for GitHubPlatform and mint_installation_token."""
from unittest.mock import MagicMock, patch

import pytest

from platforms.github import GitHubPlatform, mint_installation_token


# --- GitHubPlatform.info() ---


def test_github_info():
    github = GitHubPlatform()
    info = github.info()
    assert info.id == "github"
    assert info.label == "GitHub"
    assert info.capabilities == set()
    schema_keys = [f["key"] for f in info.credential_schema]
    assert "auth_mode" in schema_keys
    assert "personal_access_token" in schema_keys
    assert "app_id" in schema_keys
    assert "private_key" in schema_keys
    assert "installation_id" in schema_keys


def test_github_info_auth_mode_field():
    github = GitHubPlatform()
    info = github.info()
    auth_mode_field = next(f for f in info.credential_schema if f["key"] == "auth_mode")
    assert auth_mode_field["type"] == "select"
    option_values = [o["value"] for o in auth_mode_field["options"]]
    assert "pat" in option_values
    assert "app" in option_values


# --- PAT verification ---


@pytest.mark.asyncio
async def test_verify_pat_success():
    github = GitHubPlatform()
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("platforms.github.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = lambda self: _async_return(self)
        MockClient.return_value.__aexit__ = lambda *args: _async_return(None)
        MockClient.return_value.get = _async_return_fn(mock_response)

        result = await github.verify_credentials({
            "auth_mode": "pat",
            "personal_access_token": "ghp_valid_token",
        })

    assert result is True


@pytest.mark.asyncio
async def test_verify_pat_unauthorized():
    github = GitHubPlatform()
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("platforms.github.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = lambda self: _async_return(self)
        MockClient.return_value.__aexit__ = lambda *args: _async_return(None)
        MockClient.return_value.get = _async_return_fn(mock_response)

        result = await github.verify_credentials({
            "auth_mode": "pat",
            "personal_access_token": "ghp_expired",
        })

    assert result is False


@pytest.mark.asyncio
async def test_verify_pat_network_error():
    github = GitHubPlatform()

    with patch("platforms.github.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = lambda self: _async_return(self)
        MockClient.return_value.__aexit__ = lambda *args: _async_return(None)
        MockClient.return_value.get = _async_raise_fn(Exception("connection refused"))

        result = await github.verify_credentials({
            "auth_mode": "pat",
            "personal_access_token": "ghp_valid",
        })

    assert result is False


# --- App verification ---


@pytest.mark.asyncio
async def test_verify_app_success():
    github = GitHubPlatform()

    with patch("platforms.github.mint_installation_token") as mock_mint:
        mock_mint.return_value = "ghs_ephemeral_token"
        result = await github.verify_credentials({
            "auth_mode": "app",
            "app_id": "123",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            "installation_id": "456",
        })

    assert result is True
    mock_mint.assert_called_once_with(
        app_id="123",
        private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        installation_id="456",
    )


@pytest.mark.asyncio
async def test_verify_app_failure():
    github = GitHubPlatform()

    with patch("platforms.github.mint_installation_token") as mock_mint:
        mock_mint.side_effect = RuntimeError("HTTP 401 - Bad credentials")
        result = await github.verify_credentials({
            "auth_mode": "app",
            "app_id": "123",
            "private_key": "bad-key",
            "installation_id": "456",
        })

    assert result is False


@pytest.mark.asyncio
async def test_verify_unknown_auth_mode():
    github = GitHubPlatform()
    result = await github.verify_credentials({"auth_mode": "unknown"})
    assert result is False


# --- mint_installation_token ---


def test_mint_installation_token_success():
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"token": "ghs_fresh_token", "expires_at": "2026-02-23T16:00:00Z"}

    with patch("platforms.github.jwt.encode", return_value="fake.jwt.token"), \
         patch("platforms.github.httpx.post", return_value=mock_response):
        token = mint_installation_token("123", "fake-private-key", "456")

    assert token == "ghs_fresh_token"


def test_mint_installation_token_api_error():
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch("platforms.github.jwt.encode", return_value="fake.jwt.token"), \
         patch("platforms.github.httpx.post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="HTTP 404"):
            mint_installation_token("123", "fake-private-key", "999")


def test_mint_installation_token_jwt_error():
    with patch("platforms.github.jwt.encode", side_effect=ValueError("Invalid key")):
        with pytest.raises(ValueError, match="Invalid key"):
            mint_installation_token("123", "bad-key", "456")


# --- helpers ---


async def _async_return(value):
    return value


def _async_return_fn(value):
    async def fn(*args, **kwargs):
        return value
    return fn


def _async_raise_fn(exc):
    async def fn(*args, **kwargs):
        raise exc
    return fn
