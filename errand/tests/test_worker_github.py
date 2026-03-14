"""Tests for GitHub token injection in the TaskManager."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from task_manager import TaskManager
from container_runtime import RuntimeHandle


def _make_mock_task(**overrides):
    from models import Task
    task = MagicMock(spec=Task)
    task.id = overrides.get("id", "abc-123")
    task.title = overrides.get("title", "Test task")
    task.description = overrides.get("description", "Do the thing")
    task.status = overrides.get("status", "pending")
    task.position = overrides.get("position", 0)
    task.category = overrides.get("category", "immediate")
    task.execute_at = None
    task.repeat_interval = None
    task.repeat_until = None
    task.output = None
    task.runner_logs = None
    task.retry_count = 0
    task.tags = []
    task.created_at = None
    task.updated_at = None
    task.profile_id = None
    return task


def _base_settings():
    return {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
    }


def _make_async_mock_runtime():
    """Create a mock runtime with async methods."""
    mock_runtime = MagicMock()
    mock_runtime.async_prepare = AsyncMock(return_value=RuntimeHandle(runtime_data={}))

    async def async_run_gen(handle):
        return
        yield  # make it an async generator

    mock_runtime.async_run = async_run_gen
    mock_runtime.async_result = AsyncMock(
        return_value=(0, '{"status":"completed","result":"done","questions":[]}', '')
    )
    mock_runtime.async_cleanup = AsyncMock()
    return mock_runtime


async def _run_with_gh_credentials(github_credentials, settings=None):
    """Run _process_task with the given github_credentials dict."""
    task = _make_mock_task()
    if settings is None:
        settings = _base_settings()

    mock_runtime = _make_async_mock_runtime()

    tm = TaskManager()
    tm._runtime = mock_runtime

    with patch.dict("os.environ", {
        "OPENAI_BASE_URL": "http://litellm:4000",
        "OPENAI_API_KEY": "sk-test",
    }), patch("task_manager.get_valkey", return_value=None):
        await tm._process_task(task, settings, github_credentials=github_credentials)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    return env


@pytest.mark.asyncio
async def test_github_pat_token_injected():
    """PAT mode injects personal_access_token as GH_TOKEN."""
    env = await _run_with_gh_credentials({
        "auth_mode": "pat",
        "personal_access_token": "ghp_test_pat_token_123",
    })
    assert env.get("GH_TOKEN") == "ghp_test_pat_token_123"


@pytest.mark.asyncio
async def test_github_app_token_injected():
    """App mode calls mint_installation_token and injects the result as GH_TOKEN."""
    gh_creds = {
        "auth_mode": "app",
        "app_id": "12345",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        "installation_id": "67890",
    }

    with patch("platforms.github.mint_installation_token", return_value="ghs_ephemeral_abc") as mock_mint:
        env = await _run_with_gh_credentials(gh_creds)

    assert env.get("GH_TOKEN") == "ghs_ephemeral_abc"
    mock_mint.assert_called_once_with(
        app_id="12345",
        private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        installation_id="67890",
    )


@pytest.mark.asyncio
async def test_github_no_token_when_not_configured():
    """GH_TOKEN is not present when no GitHub credential exists."""
    env = await _run_with_gh_credentials(None)
    assert "GH_TOKEN" not in env


@pytest.mark.asyncio
async def test_github_no_token_when_disconnected():
    """GH_TOKEN is not present when credential exists but query returns None (disconnected)."""
    env = await _run_with_gh_credentials(None)
    assert "GH_TOKEN" not in env


@pytest.mark.asyncio
async def test_github_app_minting_failure_graceful():
    """If mint_installation_token fails, GH_TOKEN is not set and task continues."""
    gh_creds = {
        "auth_mode": "app",
        "app_id": "12345",
        "private_key": "bad-key",
        "installation_id": "67890",
    }

    with patch("platforms.github.mint_installation_token", side_effect=RuntimeError("API error")):
        env = await _run_with_gh_credentials(gh_creds)

    assert "GH_TOKEN" not in env
