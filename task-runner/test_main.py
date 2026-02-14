"""Unit tests for task runner main.py — input validation, MCP config parsing, output formatting."""

import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Add task-runner to path so we can import main
sys.path.insert(0, os.path.dirname(__file__))

# Mock the agents SDK before importing main — the SDK may not be installed locally
# or may have version conflicts. We only need the pure-Python functions from main.
_mock_agents = MagicMock()
_mock_agents.function_tool = lambda f: f  # passthrough decorator
sys.modules.setdefault("agents", _mock_agents)
sys.modules.setdefault("agents.mcp", MagicMock())
sys.modules.setdefault("openai", MagicMock())

import logging
from main import read_env_vars, read_file, parse_mcp_config, TaskRunnerOutput, OVERARCHING_PROMPT, extract_json, execute_command


# --- Environment variable validation ---


def test_read_env_vars_all_present():
    """Returns env dict when all required vars are set."""
    env = {
        "OPENAI_BASE_URL": "http://localhost:4000",
        "OPENAI_API_KEY": "sk-test",
        "OPENAI_MODEL": "gpt-4o",
        "USER_PROMPT_PATH": "/workspace/prompt.txt",
        "SYSTEM_PROMPT_PATH": "/workspace/system_prompt.txt",
        "MCP_CONFIGURATION_PATH": "/workspace/mcp.json",
    }
    with patch.dict(os.environ, env, clear=False):
        result = read_env_vars()
    assert result["OPENAI_BASE_URL"] == "http://localhost:4000"
    assert result["OPENAI_MODEL"] == "gpt-4o"


def test_read_env_vars_missing_exits():
    """Exits with code 1 when a required env var is missing."""
    env = {
        "OPENAI_BASE_URL": "http://localhost:4000",
        # Missing OPENAI_API_KEY and others
    }
    with patch.dict(os.environ, env, clear=True), pytest.raises(SystemExit) as exc_info:
        read_env_vars()
    assert exc_info.value.code == 1


# --- File reading ---


def test_read_file_success():
    """Reads file content correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello world")
        f.flush()
        result = read_file(f.name, "test file")
    assert result == "Hello world"
    os.unlink(f.name)


def test_read_file_missing_exits():
    """Exits with code 1 when file doesn't exist."""
    with pytest.raises(SystemExit) as exc_info:
        read_file("/nonexistent/path.txt", "test file")
    assert exc_info.value.code == 1


# --- MCP config parsing ---


def test_parse_mcp_config_valid():
    """Parses valid MCP config JSON."""
    raw = json.dumps({
        "mcpServers": {
            "test": {"url": "http://localhost:4000/mcp", "headers": {"key": "value"}},
        }
    })
    config = parse_mcp_config(raw)
    assert "mcpServers" in config
    assert config["mcpServers"]["test"]["url"] == "http://localhost:4000/mcp"


def test_parse_mcp_config_empty_string():
    """Returns empty dict for empty string."""
    assert parse_mcp_config("") == {}
    assert parse_mcp_config("   ") == {}


def test_parse_mcp_config_invalid_json():
    """Returns empty dict for invalid JSON."""
    assert parse_mcp_config("not json") == {}


def test_parse_mcp_config_non_dict():
    """Returns empty dict when JSON is not an object."""
    assert parse_mcp_config("[1,2,3]") == {}


# --- Structured output model ---


def test_task_runner_output_completed():
    """Valid completed output."""
    output = TaskRunnerOutput(status="completed", result="Done", questions=[])
    data = json.loads(output.model_dump_json())
    assert data["status"] == "completed"
    assert data["result"] == "Done"
    assert data["questions"] == []


def test_task_runner_output_needs_input():
    """Valid needs_input output."""
    output = TaskRunnerOutput(status="needs_input", result="Need info", questions=["What scope?"])
    data = json.loads(output.model_dump_json())
    assert data["status"] == "needs_input"
    assert data["questions"] == ["What scope?"]


def test_task_runner_output_default_questions():
    """Questions defaults to empty list."""
    output = TaskRunnerOutput(status="completed", result="Done")
    assert output.questions == []


# --- extract_json ---


