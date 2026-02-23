"""Tests for GitHub token injection in the worker."""
from unittest.mock import MagicMock, patch

from worker import process_task_in_container


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
    return task


def _base_settings():
    return {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
    }


def _run_with_gh_credentials(github_credentials, settings=None):
    """Run process_task_in_container with the given github_credentials dict."""
    task = _make_mock_task()
    if settings is None:
        settings = _base_settings()

    mock_runtime = MagicMock()
    mock_runtime.run.return_value = iter([])
    mock_runtime.result.return_value = (0, '{"status":"completed","result":"done","questions":[]}', '')

    import worker
    original_runtime = worker.container_runtime
    worker.container_runtime = mock_runtime

    try:
        with patch.dict("os.environ", {"OPENAI_BASE_URL": "http://litellm:4000", "OPENAI_API_KEY": "sk-test"}):
            process_task_in_container(task, settings, github_credentials=github_credentials)
    finally:
        worker.container_runtime = original_runtime

    env = mock_runtime.prepare.call_args.kwargs["env"]
    return env


def test_github_pat_token_injected():
    """PAT mode injects personal_access_token as GH_TOKEN."""
    env = _run_with_gh_credentials({
        "auth_mode": "pat",
        "personal_access_token": "ghp_test_pat_token_123",
    })
    assert env.get("GH_TOKEN") == "ghp_test_pat_token_123"


def test_github_app_token_injected():
    """App mode calls mint_installation_token and injects the result as GH_TOKEN."""
    gh_creds = {
        "auth_mode": "app",
        "app_id": "12345",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        "installation_id": "67890",
    }

    with patch("platforms.github.mint_installation_token", return_value="ghs_ephemeral_abc") as mock_mint:
        env = _run_with_gh_credentials(gh_creds)

    assert env.get("GH_TOKEN") == "ghs_ephemeral_abc"
    mock_mint.assert_called_once_with(
        app_id="12345",
        private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        installation_id="67890",
    )


def test_github_no_token_when_not_configured():
    """GH_TOKEN is not present when no GitHub credential exists."""
    env = _run_with_gh_credentials(None)
    assert "GH_TOKEN" not in env


def test_github_no_token_when_disconnected():
    """GH_TOKEN is not present when credential exists but query returns None (disconnected)."""
    # The async caller passes None when no connected credential is found
    env = _run_with_gh_credentials(None)
    assert "GH_TOKEN" not in env


def test_github_app_minting_failure_graceful():
    """If mint_installation_token fails, GH_TOKEN is not set and task continues."""
    gh_creds = {
        "auth_mode": "app",
        "app_id": "12345",
        "private_key": "bad-key",
        "installation_id": "67890",
    }

    with patch("platforms.github.mint_installation_token", side_effect=RuntimeError("API error")):
        env = _run_with_gh_credentials(gh_creds)

    assert "GH_TOKEN" not in env
