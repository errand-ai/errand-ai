"""MAX_TURNS / REASONING_EFFORT reach the runner: profile override, else the
resolved global setting that _read_settings supplies."""

from unittest.mock import patch

import pytest

from task_manager import TaskManager

from tests.test_task_manager import _make_mock_runtime, _make_mock_task


def _settings(**overrides) -> dict:
    base = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": {"provider_id": "11111111-1111-1111-1111-111111111111", "model": "m"},
        "system_prompt": "",
        # What _read_settings resolves on an empty database.
        "max_turns": 200,
        "reasoning_effort": "medium",
    }
    base.update(overrides)
    return base


async def _runner_env(settings: dict) -> dict:
    mock_runtime = _make_mock_runtime()
    tm = TaskManager()
    tm._runtime = mock_runtime
    provider = {"base_url": "http://llm/v1", "api_key": "k", "source": "database"}
    with patch("task_manager.get_valkey", return_value=None), \
            patch("task_manager._resolve_provider_sync", return_value=provider), \
            patch.dict("os.environ", {}, clear=True):
        await tm._process_task(_make_mock_task(), settings)
    return mock_runtime.async_prepare.call_args.kwargs["env"]


@pytest.mark.parametrize(
    "overrides, max_turns, effort",
    [
        ({}, "200", "medium"),
        ({"max_turns": 75, "reasoning_effort": "low"}, "75", "low"),
        ({"_profile_max_turns": "10", "_profile_reasoning_effort": "high", "max_turns": 75}, "10", "high"),
    ],
    ids=["defaults", "global-setting", "profile-override"],
)
async def test_agent_defaults_forwarded(overrides, max_turns, effort):
    env = await _runner_env(_settings(**overrides))
    assert env["MAX_TURNS"] == max_turns
    assert env["REASONING_EFFORT"] == effort