def test_extract_json_bare_json():
    """Extracts valid JSON when output is bare JSON."""
    raw = '{"status": "completed", "result": "Done", "questions": []}'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "completed"
    assert parsed.result == "Done"


def test_extract_json_code_fence_at_start():
    """Extracts JSON from code fence at start of output."""
    raw = '```json\n{"status": "completed", "result": "Done", "questions": []}\n```'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "completed"


def test_extract_json_plain_fence_at_start():
    """Extracts JSON from plain ``` fence without language tag."""
    raw = '```\n{"status": "needs_input", "result": "Need info", "questions": ["What?"]}\n```'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "needs_input"
    assert parsed.questions == ["What?"]


def test_extract_json_preamble_before_code_fence():
    """Extracts JSON when LLM produces preamble text before code fence."""
    raw = 'Based on my analysis of all 53 applications, here is the health status report:\n\n```json\n{"status": "completed", "result": "All healthy", "questions": []}\n```'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "completed"
    assert parsed.result == "All healthy"


def test_extract_json_preamble_before_bare_json():
    """Extracts JSON when LLM produces preamble text before bare JSON object."""
    raw = 'Here is the result:\n{"status": "completed", "result": "done", "questions": []}'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "completed"
    assert parsed.result == "done"


def test_extract_json_unparseable_output():
    """Returns None when output contains no valid TaskRunnerOutput JSON."""
    raw = "This is just plain text with no JSON at all."
    result = extract_json(raw)
    assert result is None


def test_extract_json_invalid_json_in_fence():
    """Returns None when code fence contains invalid JSON."""
    raw = '```json\nnot valid json\n```'
    result = extract_json(raw)
    assert result is None


def test_extract_json_preamble_and_postamble():
    """Extracts JSON when there is text both before and after the code fence."""
    raw = 'Here is my report:\n\n```json\n{"status": "completed", "result": "Report", "questions": []}\n```\n\nLet me know if you need more details.'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.result == "Report"


# --- Overarching prompt ---


def test_overarching_prompt_contains_schema():
    """Overarching prompt instructs agent to produce JSON with required fields."""
    assert "status" in OVERARCHING_PROMPT
    assert "result" in OVERARCHING_PROMPT
    assert "questions" in OVERARCHING_PROMPT
    assert "completed" in OVERARCHING_PROMPT
    assert "needs_input" in OVERARCHING_PROMPT


# --- Log level configuration ---


def test_log_level_defaults_to_info():
    """Without LOG_LEVEL env var, logging defaults to INFO."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LOG_LEVEL", None)
        level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    assert level == logging.INFO


def test_log_level_debug_from_env():
    """LOG_LEVEL=DEBUG sets debug logging."""
    with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
        level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    assert level == logging.DEBUG


def test_log_level_invalid_falls_back_to_info():
    """Invalid LOG_LEVEL falls back to INFO."""
    with patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}):
        level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    assert level == logging.INFO


# --- execute_command tool ---


def test_execute_command_success(tmp_path):
    """Runs a simple command and returns stdout."""
    result = execute_command("echo hello", working_directory=str(tmp_path))
    assert "hello" in result


def test_execute_command_nonzero_exit(tmp_path):
    """Reports non-zero exit code."""
    result = execute_command("exit 42", working_directory=str(tmp_path))
    assert "exited with code 42" in result


def test_execute_command_stderr(tmp_path):
    """Captures stderr output."""
    result = execute_command("echo err >&2", working_directory=str(tmp_path))
    assert "err" in result


def test_execute_command_timeout(tmp_path):
    """Returns timeout message for long-running commands."""
    import main
    original = main.COMMAND_TIMEOUT
    main.COMMAND_TIMEOUT = 1
    try:
        result = execute_command("sleep 10", working_directory=str(tmp_path))
        assert "timed out" in result
    finally:
        main.COMMAND_TIMEOUT = original


def test_execute_command_working_directory():
    """Runs command in specified working directory."""
    result = execute_command("pwd", working_directory="/tmp")
    # macOS /tmp is a symlink to /private/tmp
    assert "tmp" in result


def test_execute_command_invalid_directory():
    """Returns error for non-existent working directory."""
    result = execute_command("echo hello", working_directory="/nonexistent")
    assert "Error executing command" in result
