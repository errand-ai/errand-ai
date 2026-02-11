"""Unit tests for task runner main.py — input validation, MCP config parsing, output formatting."""

import json
import os
import sys
import tempfile
from unittest.mock import patch

import pytest

# Add task-runner to path so we can import main
sys.path.insert(0, os.path.dirname(__file__))

from main import read_env_vars, read_file, parse_mcp_config, TaskRunnerOutput, OVERARCHING_PROMPT


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


# --- Markdown fence stripping (main.py strips fences before parsing) ---


def test_strip_markdown_fences_from_json():
    """TaskRunnerOutput parses correctly after stripping ```json fences."""
    fenced = '```json\n{"status": "completed", "result": "Done", "questions": []}\n```'
    stripped = fenced.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
    parsed = TaskRunnerOutput.model_validate_json(stripped)
    assert parsed.status == "completed"
    assert parsed.result == "Done"


def test_strip_plain_markdown_fences():
    """Strips ``` fences without language tag."""
    fenced = '```\n{"status": "needs_input", "result": "Need info", "questions": ["What?"]}\n```'
    stripped = fenced.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
    parsed = TaskRunnerOutput.model_validate_json(stripped)
    assert parsed.status == "needs_input"
    assert parsed.questions == ["What?"]


# --- Overarching prompt ---


def test_overarching_prompt_contains_schema():
    """Overarching prompt instructs agent to produce JSON with required fields."""
    assert "status" in OVERARCHING_PROMPT
    assert "result" in OVERARCHING_PROMPT
    assert "questions" in OVERARCHING_PROMPT
    assert "completed" in OVERARCHING_PROMPT
    assert "needs_input" in OVERARCHING_PROMPT
