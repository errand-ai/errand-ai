"""Detected providers: the host-networking guard, and their longer default timeout.

A provider found by local detection is stored with the URL that answered the
probe — `http://host.docker.internal:11434/v1`. Task containers on a named
network get a host entry that makes that name resolve; task containers on host
networking do not, because they share the host's namespace and the correct
answer there is `localhost`. Rather than carry two URL forms, a detected
provider is refused under host networking with an error that names the fix.

Separately, a local runtime's first request can spend a long time loading model
weights, so a detected provider raises the *default* request timeout — without
ever overriding a timeout the operator configured.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from container_runtime import RuntimeHandle
from task_manager import DETECTED_PROVIDER_LLM_TIMEOUT, TaskManager

from tests.test_task_manager import _make_mock_runtime, _make_mock_task


def _settings(**overrides) -> dict:
    base = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": {"provider_id": "11111111-1111-1111-1111-111111111111", "model": "qwen3"},
        "system_prompt": "",
    }
    base.update(overrides)
    return base


def _provider(source: str) -> dict:
    return {
        "base_url": "http://host.docker.internal:11434/v1",
        "api_key": "sk-no-key-required",
        "source": source,
    }


async def _run(settings: dict, source: str, env: dict):
    """Run _process_task with a provider of the given source under the given env."""
    task = _make_mock_task()
    mock_runtime = _make_mock_runtime()
    tm = TaskManager()
    tm._runtime = mock_runtime

    with patch("task_manager.get_valkey", return_value=None), \
            patch("task_manager._resolve_provider_sync", return_value=_provider(source)), \
            patch.dict("os.environ", env, clear=True):
        result = await tm._process_task(task, settings)

    return result, mock_runtime


class TestHostNetworkingGuard:
    async def test_detected_provider_refused_under_host_networking(self):
        """No named network → the task fails before starting, naming the fix."""
        result, mock_runtime = await _run(_settings(), "detected", {})

        exit_code, output, error = result
        assert exit_code == -1
        assert "TASK_RUNNER_NETWORK" in error
        assert json.loads(output)["error"] == error
        mock_runtime.async_prepare.assert_not_called()

    async def test_error_explains_why(self):
        """The message has to be actionable: it names the provider source and the setting."""
        (_, _, error), _ = await _run(_settings(), "detected", {})

        assert "detect" in error.lower()
        assert "named" in error.lower() or "network" in error.lower()

    async def test_detected_provider_accepted_on_named_network(self):
        result, mock_runtime = await _run(
            _settings(), "detected", {"TASK_RUNNER_NETWORK": "errand-net"}
        )

        assert result[0] == 0
        mock_runtime.async_prepare.assert_called_once()
        env = mock_runtime.async_prepare.call_args.kwargs["env"]
        assert env["OPENAI_BASE_URL"] == "http://host.docker.internal:11434/v1"

    async def test_manually_configured_provider_unaffected(self):
        """Host networking is fine for a provider whose URL was not probed through the gateway."""
        result, mock_runtime = await _run(_settings(), "database", {})

        assert result[0] == 0
        mock_runtime.async_prepare.assert_called_once()

    async def test_env_sourced_provider_unaffected(self):
        result, mock_runtime = await _run(_settings(), "env", {})

        assert result[0] == 0
        mock_runtime.async_prepare.assert_called_once()

    async def test_kubernetes_does_not_trip_the_guard(self):
        """A pod never uses Docker host networking, so the guard must not fire there."""
        result, mock_runtime = await _run(
            _settings(), "detected", {"CONTAINER_RUNTIME": "kubernetes"}
        )

        assert result[0] == 0
        mock_runtime.async_prepare.assert_called_once()


class TestDetectedProviderTimeout:
    """D9 — a detected provider raises the default, never overrides configuration."""

    NAMED_NET = {"TASK_RUNNER_NETWORK": "errand-net"}

    async def test_detected_provider_gets_longer_default(self):
        _, mock_runtime = await _run(_settings(), "detected", self.NAMED_NET)

        env = mock_runtime.async_prepare.call_args.kwargs["env"]
        assert env["LLM_REQUEST_TIMEOUT"] == str(DETECTED_PROVIDER_LLM_TIMEOUT)
        assert DETECTED_PROVIDER_LLM_TIMEOUT > 30

    async def test_profile_timeout_wins(self):
        _, mock_runtime = await _run(
            _settings(_profile_llm_timeout=45), "detected", self.NAMED_NET
        )

        env = mock_runtime.async_prepare.call_args.kwargs["env"]
        assert env["LLM_REQUEST_TIMEOUT"] == "45"

    async def test_global_setting_wins(self):
        _, mock_runtime = await _run(
            _settings(task_processing_timeout=60), "detected", self.NAMED_NET
        )

        env = mock_runtime.async_prepare.call_args.kwargs["env"]
        assert env["LLM_REQUEST_TIMEOUT"] == "60"

    async def test_non_detected_provider_keeps_standard_default(self):
        _, mock_runtime = await _run(_settings(), "database", self.NAMED_NET)

        env = mock_runtime.async_prepare.call_args.kwargs["env"]
        assert env["LLM_REQUEST_TIMEOUT"] == "30"
