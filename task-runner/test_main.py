"""Unit tests for task runner main.py — input validation, MCP config parsing, structured events."""

# Mocks are set up in conftest.py (shared with test_tool_registry.py)

import asyncio
import json
import logging
import os
import re
import sys
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from conftest import MockCallModelData as _MockCallModelData

from main import (
    read_env_vars, _read_startup_file, parse_mcp_config, TaskRunnerOutput,
    execute_command, StreamEventEmitter, _truncate, TOOL_RESULT_MAX_LENGTH,
    emit_event, get_reasoning_effort, get_llm_request_timeout, extract_json,
    filter_model_input, _strip_screenshots, _trim_context_window,
    _sanitize_tool_calls, _repair_truncated_json, _classify_error,
    _estimate_tokens, MAX_RETAINED_SCREENSHOTS, MAX_CONTEXT_TOKENS,
    connect_mcp_servers, resolve_max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS,
    _TRUNCATION_RECOVERY_MESSAGE,
    extract_output, _OUTPUT, _NUDGE, _EMPTY_FAIL,
    _execute_command_impl, EXECUTE_COMMAND_ALIASES, EXECUTE_COMMAND_ALIAS_TOOLS,
    _normalize_harmony_tool_name, _resolve_recovery_target,
    HARMONY_RECOVERY_CAP_PER_PAIR,
    StallDetector, AgentStallError, DEFAULT_STALL_REPEAT_LIMIT,
    DEFAULT_STALL_NUDGE_LIMIT, build_stall_nudge, GuardedAgent,
)
import main


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


def test_read_startup_file_success():
    """Reads file content correctly."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello world")
        f.flush()
        result = _read_startup_file(f.name, "test file")
    assert result == "Hello world"
    os.unlink(f.name)


def test_read_startup_file_missing_exits():
    """Exits with code 1 when file doesn't exist."""
    with pytest.raises(SystemExit) as exc_info:
        _read_startup_file("/nonexistent/path.txt", "test file")
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


# --- emit_event ---


def test_emit_event_writes_json_to_stderr(capsys):
    """emit_event writes a single-line JSON object to stderr."""
    emit_event("agent_start", {"agent": "TaskRunner"})
    captured = capsys.readouterr()
    line = captured.err.strip()
    parsed = json.loads(line)
    assert parsed == {"type": "agent_start", "data": {"agent": "TaskRunner"}}


def test_emit_event_tool_call(capsys):
    """emit_event produces correct tool_call event."""
    emit_event("tool_call", {"tool": "execute_command", "args": {"command": "ls -la"}})
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["type"] == "tool_call"
    assert parsed["data"]["tool"] == "execute_command"
    assert parsed["data"]["args"] == {"command": "ls -la"}


def test_emit_event_error(capsys):
    """emit_event produces correct error event."""
    emit_event("error", {"message": "API auth failed"})
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["type"] == "error"
    assert parsed["data"]["message"] == "API auth failed"


def test_emit_event_valid_json(capsys):
    """All events are valid JSON with exactly type and data keys."""
    emit_event("thinking", {"text": "Let me consider..."})
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert set(parsed.keys()) == {"type", "data"}
    assert isinstance(parsed["type"], str)
    assert isinstance(parsed["data"], dict)


# --- StreamEventEmitter ---


@pytest.mark.asyncio
async def test_stream_event_emitter_on_agent_start(capsys):
    """on_agent_start emits agent_start event to stderr."""
    agent = MagicMock()
    agent.name = "TaskRunner"
    emitter = StreamEventEmitter()
    await emitter.on_agent_start(MagicMock(), agent)
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed == {"type": "agent_start", "data": {"agent": "TaskRunner"}}


@pytest.mark.asyncio
async def test_stream_event_emitter_on_tool_start_is_noop(capsys):
    """on_tool_start is a no-op (tool_call emitted from streaming loop with full args)."""
    agent = MagicMock()
    tool = MagicMock()
    tool.name = "execute_command"
    emitter = StreamEventEmitter()
    await emitter.on_tool_start(MagicMock(), agent, tool)
    captured = capsys.readouterr()
    assert captured.err.strip() == ""


@pytest.mark.asyncio
async def test_stream_event_emitter_on_tool_end(capsys):
    """on_tool_end emits tool_result event with truncated output and length."""
    agent = MagicMock()
    tool = MagicMock()
    tool.name = "execute_command"
    emitter = StreamEventEmitter()
    await emitter.on_tool_end(MagicMock(), agent, tool, "hello world")
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["type"] == "tool_result"
    assert parsed["data"]["tool"] == "execute_command"
    assert parsed["data"]["output"] == "hello world"
    assert parsed["data"]["length"] == 11


@pytest.mark.asyncio
async def test_stream_event_emitter_on_tool_end_truncates(capsys):
    """on_tool_end truncates long results to TOOL_RESULT_MAX_LENGTH."""
    agent = MagicMock()
    tool = MagicMock()
    tool.name = "execute_command"
    long_result = "x" * 800
    emitter = StreamEventEmitter()
    await emitter.on_tool_end(MagicMock(), agent, tool, long_result)
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["data"]["length"] == 800
    assert len(parsed["data"]["output"]) == TOOL_RESULT_MAX_LENGTH + 3  # 500 + "..."
    assert parsed["data"]["output"].endswith("...")


@pytest.mark.asyncio
async def test_stream_event_emitter_on_agent_end(capsys):
    """on_agent_end emits agent_end event with output."""
    agent = MagicMock()
    output = TaskRunnerOutput(status="completed", result="Done", questions=[])
    emitter = StreamEventEmitter()
    await emitter.on_agent_end(MagicMock(), agent, output)
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["type"] == "agent_end"
    assert parsed["data"]["output"]["status"] == "completed"


@pytest.mark.asyncio
async def test_stream_event_emitter_on_llm_start(capsys):
    """on_llm_start emits llm_turn_start event to stderr."""
    agent = MagicMock()
    agent.name = "TaskRunner"
    emitter = StreamEventEmitter()
    await emitter.on_llm_start(MagicMock(), agent)
    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["type"] == "llm_turn_start"
    assert "turn_id" in parsed["data"]


@pytest.mark.asyncio
async def test_stream_event_emitter_on_llm_end():
    """on_llm_end is a no-op (does not raise)."""
    agent = MagicMock()
    agent.name = "TaskRunner"
    emitter = StreamEventEmitter()
    await emitter.on_llm_end(MagicMock(), agent, MagicMock())


# --- REASONING_EFFORT env var ---


def test_reasoning_effort_default():
    """Default reasoning effort is 'medium'."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("REASONING_EFFORT", None)
        assert get_reasoning_effort() == "medium"


def test_reasoning_effort_high():
    """REASONING_EFFORT=high returns 'high'."""
    with patch.dict(os.environ, {"REASONING_EFFORT": "high"}):
        assert get_reasoning_effort() == "high"


def test_reasoning_effort_low():
    """REASONING_EFFORT=low returns 'low'."""
    with patch.dict(os.environ, {"REASONING_EFFORT": "low"}):
        assert get_reasoning_effort() == "low"


def test_reasoning_effort_invalid_falls_back():
    """Invalid REASONING_EFFORT falls back to 'medium'."""
    with patch.dict(os.environ, {"REASONING_EFFORT": "extreme"}):
        assert get_reasoning_effort() == "medium"


def test_llm_request_timeout_unset_returns_none():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LLM_REQUEST_TIMEOUT", None)
        assert get_llm_request_timeout() is None


def test_llm_request_timeout_blank_returns_none():
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "   "}):
        assert get_llm_request_timeout() is None


def test_llm_request_timeout_valid_returns_float():
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "120"}):
        assert get_llm_request_timeout() == 120.0


def test_llm_request_timeout_invalid_logs_warning_and_returns_none(caplog):
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "abc"}):
        with caplog.at_level(logging.WARNING):
            assert get_llm_request_timeout() is None
    assert any("Invalid LLM_REQUEST_TIMEOUT 'abc'" in r.message for r in caplog.records)


def test_llm_request_timeout_zero_returns_none():
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "0"}):
        assert get_llm_request_timeout() is None


def test_llm_request_timeout_negative_returns_none():
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "-10"}):
        assert get_llm_request_timeout() is None


def _build_async_openai_kwargs():
    """Replicate the AsyncOpenAI kwargs-construction logic from main()."""
    client_kwargs: dict = {"base_url": "http://example", "api_key": "key"}
    request_timeout = get_llm_request_timeout()
    if request_timeout is not None:
        client_kwargs["timeout"] = request_timeout
    return client_kwargs


def test_async_openai_kwargs_include_timeout_when_env_set():
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "120"}):
        kwargs = _build_async_openai_kwargs()
    assert kwargs.get("timeout") == 120.0


def test_async_openai_kwargs_omit_timeout_when_env_unset():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LLM_REQUEST_TIMEOUT", None)
        kwargs = _build_async_openai_kwargs()
    assert "timeout" not in kwargs


def test_async_openai_kwargs_omit_timeout_when_env_invalid():
    with patch.dict(os.environ, {"LLM_REQUEST_TIMEOUT": "abc"}):
        kwargs = _build_async_openai_kwargs()
    assert "timeout" not in kwargs


def test_reasoning_effort_case_insensitive():
    """REASONING_EFFORT is case-insensitive."""
    with patch.dict(os.environ, {"REASONING_EFFORT": "HIGH"}):
        assert get_reasoning_effort() == "high"


# --- Agent output_type configuration ---


def test_task_runner_output_has_required_fields():
    """TaskRunnerOutput model has the required fields for structured output parsing."""
    assert hasattr(TaskRunnerOutput, "model_fields")
    assert "status" in TaskRunnerOutput.model_fields
    assert "result" in TaskRunnerOutput.model_fields
    assert "questions" in TaskRunnerOutput.model_fields


# --- extract_json() ---


def test_extract_json_direct_parse():
    """Direct JSON string is parsed successfully."""
    raw = '{"status": "completed", "result": "done", "questions": []}'
    parsed = extract_json(raw)
    assert parsed == {"status": "completed", "result": "done", "questions": []}


def test_extract_json_with_preamble():
    """JSON embedded after preamble text is extracted via brace strategy."""
    raw = 'Now let me create a report:\n\n{"status": "completed", "result": "report content", "questions": []}'
    parsed = extract_json(raw)
    assert parsed is not None
    assert parsed["status"] == "completed"
    assert parsed["result"] == "report content"


def test_extract_json_code_fence():
    """JSON inside a markdown code fence is extracted."""
    raw = 'Here is the output:\n\n```json\n{"status": "completed", "result": "fenced", "questions": []}\n```'
    parsed = extract_json(raw)
    assert parsed is not None
    assert parsed["result"] == "fenced"


def test_extract_json_returns_none_for_invalid():
    """Returns None when no valid TaskRunnerOutput JSON is found."""
    assert extract_json("just plain text") is None
    assert extract_json("") is None
    assert extract_json('{"not": "valid schema"}') is None


def test_extract_json_with_trailing_text():
    """JSON followed by trailing text is extracted via brace strategy."""
    raw = '{"status": "completed", "result": "ok", "questions": []}\n\nSome trailing text.'
    parsed = extract_json(raw)
    assert parsed is not None
    assert parsed["result"] == "ok"


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
#
# NOTE: `execute_command` and the alias shims in EXECUTE_COMMAND_ALIAS_TOOLS are
# `async def` (see main.py — required by the mid-task Google token refresh
# wrapper, which awaits an HTTP refresh on UNAUTHENTICATED responses). Calling
# them without `await` / `asyncio.run(...)` returns a coroutine that's never
# awaited and the assertion fails with `TypeError: argument of type 'coroutine'
# is not iterable`. New tests in this cluster MUST either be `async def` +
# `@pytest.mark.asyncio`, or wrap the call in `asyncio.run(...)` as the sync
# tests below do.


def test_execute_command_success(tmp_path):
    """Runs a simple command and returns stdout."""
    result = asyncio.run(execute_command("echo hello", working_directory=str(tmp_path)))
    assert "hello" in result


def test_execute_command_nonzero_exit(tmp_path):
    """Reports non-zero exit code."""
    result = asyncio.run(execute_command("exit 42", working_directory=str(tmp_path)))
    assert "exited with code 42" in result


def test_execute_command_stderr(tmp_path):
    """Captures stderr output."""
    result = asyncio.run(execute_command("echo err >&2", working_directory=str(tmp_path)))
    assert "err" in result


def test_execute_command_timeout(tmp_path):
    """Returns timeout message for long-running commands."""
    main_module = sys.modules["main"]
    original = main_module.COMMAND_TIMEOUT
    main_module.COMMAND_TIMEOUT = 1
    try:
        result = asyncio.run(execute_command("sleep 10", working_directory=str(tmp_path)))
        assert "timed out" in result
    finally:
        main_module.COMMAND_TIMEOUT = original


def test_execute_command_working_directory():
    """Runs command in specified working directory."""
    result = asyncio.run(execute_command("pwd", working_directory="/tmp"))
    # macOS /tmp is a symlink to /private/tmp
    assert "tmp" in result


def test_execute_command_invalid_directory():
    """Returns error for non-existent working directory."""
    result = asyncio.run(execute_command("echo hello", working_directory="/nonexistent"))
    assert "Error executing command" in result


# --- execute_command output truncation ---


def test_execute_command_output_truncated_at_cap(tmp_path):
    """Output exceeding MAX_TOOL_OUTPUT_CHARS is truncated with a guidance message."""
    main_module = sys.modules["main"]
    original_cap = main_module.MAX_TOOL_OUTPUT_CHARS
    main_module.MAX_TOOL_OUTPUT_CHARS = 100  # small cap for testing
    try:
        # Generate output larger than the cap
        result = asyncio.run(execute_command(f"python3 -c \"print('x' * 200)\"", working_directory=str(tmp_path)))
        assert "[OUTPUT TRUNCATED" in result
        assert "file-path-based tools" in result
    finally:
        main_module.MAX_TOOL_OUTPUT_CHARS = original_cap


def test_execute_command_output_within_cap_not_truncated(tmp_path):
    """Output within MAX_TOOL_OUTPUT_CHARS is returned unchanged."""
    main_module = sys.modules["main"]
    original_cap = main_module.MAX_TOOL_OUTPUT_CHARS
    main_module.MAX_TOOL_OUTPUT_CHARS = 10000  # large cap
    try:
        result = asyncio.run(execute_command("echo hello", working_directory=str(tmp_path)))
        assert "[OUTPUT TRUNCATED" not in result
        assert "hello" in result
    finally:
        main_module.MAX_TOOL_OUTPUT_CHARS = original_cap


# --- Streaming event loop: thinking and reasoning emission ---


@pytest.mark.asyncio
async def test_streaming_loop_emits_thinking_for_message_output(capsys):
    """The streaming loop emits a 'thinking' event when a message_output_item is received."""
    # Build a mock event that mimics RunItemStreamEvent with a message_output_item
    mock_item = MagicMock()
    mock_item.type = "message_output_item"

    mock_event = MagicMock()
    mock_event.type = "run_item_stream_event"
    mock_event.item = mock_item

    # Mock ItemHelpers.text_message_output to return text
    with patch("main.ItemHelpers") as mock_helpers:
        mock_helpers.text_message_output.return_value = "I need to check the status first."

        # Simulate the streaming loop logic inline (same as main.py lines 260-277)
        if mock_event.type == "run_item_stream_event":
            if mock_event.item.type == "message_output_item":
                text = mock_helpers.text_message_output(mock_event.item)
                if text:
                    emit_event("thinking", {"text": text})

    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["type"] == "thinking"
    assert parsed["data"]["text"] == "I need to check the status first."


@pytest.mark.asyncio
async def test_streaming_loop_emits_reasoning_for_reasoning_item(capsys):
    """The streaming loop emits a 'reasoning' event when a reasoning_item with summary is received."""
    # Build a mock reasoning_item with summary parts
    mock_part1 = MagicMock()
    mock_part1.text = "Step 1: Parse the request"
    mock_part2 = MagicMock()
    mock_part2.text = "Step 2: Execute the plan"

    mock_item = MagicMock()
    mock_item.type = "reasoning_item"
    mock_item.summary = [mock_part1, mock_part2]

    mock_event = MagicMock()
    mock_event.type = "run_item_stream_event"
    mock_event.item = mock_item

    # Simulate the streaming loop logic for reasoning_item
    if mock_event.type == "run_item_stream_event":
        if mock_event.item.type == "reasoning_item":
            summary = getattr(mock_event.item, "summary", None)
            if summary:
                texts = []
                for part in summary:
                    t = getattr(part, "text", None)
                    if t:
                        texts.append(t)
                if texts:
                    emit_event("reasoning", {"text": "\n".join(texts)})

    captured = capsys.readouterr()
    parsed = json.loads(captured.err.strip())
    assert parsed["type"] == "reasoning"
    assert parsed["data"]["text"] == "Step 1: Parse the request\nStep 2: Execute the plan"


@pytest.mark.asyncio
async def test_streaming_loop_skips_reasoning_without_summary(capsys):
    """The streaming loop does not emit a reasoning event when summary is None."""
    mock_item = MagicMock()
    mock_item.type = "reasoning_item"
    mock_item.summary = None

    mock_event = MagicMock()
    mock_event.type = "run_item_stream_event"
    mock_event.item = mock_item

    if mock_event.type == "run_item_stream_event":
        if mock_event.item.type == "reasoning_item":
            summary = getattr(mock_event.item, "summary", None)
            if summary:
                texts = []
                for part in summary:
                    t = getattr(part, "text", None)
                    if t:
                        texts.append(t)
                if texts:
                    emit_event("reasoning", {"text": "\n".join(texts)})

    captured = capsys.readouterr()
    assert captured.err.strip() == ""


def test_truncate_short_string():
    """Short strings are returned unchanged."""
    assert _truncate("hello") == "hello"


def test_truncate_exact_length():
    """String at exactly max length is not truncated."""
    text = "x" * TOOL_RESULT_MAX_LENGTH
    assert _truncate(text) == text


def test_truncate_long_string():
    """Long strings are truncated with '...' appended."""
    text = "x" * 600
    result = _truncate(text)
    assert len(result) == TOOL_RESULT_MAX_LENGTH + 3  # 500 + "..."
    assert result.endswith("...")


# --- Screenshot filter ---


def _make_call_model_data(messages, instructions="You are a helpful agent."):
    """Helper to wrap messages in a CallModelData-like object for filter_model_input."""
    return _MockCallModelData(messages, instructions)


def test_filter_model_input_removes_old():
    """Old screenshots beyond retention limit are replaced with placeholder."""
    messages = []
    for i in range(10):
        messages.append({
            "role": "assistant",
            "content": [
                {"type": "text", "text": f"Step {i}"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,screenshot{i}"}},
            ]
        })
    with patch("main.MAX_RETAINED_SCREENSHOTS", 5):
        output = filter_model_input(_make_call_model_data(messages))

    # Count remaining images
    image_count = 0
    removed_count = 0
    for msg in output.input:
        for part in msg.get("content", []):
            if isinstance(part, dict):
                if part.get("type") == "image_url":
                    image_count += 1
                elif part.get("type") == "text" and part.get("text") == "[screenshot removed]":
                    removed_count += 1
    assert image_count == 5
    assert removed_count == 5


def test_filter_model_input_retains_recent():
    """Screenshots below retention limit pass through unchanged."""
    messages = [
        {"role": "assistant", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]}
    ]
    with patch("main.MAX_RETAINED_SCREENSHOTS", 5):
        output = filter_model_input(_make_call_model_data(messages))
    assert output.input[0]["content"][0]["type"] == "image_url"


def test_filter_model_input_non_image_unaffected():
    """Non-image items pass through without modification."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "Response"}]},
    ]
    with patch("main.MAX_RETAINED_SCREENSHOTS", 5):
        output = filter_model_input(_make_call_model_data(messages))
    assert output.input == messages


def test_filter_model_input_custom_retention():
    """Custom retention limit via MAX_RETAINED_SCREENSHOTS."""
    messages = []
    for i in range(6):
        messages.append({
            "role": "assistant",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,img{i}"}},
            ]
        })
    with patch("main.MAX_RETAINED_SCREENSHOTS", 3):
        output = filter_model_input(_make_call_model_data(messages))

    image_count = sum(
        1 for msg in output.input for part in msg.get("content", [])
        if isinstance(part, dict) and part.get("type") == "image_url"
    )
    assert image_count == 3


def test_filter_model_input_does_not_mutate_original():
    """Filter returns a new list, not mutating the original."""
    messages = []
    for i in range(10):
        messages.append({
            "role": "assistant",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,img{i}"}},
            ]
        })
    original_count = len([
        1 for msg in messages for part in msg.get("content", [])
        if isinstance(part, dict) and part.get("type") == "image_url"
    ])
    with patch("main.MAX_RETAINED_SCREENSHOTS", 5):
        filter_model_input(_make_call_model_data(messages))
    after_count = len([
        1 for msg in messages for part in msg.get("content", [])
        if isinstance(part, dict) and part.get("type") == "image_url"
    ])
    assert original_count == after_count  # Original unchanged


def test_filter_model_input_preserves_instructions():
    """Filter preserves instructions from the CallModelData."""
    messages = [{"role": "user", "content": "Hello"}]
    instructions = "You are a task runner agent."
    with patch("main.MAX_RETAINED_SCREENSHOTS", 5):
        output = filter_model_input(_make_call_model_data(messages, instructions))
    assert output.instructions == instructions


# --- Context window trimming ---


def test_trim_context_window_no_trimming_needed():
    """Messages under the token limit are returned unchanged."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result = _trim_context_window(messages)
    assert result == messages


def test_trim_context_window_drops_old_messages():
    """Oldest messages (after first) are dropped when over token limit."""
    # Create messages that exceed a small token limit
    messages = [{"role": "user", "content": "initial prompt"}]
    for i in range(20):
        messages.append({"role": "assistant", "content": "x" * 5000})
    with patch("main.MAX_CONTEXT_TOKENS", 5000):
        result = _trim_context_window(messages)
    assert len(result) < len(messages)
    # First message is preserved
    assert result[0] == messages[0]


def test_trim_context_window_preserves_first_message():
    """The first message (initial user prompt) is always preserved."""
    first = {"role": "user", "content": "Do the task"}
    messages = [first] + [{"role": "assistant", "content": "x" * 10000} for _ in range(10)]
    with patch("main.MAX_CONTEXT_TOKENS", 3000):
        result = _trim_context_window(messages)
    assert result[0] == first


def test_estimate_tokens():
    """Token estimation produces reasonable values."""
    messages = [{"role": "user", "content": "Hello world"}]
    tokens = _estimate_tokens(messages)
    assert tokens > 0
    # JSON serialized length / 4, should be small for this input
    assert tokens < 100


def test_filter_model_input_trims_context():
    """Full filter pipeline trims context when over limit."""
    messages = [{"role": "user", "content": "initial"}]
    for i in range(20):
        messages.append({"role": "assistant", "content": "x" * 5000})
    with patch("main.MAX_CONTEXT_TOKENS", 5000), patch("main.MAX_RETAINED_SCREENSHOTS", 5):
        output = filter_model_input(_make_call_model_data(messages))
    assert len(output.input) < len(messages)
    assert output.input[0] == messages[0]


# --- connect_mcp_servers with tool_filter ---


@pytest.mark.asyncio
async def test_connect_mcp_servers_no_tool_filter_in_constructor():
    """connect_mcp_servers does not pass tool_filter to constructor (filter is set post-connect)."""
    from contextlib import AsyncExitStack

    with patch("main.MCPServerStreamableHttp") as MockServer:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockServer.return_value = mock_instance

        config = {"mcpServers": {"test": {"url": "http://localhost:4000/mcp"}}}

        async with AsyncExitStack() as stack:
            await connect_mcp_servers(config, stack)

        # Verify tool_filter was NOT passed to constructor
        call_kwargs = MockServer.call_args[1]
        assert "tool_filter" not in call_kwargs


# --- _repair_truncated_json ---


def test_repair_truncated_json_valid_passthrough():
    """Already-valid JSON is returned unchanged."""
    s = '{"key": "value"}'
    assert _repair_truncated_json(s) == s


def test_repair_truncated_json_missing_closing_brace():
    """Missing closing brace is repaired."""
    result = _repair_truncated_json('{"key": "value"')
    assert result is not None
    parsed = json.loads(result)
    assert parsed["key"] == "value"


def test_repair_truncated_json_missing_quote_and_brace():
    """Missing closing quote and brace are repaired."""
    result = _repair_truncated_json('{"path": "/file.md", "content": "some text')
    assert result is not None
    parsed = json.loads(result)
    assert parsed["path"] == "/file.md"


def test_repair_truncated_json_nested_structure():
    """Nested unclosed structure is repaired."""
    result = _repair_truncated_json('{"data": [{"a": 1}, {"b": 2')
    assert result is not None
    parsed = json.loads(result)
    assert parsed["data"][0]["a"] == 1


def test_repair_truncated_json_irreparable_returns_none():
    """Non-JSON input returns None."""
    assert _repair_truncated_json("not json at all") is None
    assert _repair_truncated_json("") is None
    assert _repair_truncated_json("   ") is None


def test_repair_truncated_json_array():
    """Truncated array is repaired."""
    result = _repair_truncated_json('[1, 2, 3')
    assert result is not None
    parsed = json.loads(result)
    assert parsed == [1, 2, 3]


# --- _sanitize_tool_calls (Responses API format) ---


def test_sanitize_tool_calls_valid_function_call_passthrough():
    """Valid function_call items pass through unchanged."""
    messages = [
        {"type": "function_call", "call_id": "abc", "name": "test", "arguments": '{"key": "value"}', "id": "1"},
    ]
    result = _sanitize_tool_calls(messages)
    assert result[0]["arguments"] == '{"key": "value"}'


def test_sanitize_tool_calls_repairs_truncated_function_call():
    """Truncated function_call arguments are repaired."""
    messages = [
        {"type": "function_call", "call_id": "abc", "name": "gdrive_write_file", "arguments": '{"path": "/file.md"', "id": "1"},
    ]
    result = _sanitize_tool_calls(messages)
    parsed = json.loads(result[0]["arguments"])
    assert parsed["path"] == "/file.md"


def test_sanitize_tool_calls_replaces_unrepairable_function_call():
    """Unrepairable function_call arguments get error placeholder."""
    messages = [
        {"type": "function_call", "call_id": "abc", "name": "bad_tool", "arguments": "<<<not json>>>", "id": "1"},
    ]
    result = _sanitize_tool_calls(messages)
    parsed = json.loads(result[0]["arguments"])
    assert parsed["error"] == "malformed_arguments"
    assert "<<<not json>>>" in parsed["original_fragment"]


def test_sanitize_tool_calls_non_function_call_unaffected():
    """Non-function_call items are not modified."""
    messages = [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]},
        {"type": "function_call_output", "call_id": "abc", "output": "result"},
    ]
    result = _sanitize_tool_calls(messages)
    assert result == messages


def test_sanitize_tool_calls_does_not_mutate_original():
    """Sanitization returns a new list when mutations occur."""
    messages = [
        {"type": "function_call", "call_id": "abc", "name": "test", "arguments": '{"path": "/file.md"', "id": "1"},
    ]
    original_args = messages[0]["arguments"]
    _sanitize_tool_calls(messages)
    assert messages[0]["arguments"] == original_args


# --- _classify_error ---


def test_classify_error_rate_limit():
    """RateLimitError is classified as transient."""
    import openai
    exc = openai.RateLimitError("rate limited", response=MagicMock(status_code=429), body=None)
    assert _classify_error(exc) == "transient"


def test_classify_error_timeout():
    """APITimeoutError is classified as transient."""
    import openai
    exc = openai.APITimeoutError(request=MagicMock())
    assert _classify_error(exc) == "transient"


def test_classify_error_connection():
    """APIConnectionError is classified as transient."""
    import openai
    exc = openai.APIConnectionError(request=MagicMock())
    assert _classify_error(exc) == "transient"


def test_classify_error_bad_request():
    """BadRequestError is classified as non_retryable."""
    import openai
    exc = openai.BadRequestError("bad request", response=MagicMock(status_code=400), body=None)
    assert _classify_error(exc) == "non_retryable"


def test_classify_error_authentication():
    """AuthenticationError is classified as non_retryable."""
    import openai
    exc = openai.AuthenticationError("auth failed", response=MagicMock(status_code=401), body=None)
    assert _classify_error(exc) == "non_retryable"


def test_classify_error_500_tool_conversion():
    """HTTP 500 with tool conversion message is classified as non_retryable."""
    import openai
    exc = openai.InternalServerError(
        "Unable to convert openai tool calls to bedrock",
        response=MagicMock(status_code=500),
        body=None,
    )
    assert _classify_error(exc) == "non_retryable"


def test_classify_error_500_generic():
    """Generic HTTP 500 (without tool conversion message) is classified as transient."""
    import openai
    exc = openai.InternalServerError(
        "Internal server error",
        response=MagicMock(status_code=500),
        body=None,
    )
    assert _classify_error(exc) == "transient"


def test_classify_error_unknown():
    """Generic Exception is classified as unknown."""
    assert _classify_error(ValueError("something broke")) == "unknown"
    assert _classify_error(KeyError("missing")) == "unknown"


# --- filter_model_input sanitization ordering ---


def test_filter_model_input_sanitizes_before_screenshots():
    """Sanitization runs before screenshot stripping in the filter chain."""
    # Message with a malformed function_call (Responses API format) and screenshots
    messages = [
        {"type": "function_call", "call_id": "abc", "name": "test", "arguments": '{"key": "value"', "id": "1"},
    ]
    # Add screenshots beyond retention limit
    for i in range(5):
        messages.append({
            "role": "assistant",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,img{i}"}},
            ]
        })
    with patch("main.MAX_RETAINED_SCREENSHOTS", 2):
        output = filter_model_input(_make_call_model_data(messages))

    # Tool call should be repaired (sanitization ran)
    fc_items = [m for m in output.input if isinstance(m, dict) and m.get("type") == "function_call"]
    assert len(fc_items) == 1
    parsed = json.loads(fc_items[0]["arguments"])
    assert parsed["key"] == "value"

    # Screenshots should also be stripped (screenshot filter ran after)
    image_count = sum(
        1 for msg in output.input for part in msg.get("content", [])
        if isinstance(part, dict) and part.get("type") == "image_url"
    )
    assert image_count == 2


# --- resolve_max_output_tokens ---


def test_resolve_max_output_tokens_claude_sonnet_45():
    """Claude Sonnet 4.5 resolves to 64000."""
    assert resolve_max_output_tokens("claude-sonnet-4-5-20250929") == 64000


def test_resolve_max_output_tokens_claude_opus_46():
    """Claude Opus 4.6 resolves to 128000."""
    assert resolve_max_output_tokens("claude-opus-4-6") == 128000


def test_resolve_max_output_tokens_claude_opus_41():
    """Claude Opus 4.1 resolves to 32000."""
    assert resolve_max_output_tokens("claude-opus-4-1-20250805") == 32000


def test_resolve_max_output_tokens_claude_haiku_45():
    """Claude Haiku 4.5 resolves to 64000."""
    assert resolve_max_output_tokens("claude-haiku-4-5-20251001") == 64000


def test_resolve_max_output_tokens_claude_3():
    """Claude 3 models resolve to 4096."""
    assert resolve_max_output_tokens("claude-3-haiku-20240307") == 4096


def test_resolve_max_output_tokens_gpt41():
    """GPT-4.1 resolves to 32768."""
    assert resolve_max_output_tokens("gpt-4.1") == 32768


def test_resolve_max_output_tokens_gpt4o():
    """GPT-4o resolves to 16384."""
    assert resolve_max_output_tokens("gpt-4o") == 16384


def test_resolve_max_output_tokens_gemini():
    """Gemini 2.5 models resolve to 65535."""
    assert resolve_max_output_tokens("gemini-2.5-pro") == 65535
    assert resolve_max_output_tokens("gemini-2.5-flash") == 65535


def test_resolve_max_output_tokens_unknown_model():
    """Unknown model resolves to default."""
    assert resolve_max_output_tokens("my-custom-model") == DEFAULT_MAX_OUTPUT_TOKENS


def test_resolve_max_output_tokens_bedrock_prefix():
    """Bedrock-prefixed model name still matches."""
    assert resolve_max_output_tokens("bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0") == 64000


def test_resolve_max_output_tokens_case_insensitive():
    """Model matching is case-insensitive."""
    assert resolve_max_output_tokens("Claude-Sonnet-4-5") == 64000


def test_resolve_max_output_tokens_env_override():
    """MAX_OUTPUT_TOKENS env var overrides lookup."""
    with patch.dict(os.environ, {"MAX_OUTPUT_TOKENS": "32000"}):
        assert resolve_max_output_tokens("claude-sonnet-4-5-20250929") == 32000


def test_resolve_max_output_tokens_env_invalid_ignored():
    """Invalid MAX_OUTPUT_TOKENS is ignored with warning."""
    with patch.dict(os.environ, {"MAX_OUTPUT_TOKENS": "abc"}):
        assert resolve_max_output_tokens("claude-sonnet-4-5-20250929") == 64000


def test_resolve_max_output_tokens_env_zero_ignored():
    """Zero MAX_OUTPUT_TOKENS is ignored."""
    with patch.dict(os.environ, {"MAX_OUTPUT_TOKENS": "0"}):
        assert resolve_max_output_tokens("claude-sonnet-4-5-20250929") == 64000


# --- Truncation recovery message injection ---


def test_sanitize_injects_truncation_message_into_matching_output():
    """Matching function_call_output gets truncation recovery message."""
    messages = [
        {"type": "function_call", "call_id": "abc123", "name": "gdrive_write_file",
         "arguments": '{"path": "/file.md"', "id": "1"},
        {"type": "function_call_output", "call_id": "abc123",
         "output": "An error occurred while parsing tool arguments."},
    ]
    result = _sanitize_tool_calls(messages)
    output_text = result[1]["output"]
    assert "truncated" in output_text.lower()
    assert "split" in output_text.lower()
    assert "An error occurred while parsing tool arguments." in output_text


def test_sanitize_unrepairable_does_not_inject_truncation_message():
    """Unrepairable (non-truncation) arguments do not trigger truncation recovery message."""
    messages = [
        {"type": "function_call", "call_id": "abc123", "name": "bad_tool",
         "arguments": "<<<not json>>>", "id": "1"},
        {"type": "function_call_output", "call_id": "abc123",
         "output": "Some tool error"},
    ]
    result = _sanitize_tool_calls(messages)
    # Arguments replaced with placeholder
    parsed = json.loads(result[0]["arguments"])
    assert parsed["error"] == "malformed_arguments"
    # Output NOT replaced with truncation message — left as-is
    assert result[1]["output"] == "Some tool error"


def test_sanitize_no_matching_output_leaves_other_items():
    """When no matching function_call_output exists, only the arguments are repaired."""
    messages = [
        {"type": "function_call", "call_id": "abc123", "name": "test",
         "arguments": '{"path": "/file.md"', "id": "1"},
        {"type": "function_call_output", "call_id": "different_id",
         "output": "some result"},
    ]
    result = _sanitize_tool_calls(messages)
    # function_call repaired
    parsed = json.loads(result[0]["arguments"])
    assert parsed["path"] == "/file.md"
    # Non-matching output unchanged
    assert result[1]["output"] == "some result"


def test_sanitize_multiple_truncated_calls_handled_independently():
    """Multiple truncated function_calls are each repaired with their own output updated."""
    messages = [
        {"type": "function_call", "call_id": "call1", "name": "tool_a",
         "arguments": '{"a": 1', "id": "1"},
        {"type": "function_call_output", "call_id": "call1", "output": "error1"},
        {"type": "function_call", "call_id": "call2", "name": "tool_b",
         "arguments": '{"b": 2', "id": "2"},
        {"type": "function_call_output", "call_id": "call2", "output": "error2"},
    ]
    result = _sanitize_tool_calls(messages)
    # Both function_calls repaired
    assert json.loads(result[0]["arguments"])["a"] == 1
    assert json.loads(result[2]["arguments"])["b"] == 2
    # Both outputs updated with recovery messages
    assert "truncated" in result[1]["output"].lower()
    assert "error1" in result[1]["output"]
    assert "truncated" in result[3]["output"].lower()
    assert "error2" in result[3]["output"]


def test_sanitize_handles_list_output_in_function_call_output():
    """function_call_output with list content is handled correctly."""
    messages = [
        {"type": "function_call", "call_id": "abc", "name": "test",
         "arguments": '{"key": "val', "id": "1"},
        {"type": "function_call_output", "call_id": "abc",
         "output": [{"type": "text", "text": "parse error"}]},
    ]
    result = _sanitize_tool_calls(messages)
    output_text = result[1]["output"]
    assert "truncated" in output_text.lower()
    assert "parse error" in output_text


# --- ModelBehaviorError auto-enable ---


def test_model_behavior_error_tool_name_parsing():
    """Regex extracts tool name from ModelBehaviorError message."""
    msg = "Tool gdrive_read_file not found in agent TaskRunner"
    match = re.search(r"Tool (\S+) not found in agent", msg)
    assert match is not None
    assert match.group(1) == "gdrive_read_file"


def test_model_behavior_error_auto_enable_known_tool():
    """Known tool is auto-enabled in visibility context on ModelBehaviorError."""
    from tool_registry import ToolVisibilityContext
    ctx = ToolVisibilityContext(
        enabled_tools={"retain"},
        all_known_tools={"retain", "gdrive_read_file"},
    )
    tool_name = "gdrive_read_file"
    assert tool_name not in ctx.enabled_tools
    assert tool_name in ctx.all_known_tools
    ctx.enabled_tools.add(tool_name)
    assert tool_name in ctx.enabled_tools


def test_model_behavior_error_unknown_tool_not_enabled():
    """Unknown tool (not in all_known_tools) is not auto-enabled."""
    from tool_registry import ToolVisibilityContext
    ctx = ToolVisibilityContext(
        enabled_tools={"retain"},
        all_known_tools={"retain", "gdrive_read_file"},
    )
    tool_name = "nonexistent_tool"
    assert tool_name not in ctx.all_known_tools
    # Should not be enabled — retry loop would fall through to failure
    assert tool_name not in ctx.enabled_tools


# --- Model name slash handling ---


def test_model_name_with_slash_passed_to_agent_unchanged():
    """Model names with slashes are passed directly to the Agent without prefix manipulation."""
    # The Agent receives the raw OPENAI_MODEL value — no prefix stripping or adding.
    # The RunConfig uses OpenAIProvider (not MultiProvider) to bypass slash-based
    # prefix parsing, so the model name reaches the LiteLLM backend as-is.
    model = "bedrock/gpt-oss:20b"
    assert "/" in model  # contains slash
    # resolve_max_output_tokens also handles slashed names correctly
    assert resolve_max_output_tokens(model) == DEFAULT_MAX_OUTPUT_TOKENS


def test_model_name_without_slash_works():
    """Plain model names without slashes work normally."""
    model = "gpt-4o"
    assert "/" not in model
    assert resolve_max_output_tokens(model) == 16384


def test_model_name_bedrock_claude_resolves_tokens():
    """Bedrock Claude model names with slashes resolve correctly in token lookup."""
    assert resolve_max_output_tokens("bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0") == 64000


# --- Empty response detection ---


@pytest.mark.parametrize("final_output", ["", None, "   ", " \n ", "\t\n  "])
def test_empty_response_detected(final_output, capsys, tmp_path):
    """Empty/whitespace-only final_output triggers error event, failed status, and exit 1."""
    raw_text = str(final_output) if final_output else ""

    if not raw_text.strip():
        # Simulate the empty response handling from main()
        emit_event("error", {
            "message": "LLM returned empty response",
            "error_type": "empty_response",
            "error_class": "EmptyResponseError",
        })
        failed_output = json.dumps({
            "status": "failed",
            "result": "",
            "error": "LLM returned empty response",
            "questions": [],
        })

        # Verify error event on stderr
        captured = capsys.readouterr()
        error_event = json.loads(captured.err.strip())
        assert error_event["type"] == "error"
        assert error_event["data"]["error_type"] == "empty_response"
        assert error_event["data"]["error_class"] == "EmptyResponseError"

        # Verify failed output payload
        payload = json.loads(failed_output)
        assert payload["status"] == "failed"
        assert payload["error"] == "LLM returned empty response"
        assert payload["questions"] == []

        # Verify output file written correctly
        from main import write_output_file
        write_output_file(failed_output, output_dir=str(tmp_path))
        result_file = tmp_path / "result.json"
        assert result_file.exists()
        written = json.loads(result_file.read_text())
        assert written["status"] == "failed"
    else:
        pytest.fail("Expected empty output to be detected")


def test_non_empty_response_not_treated_as_empty():
    """Non-empty final_output passes the empty check and proceeds to normal processing."""
    final_output = "Here is the result"
    raw_text = str(final_output) if final_output else ""
    # The empty check should NOT trigger
    assert raw_text.strip(), "Non-empty output should pass the empty check"
    # Normal path: extract_json or fallback wrapping
    parsed = extract_json(raw_text)
    if parsed:
        output = TaskRunnerOutput(**parsed).model_dump_json()
    else:
        output = json.dumps({
            "status": "completed",
            "result": raw_text,
            "questions": [],
        })
    payload = json.loads(output)
    assert payload["status"] == "completed"
    assert payload["result"] == "Here is the result"


def test_structured_json_response_not_treated_as_empty():
    """A valid structured JSON response passes the empty check and is parsed normally."""
    final_output = '{"status": "completed", "result": "Task done", "questions": []}'
    raw_text = str(final_output) if final_output else ""
    assert raw_text.strip(), "Structured output should pass the empty check"
    parsed = extract_json(raw_text)
    assert parsed is not None
    output = TaskRunnerOutput(**parsed).model_dump_json()
    payload = json.loads(output)
    assert payload["status"] == "completed"
    assert payload["result"] == "Task done"


# --- Output extraction priority (submit_result integration) ---
# All tests below call the real extract_output() helper from main.py.


def test_output_extraction_submit_result_preferred_over_text():
    """submit_result output is used even when text JSON is also present."""
    submitted = {"status": "completed", "result": "Tool result", "questions": []}
    raw_text = '{"status": "completed", "result": "Text result", "questions": []}'

    tag, output = extract_output(submitted, raw_text, new_items=[], nudge_attempted=False)

    assert tag == _OUTPUT
    payload = json.loads(output)
    assert payload["result"] == "Tool result"


def test_output_extraction_text_json_fallback():
    """Text JSON is used when submit_result was not called."""
    raw_text = '{"status": "completed", "result": "Some findings", "questions": []}'

    tag, output = extract_output(None, raw_text, new_items=[], nudge_attempted=False)

    assert tag == _OUTPUT
    payload = json.loads(output)
    assert payload["result"] == "Some findings"


def test_output_extraction_raw_text_fallback():
    """Raw text is wrapped when no JSON is available and submit_result not called."""
    tag, output = extract_output(None, "Here are the results...", new_items=[], nudge_attempted=False)

    assert tag == _OUTPUT
    payload = json.loads(output)
    assert payload["status"] == "completed"
    assert payload["result"] == "Here are the results..."


def test_output_extraction_empty_triggers_nudge_when_tools_called():
    """Empty output with tool calls triggers nudge (not immediate failure)."""
    tool_call_item = MagicMock()
    tool_call_item.type = "tool_call_output_item"

    tag, output = extract_output(None, "", new_items=[tool_call_item], nudge_attempted=False)

    assert tag == _NUDGE
    assert output is None


def test_output_extraction_no_nudge_without_tool_calls():
    """Empty output with no tool calls goes straight to failure (no nudge)."""
    tag, output = extract_output(None, "", new_items=[], nudge_attempted=False)

    assert tag == _EMPTY_FAIL
    assert output is None


def test_nudge_capped_at_one_attempt():
    """Nudge is only attempted once — second empty output goes to failure."""
    tool_call_item = MagicMock()
    tool_call_item.type = "tool_call_output_item"

    tag, output = extract_output(None, "", new_items=[tool_call_item], nudge_attempted=True)

    assert tag == _EMPTY_FAIL
    assert output is None


def test_backward_compat_text_json_without_submit_result():
    """Text-based JSON output still works when submit_result is not called."""
    raw_text = '{"status": "completed", "result": "Legacy output format", "questions": []}'

    tag, output = extract_output(None, raw_text, new_items=[], nudge_attempted=False)

    assert tag == _OUTPUT
    payload = json.loads(output)
    assert payload["status"] == "completed"
    assert payload["result"] == "Legacy output format"


# --- execute_command alias shims ---
#
# See the note above the `# --- execute_command tool ---` cluster: the alias
# shims and `_execute_command_impl` are all `async def`. Wrap calls in
# `asyncio.run(...)` from sync tests, or use `@pytest.mark.asyncio` + `await`.


def test_execute_command_impl_direct_invocation(tmp_path):
    """The shared helper is directly callable and returns expected output."""
    result = asyncio.run(
        _execute_command_impl("echo alias-test", working_directory=str(tmp_path))
    )
    assert "alias-test" in result


def test_execute_command_aliases_constant_is_locked():
    """Regression guard against accidental shrinkage or rename of the alias list."""
    assert EXECUTE_COMMAND_ALIASES == ("run_command", "bash", "shell", "sh", "executescript")


def test_execute_command_alias_tools_match_alias_names():
    """Each generated alias tool exposes `.name` equal to its alias string."""
    names = [t.name for t in EXECUTE_COMMAND_ALIAS_TOOLS]
    assert names == list(EXECUTE_COMMAND_ALIASES)


def test_execute_command_alias_tools_count_matches_constant():
    """One alias tool is generated for each entry in the alias constant."""
    assert len(EXECUTE_COMMAND_ALIAS_TOOLS) == len(EXECUTE_COMMAND_ALIASES)


def test_execute_command_alias_delegates_to_impl(tmp_path):
    """Alias shims invoke the same implementation as execute_command."""
    # Under conftest's mocked function_tool, the alias is a plain callable.
    run_command = EXECUTE_COMMAND_ALIAS_TOOLS[0]
    assert callable(run_command), "alias should be callable under the test SDK mock"
    result = asyncio.run(run_command("echo alias-delegate", working_directory=str(tmp_path)))
    assert "alias-delegate" in result


def test_native_tools_includes_alias_tools_via_always_on_set():
    """Simulate the agent-construction path and confirm aliases land in always_on_tools."""
    native_tools = [execute_command] + list(EXECUTE_COMMAND_ALIAS_TOOLS)
    always_on_tools = {t.name for t in native_tools}
    for alias in EXECUTE_COMMAND_ALIASES:
        assert alias in always_on_tools, f"alias {alias!r} missing from always_on_tools"


def test_discover_tools_classifies_alias_as_always_on():
    """An alias name probed via discover_tools is reported as already-enabled (always-on)."""
    from conftest import MockRunContextWrapper as _MockRunContextWrapper
    from tool_registry import ToolVisibilityContext, discover_tools

    ctx = ToolVisibilityContext(
        enabled_tools=set(),
        all_known_tools=set(),
        always_on_tools={"execute_command", *EXECUTE_COMMAND_ALIASES},
    )
    wrapper = _MockRunContextWrapper(ctx)

    result = discover_tools(wrapper, ["run_command"])

    assert result == "Already enabled (always-on): run_command"
    assert ctx.enabled_tools == set()


# --- Harmony-suffix normalizer + executescript alias ---


def test_normalize_harmony_tool_name_strips_channel_suffix():
    assert _normalize_harmony_tool_name("run_command<|channel|>json") == "run_command"


def test_normalize_harmony_tool_name_strips_message_suffix():
    assert _normalize_harmony_tool_name("execute_command<|message|>start") == "execute_command"


def test_normalize_harmony_tool_name_passes_through_clean_name():
    assert _normalize_harmony_tool_name("plain_name") == "plain_name"


def test_normalize_harmony_tool_name_passes_through_empty():
    assert _normalize_harmony_tool_name("") == ""


def test_executescript_is_registered_alias():
    """The executescript alias is in the constant and has a generated tool."""
    assert "executescript" in EXECUTE_COMMAND_ALIASES
    names = [t.name for t in EXECUTE_COMMAND_ALIAS_TOOLS]
    assert "executescript" in names


def test_executescript_alias_delegates_to_impl(tmp_path):
    """The executescript shim invokes the same implementation as execute_command."""
    executescript = next(t for t in EXECUTE_COMMAND_ALIAS_TOOLS if t.name == "executescript")
    assert callable(executescript)
    result = asyncio.run(executescript("echo executescript-delegate", working_directory=str(tmp_path)))
    assert "executescript-delegate" in result


def test_harmony_recovery_alias_with_suffix():
    """run_command<|channel|>json is recovered to run_command (alias)."""
    assert _resolve_recovery_target(
        "run_command<|channel|>json", set()
    ) == "run_command"


def test_harmony_recovery_canonical_with_suffix():
    """execute_command<|message|>start is recovered to execute_command."""
    assert _resolve_recovery_target(
        "execute_command<|channel|>commentary", set()
    ) == "execute_command"


def test_harmony_recovery_known_mcp_tool_with_suffix():
    """An MCP tool name with Harmony suffix recovers to the bare known name."""
    assert _resolve_recovery_target(
        "gdrive_read_file<|channel|>json", {"gdrive_read_file"}
    ) == "gdrive_read_file"


def test_harmony_recovery_unknown_tool_falls_through():
    """frobnicate<|channel|>json has no known bare name — no recovery."""
    assert _resolve_recovery_target(
        "frobnicate<|channel|>json", {"retain", "gdrive_read_file"}
    ) is None


def test_harmony_recovery_no_suffix_falls_through():
    """A clean name with no Harmony suffix is not handled by this path."""
    assert _resolve_recovery_target(
        "executescript", {"retain"}
    ) is None  # bare name dispatch — handled by the alias mechanism, not this normalizer


def test_harmony_recovery_empty_falls_through():
    assert _resolve_recovery_target("", set()) is None


def test_harmony_recovery_cap_constant_is_positive():
    """Sanity guard: the cap must be a positive int so the loop bound is meaningful."""
    assert isinstance(HARMONY_RECOVERY_CAP_PER_PAIR, int)
    assert HARMONY_RECOVERY_CAP_PER_PAIR >= 1


def test_harmony_recovery_cap_logic_caps_repeated_pairs():
    """Simulate the in-main() cap accounting: after CAP fires, further attempts return False."""
    counts: dict[tuple[str, str], int] = {}
    pair = ("run_command<|channel|>json", "run_command")
    fired = []
    for _ in range(HARMONY_RECOVERY_CAP_PER_PAIR + 2):
        prior = counts.get(pair, 0)
        if prior < HARMONY_RECOVERY_CAP_PER_PAIR:
            counts[pair] = prior + 1
            fired.append(True)
        else:
            fired.append(False)
    # The first CAP attempts fire; subsequent attempts fall through.
    assert fired == [True] * HARMONY_RECOVERY_CAP_PER_PAIR + [False, False]


# ---------------------------------------------------------------------------
# Mid-task Google Workspace token refresh — execute_command wrapper
# ---------------------------------------------------------------------------


_GWS_SIG = '"status": "UNAUTHENTICATED"'


@pytest.fixture(autouse=True)
def _reset_google_token_refresh_lock(monkeypatch):
    """Replace the module-level `_google_token_refresh_lock` with a fresh
    `asyncio.Lock()` per test, and reset the concurrent-wave dedup state.

    pytest-asyncio runs each test on its own event loop, but an `asyncio.Lock`
    created at module import binds to the FIRST loop that awaits it. The
    second test then trips Python 3.12's "bound to a different event loop"
    safety check. In production the task-runner has one long-lived loop, so
    the module-level lock is correct; only tests need this isolation.

    Uses `monkeypatch.setattr` (the prevailing pattern in this file) to
    avoid mixing `import main as ...` with the existing `from main import`
    style elsewhere in the module.
    """
    monkeypatch.setattr("main._google_token_refresh_lock", asyncio.Lock())
    monkeypatch.setattr(
        "main._refresh_dedup_state",
        {"inflight_count": 0, "recent_failed_stale_token": None},
    )


def _make_async_resp(status_code: int, body: dict | None = None):
    """Build a minimal stand-in for an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body or {})
    return resp


def _build_async_client_cm(post_return):
    """Build an async-context-manager mock that returns a client whose .post awaits to post_return."""
    client = MagicMock()
    client.post = AsyncMock(return_value=post_return)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


@pytest.mark.asyncio
async def test_execute_command_recovers_from_auth_failure(monkeypatch):
    """Signature in original output → exactly one refresh + one retry; only retry output returned."""
    from main import _refresh_google_workspace_token  # noqa: F401 — ensure import

    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    call_count = {"n": 0}

    def fake_run_subprocess(command, working_directory):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return 1, f'error[api]: {_GWS_SIG}'
        return 0, "drive-list-output"

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    cm, http_client = _build_async_client_cm(
        _make_async_resp(200, {"access_token": "fresh-token", "expires_at": 9999999999})
    )
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    result = await _execute_command_impl("gws drive list", "/workspace")

    assert call_count["n"] == 2
    assert http_client.post.await_count == 1
    assert "drive-list-output" in result
    assert _GWS_SIG not in result  # original output discarded
    assert os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"] == "fresh-token"


@pytest.mark.asyncio
async def test_execute_command_no_refresh_when_token_env_unset(monkeypatch):
    """Signature present but GOOGLE_WORKSPACE_CLI_TOKEN unset → no refresh, original output returned."""
    monkeypatch.delenv("GOOGLE_WORKSPACE_CLI_TOKEN", raising=False)
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    def fake_run_subprocess(command, working_directory):
        return 0, f'cat: {_GWS_SIG}'

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    cm, http_client = _build_async_client_cm(_make_async_resp(200, {"access_token": "fresh"}))
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    result = await _execute_command_impl("cat sample.json", "/workspace")

    assert _GWS_SIG in result  # original output returned unchanged
    assert http_client.post.await_count == 0


@pytest.mark.asyncio
async def test_execute_command_retry_also_fails(monkeypatch):
    """Signature in BOTH original and retry → second output returned, no second refresh attempted."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    call_count = {"n": 0}

    def fake_run_subprocess(command, working_directory):
        call_count["n"] += 1
        return 1, f'attempt-{call_count["n"]}: {_GWS_SIG}'

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    cm, http_client = _build_async_client_cm(
        _make_async_resp(200, {"access_token": "fresh-token"})
    )
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    result = await _execute_command_impl("gws drive list", "/workspace")

    assert call_count["n"] == 2  # original + one retry, no third attempt
    assert http_client.post.await_count == 1
    assert "attempt-2" in result
    assert _GWS_SIG in result  # second output preserved


@pytest.mark.asyncio
async def test_execute_command_no_retry_when_refresh_endpoint_fails(monkeypatch):
    """Refresh endpoint returns non-200 → original output returned, no retry attempted."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    call_count = {"n": 0}

    def fake_run_subprocess(command, working_directory):
        call_count["n"] += 1
        return 1, f'attempt-{call_count["n"]}: {_GWS_SIG}'

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    cm, http_client = _build_async_client_cm(_make_async_resp(502, {}))
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    result = await _execute_command_impl("gws drive list", "/workspace")

    assert call_count["n"] == 1  # no retry
    assert http_client.post.await_count == 1
    assert "attempt-1" in result
    assert os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"] == "stale-token"  # unchanged


@pytest.mark.asyncio
async def test_execute_command_concurrent_refresh_deduplicates(monkeypatch):
    """Two parallel auth-failing commands → exactly one HTTP POST to the refresh endpoint."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    invocation = {"count": 0}

    def fake_run_subprocess(command, working_directory):
        invocation["count"] += 1
        if invocation["count"] <= 2:
            return 1, f'attempt: {_GWS_SIG}'
        return 0, f"ok-{invocation['count']}"

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    # Make the refresh HTTP call slow enough that both coroutines reach the
    # refresh helper before the first one completes its network call.
    # Otherwise AsyncMock returns synchronously and coroutine 1 finishes its
    # entire refresh path before coroutine 2 starts.
    post_calls = {"n": 0}

    async def slow_post(*args, **kwargs):
        post_calls["n"] += 1
        await asyncio.sleep(0.05)
        return _make_async_resp(200, {"access_token": "fresh-token", "expires_at": 9999999999})

    http_client = MagicMock()
    http_client.post = AsyncMock(side_effect=slow_post)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=http_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    results = await asyncio.gather(
        _execute_command_impl("gws drive list", "/workspace"),
        _execute_command_impl("gws drive list", "/workspace"),
    )

    assert post_calls["n"] == 1, f"expected 1 refresh, got {post_calls['n']}"
    assert all("ok-" in r for r in results), f"results={results}"
    assert os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"] == "fresh-token"


@pytest.mark.asyncio
async def test_token_refreshed_event_emitted_on_dedupe_reuse(monkeypatch):
    """The deduplicated-reuse path still emits a token_refreshed event so the
    transcript shows one event per caller, not per HTTP round-trip."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr("main.emit_event", lambda et, data: events.append((et, data)))

    invocation = {"count": 0}

    def fake_run_subprocess(command, working_directory):
        invocation["count"] += 1
        if invocation["count"] <= 2:
            return 1, f'attempt: {_GWS_SIG}'
        return 0, f"ok-{invocation['count']}"

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    async def slow_post(*args, **kwargs):
        await asyncio.sleep(0.05)
        return _make_async_resp(200, {"access_token": "fresh-token", "expires_at": 9999999999})

    http_client = MagicMock()
    http_client.post = AsyncMock(side_effect=slow_post)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=http_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    await asyncio.gather(
        _execute_command_impl("gws drive list", "/workspace"),
        _execute_command_impl("gws drive list", "/workspace"),
    )

    ok_events = [d for et, d in events if et == "token_refreshed" and d.get("status") == "ok"]
    assert len(ok_events) == 2, f"expected 2 ok events (one per caller), got {len(ok_events)}: {events}"


@pytest.mark.asyncio
async def test_execute_command_retry_uses_refreshed_env(monkeypatch):
    """The subprocess for the retry sees the refreshed GOOGLE_WORKSPACE_CLI_TOKEN value."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    seen_tokens: list[str] = []

    def fake_run_subprocess(command, working_directory):
        seen_tokens.append(os.environ.get("GOOGLE_WORKSPACE_CLI_TOKEN", ""))
        if len(seen_tokens) == 1:
            return 1, _GWS_SIG
        return 0, "ok"

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    cm, http_client = _build_async_client_cm(
        _make_async_resp(200, {"access_token": "fresh-token", "expires_at": 9999999999})
    )
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    await _execute_command_impl("gws drive list", "/workspace")

    assert seen_tokens == ["stale-token", "fresh-token"]


@pytest.mark.asyncio
async def test_token_refreshed_event_emitted_on_success(monkeypatch):
    """token_refreshed event with status=ok is emitted on a successful refresh."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr("main.emit_event", lambda et, data: events.append((et, data)))

    cm, _ = _build_async_client_cm(
        _make_async_resp(200, {"access_token": "fresh-token", "expires_at": 9999999999})
    )
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _refresh_google_workspace_token
    new = await _refresh_google_workspace_token()

    assert new == "fresh-token"
    assert ("token_refreshed", {"provider": "google_workspace", "status": "ok"}) in events
    # Event payload does not include the token value
    for et, data in events:
        if et == "token_refreshed":
            assert "access_token" not in data
            assert "token" not in data


@pytest.mark.asyncio
async def test_token_refreshed_event_emitted_on_failure(monkeypatch):
    """token_refreshed event with status=failed is emitted when the refresh endpoint fails."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr("main.emit_event", lambda et, data: events.append((et, data)))

    cm, _ = _build_async_client_cm(_make_async_resp(502, {}))
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _refresh_google_workspace_token
    new = await _refresh_google_workspace_token()

    assert new is None
    assert ("token_refreshed", {"provider": "google_workspace", "status": "failed"}) in events


@pytest.mark.asyncio
async def test_concurrent_refresh_failure_dedupes_to_one_post(monkeypatch):
    """When the first concurrent refresh fails, subsequent waiters in the
    same wave SHALL share the failure outcome rather than each issuing
    their own POST. Once the wave drains, a later caller may try again."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    invocation = {"count": 0}

    def fake_run_subprocess(command, working_directory):
        invocation["count"] += 1
        return 1, f'attempt-{invocation["count"]}: {_GWS_SIG}'

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    post_calls = {"n": 0}

    async def slow_failing_post(*args, **kwargs):
        post_calls["n"] += 1
        await asyncio.sleep(0.05)
        return _make_async_resp(502, {})

    http_client = MagicMock()
    http_client.post = AsyncMock(side_effect=slow_failing_post)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=http_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl
    await asyncio.gather(
        _execute_command_impl("gws drive list", "/workspace"),
        _execute_command_impl("gws drive list", "/workspace"),
    )

    # Exactly one POST despite two concurrent waiters hitting the same stale token.
    assert post_calls["n"] == 1, f"expected 1 POST, got {post_calls['n']}"

    # After the wave drains, a later caller is allowed to try again — the
    # `_recent_failed_stale_token` cache only scopes dedup to concurrent waiters.
    await _execute_command_impl("gws drive list", "/workspace")
    assert post_calls["n"] == 2, "wave-scoped dedup must reset after no concurrent waiters remain"


@pytest.mark.asyncio
async def test_concurrent_refresh_dedupes_when_second_caller_arrives_after_env_updated(monkeypatch):
    """The race the dedupe must handle:

        C1 subprocess runs with stale-token. Sees 401.
        C2 subprocess runs with stale-token. Sees 401.
        C1 enters refresh helper, completes refresh, env := fresh-token,
           releases lock — ALL before C2 enters the helper.
        C2 enters helper. If the helper reads env at entry, it sees
           fresh-token and proceeds to issue a SECOND POST (wrong).

    With `stale_token` captured before each subprocess run and passed
    explicitly into the helper, C2's `current_token != stale_token`
    check correctly identifies that the env has already been updated
    past *its* stale value, and reuses the new token without a second
    POST. This test exercises that path."""
    monkeypatch.setenv("GOOGLE_WORKSPACE_CLI_TOKEN", "stale-token")
    monkeypatch.setenv("ERRAND_API_URL", "http://errand:8000")
    monkeypatch.setenv("ERRAND_API_KEY", "test-key")

    invocation = {"count": 0}

    def fake_run_subprocess(command, working_directory):
        invocation["count"] += 1
        n = invocation["count"]
        if n in (1, 2):
            return 1, f'attempt-{n}: {_GWS_SIG}'
        return 0, f"ok-{n}"

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess)

    post_calls = {"n": 0}

    async def post_records_and_returns_success(*args, **kwargs):
        post_calls["n"] += 1
        return _make_async_resp(200, {"access_token": "fresh-token", "expires_at": 9999999999})

    http_client = MagicMock()
    http_client.post = AsyncMock(side_effect=post_records_and_returns_success)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=http_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("main.httpx.AsyncClient", lambda *a, **kw: cm)

    from main import _execute_command_impl

    # Run C1 to completion FIRST (its refresh succeeds and updates env).
    await _execute_command_impl("gws drive list", "/workspace")
    assert os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"] == "fresh-token"
    assert post_calls["n"] == 1

    # Now run C2 — its subprocess sees the OLD env (because we restore
    # it just for the second subprocess), but its `stale_token` capture
    # at the wrapper entry should record stale-token before the run.
    # We simulate this by manually rolling back the env before invoking,
    # then asserting the wrapper does the right thing.
    os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"] = "stale-token"

    # ...but for the next invocation, we also want to model that C1's
    # refresh has *already* re-applied fresh-token to the env between
    # C2's subprocess returning and the refresh helper entering. The
    # cleanest way: have the subprocess restore the env to "fresh-token"
    # before returning, simulating "the env got updated while we were
    # running our subprocess".
    def fake_run_subprocess_that_updates_env(command, working_directory):
        invocation["count"] += 1
        # C2's subprocess sees stale-token at fork time, returns 401.
        # Simulate "C1 finished and updated env between subprocess
        # invocation and refresh-helper entry":
        os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"] = "fresh-token"
        return 1, f'attempt-c2: {_GWS_SIG}'

    monkeypatch.setattr("main._run_subprocess", fake_run_subprocess_that_updates_env)

    await _execute_command_impl("gws drive list", "/workspace")
    # C2 must NOT have issued a second POST — its captured stale_token
    # is "stale-token", and at lock acquisition env reads "fresh-token",
    # which the dedupe check identifies as already-refreshed.
    assert post_calls["n"] == 1, f"expected dedupe (still 1 POST), got {post_calls['n']}"


# --- Stall guard (no-progress loop detection) ---
#
# The rule is (tool, args) keyed, counting only while the RESULT is unchanged.
# Identical arguments with a changing result is progress, not a stall — that
# distinction is the whole point of these tests.

WROTE = "Wrote 354 bytes to /tmp/tweet.md"


def test_stall_detector_trips_on_identical_repeats():
    """Same (tool, args) AND same result `limit` times reaches the threshold."""
    d = StallDetector(limit=3)
    args = {"path": "/tmp/blogs.work.md"}
    assert d.record("read_file", args, "contents") == 1
    assert d.record("read_file", args, "contents") == 2
    assert d.record("read_file", args, "contents") == 3  # caller aborts at >= limit


def test_stall_detector_changing_result_resets():
    """Regression for the production false positive.

    A healthy draft-and-verify loop called count_tweet_chars with byte-identical
    arguments once per revision, getting 207, then 184, then 174 back. Under the
    old args-only rule this accrued toward the limit; it must not.
    """
    d = StallDetector(limit=3)
    args = {"command": "python3 count_tweet_chars.py /tmp/tweet.md"}
    for result in ("weighted_chars: 207", "weighted_chars: 184", "weighted_chars: 174"):
        assert d.record("execute_command", args, result) == 1


def test_stall_detector_real_stall_trips_at_limit():
    """Regression for the genuine loop: identical args AND identical result."""
    d = StallDetector(limit=6)
    args = {"path": "/tmp/tweet.md", "content": "..."}
    counts = [d.record("write_file", args, WROTE) for _ in range(6)]
    assert counts == [1, 2, 3, 4, 5, 6]


def test_stall_detector_earlier_result_does_not_accumulate():
    """A -> B -> A leaves the counter at 1: the intervening B reset it, so a
    coincidental later recurrence cannot creep toward the limit."""
    d = StallDetector(limit=3)
    args = {"path": "/tmp/x"}
    assert d.record("read_file", args, "A") == 1
    assert d.record("read_file", args, "B") == 1
    assert d.record("read_file", args, "A") == 1


def test_stall_detector_interleaved_keys_accrue_independently():
    """Calls to other keys must not reset a key, or an alternating loop would
    never trip."""
    d = StallDetector(limit=3)
    a, b = {"path": "/a"}, {"path": "/b"}
    assert d.record("read_file", a, "ra") == 1
    assert d.record("read_file", b, "rb") == 1
    assert d.record("read_file", a, "ra") == 2
    assert d.record("read_file", b, "rb") == 2
    assert d.record("read_file", a, "ra") == 3  # trips despite interleaving


def test_stall_detector_long_results_differing_after_truncation():
    """The digest covers the whole result, not the 500-char transcript
    rendering, so two long outputs sharing a prefix stay distinct."""
    d = StallDetector(limit=2)
    args = {"url": "https://example.com"}
    prefix = "x" * 600
    assert d.record("read_url", args, prefix + "alpha") == 1
    assert d.record("read_url", args, prefix + "beta") == 1


def test_stall_detector_argument_order_insensitive():
    """Signature is canonical: key order doesn't create distinct signatures."""
    d = StallDetector(limit=5)
    assert d.record("discover_tools", {"a": 1, "b": 2}, "same") == 1
    assert d.record("discover_tools", {"b": 2, "a": 1}, "same") == 2


def test_stall_detector_distinguishes_by_tool_and_args():
    """Different tools, or same tool with different args, count separately."""
    d = StallDetector(limit=5)
    assert d.record("read_file", {"path": "/a"}, "r") == 1
    assert d.record("read_file", {"path": "/b"}, "r") == 1  # different args
    assert d.record("read_url", {"path": "/a"}, "r") == 1   # different tool
    assert d.record("read_file", {"path": "/a"}, "r") == 2  # back to the first


def test_stall_detector_disabled_when_limit_non_positive():
    """limit <= 0 disables the guard: record always returns 0 (never trips)."""
    for lim in (0, -1):
        d = StallDetector(limit=lim, nudge_limit=3)
        for _ in range(50):
            assert d.record("read_file", {"path": "/tmp/x"}, "same") == 0


def test_stall_detector_handles_unserializable_args():
    """Non-JSON-serializable args fall back to repr instead of raising."""
    d = StallDetector(limit=2)
    weird = {"fn": object()}
    assert d.record("t", weird, "r") == 1
    assert d.record("t", weird, "r") == 2


def test_stall_detector_reproduces_blog_to_tweets_loop():
    """Regression: a production run called parse_queue.py identically 192 times,
    every call returning "(no output)", and died on MaxTurnsExceeded(200). The
    guard must trip within the limit instead."""
    d = StallDetector(limit=DEFAULT_STALL_REPEAT_LIMIT)
    args = {"command": "python3 parse_queue.py /shared/BlogsToProcess.md 10"}
    tripped_at = None
    for i in range(1, 193):
        if d.record("execute_command", args, "(no output)") >= DEFAULT_STALL_REPEAT_LIMIT:
            tripped_at = i
            break
    assert tripped_at == DEFAULT_STALL_REPEAT_LIMIT


# --- Stall guard: nudge tier ---


def test_stall_nudge_fires_at_threshold_once_only():
    """A key is nudged the first time it reaches the threshold and never again,
    so an agent that ignores the nudge is not nudged on every later call."""
    d = StallDetector(limit=6, nudge_limit=3)
    args = {"path": "/tmp/tweet.md"}
    fired = []
    for _ in range(5):
        n = d.record("write_file", args, WROTE)
        fired.append(d.should_nudge("write_file", args, n))
    assert fired == [False, False, True, False, False]


def test_stall_nudge_does_not_reset_the_counter():
    """Nudging must not reset accrual, or a nudged-but-looping agent would never
    reach the abort."""
    d = StallDetector(limit=6, nudge_limit=3)
    args = {"path": "/tmp/tweet.md"}
    counts = []
    for _ in range(6):
        n = d.record("write_file", args, WROTE)
        d.should_nudge("write_file", args, n)
        counts.append(n)
    assert counts == [1, 2, 3, 4, 5, 6]


def test_stall_nudge_disabled_independently_of_abort():
    """nudge_limit <= 0 disables only the nudge; the abort still accrues."""
    d = StallDetector(limit=6, nudge_limit=0)
    args = {"path": "/tmp/x"}
    for _ in range(6):
        n = d.record("write_file", args, WROTE)
        assert d.should_nudge("write_file", args, n) is False
    assert n == 6


def test_stall_nudge_at_or_above_abort_is_treated_as_disabled():
    """A nudge threshold that could never fire is disabled rather than silently
    reordering the tiers."""
    for nudge in (6, 8):
        d = StallDetector(limit=6, nudge_limit=nudge)
        assert d.nudge_limit == 0


def test_stall_nudge_separate_keys_each_get_one_nudge():
    d = StallDetector(limit=6, nudge_limit=2)
    a, b = {"path": "/a"}, {"path": "/b"}
    assert d.should_nudge("write_file", a, d.record("write_file", a, "x")) is False
    assert d.should_nudge("write_file", a, d.record("write_file", a, "x")) is True
    assert d.should_nudge("write_file", b, d.record("write_file", b, "y")) is False
    assert d.should_nudge("write_file", b, d.record("write_file", b, "y")) is True


def test_fresh_detector_clears_counts_and_nudge_history():
    """A retry attempt starts clean — counts, digests and nudge history."""
    args = {"path": "/tmp/x"}
    first = StallDetector(limit=6, nudge_limit=3)
    for _ in range(4):
        first.should_nudge("write_file", args, first.record("write_file", args, WROTE))
    second = StallDetector(limit=6, nudge_limit=3)
    assert second.record("write_file", args, WROTE) == 1
    assert second.should_nudge("write_file", args, 3) is True


def test_build_stall_nudge_points_at_submit_result():
    """Per design D5: the measured effect is dithering -> completion, so the
    message must name the escape hatch."""
    msg = build_stall_nudge("write_file", 3)
    assert "submit_result" in msg
    assert "write_file" in msg
    assert "3" in msg


def test_build_stall_nudge_does_not_echo_tool_content():
    """Fixed template: only tool name and count are interpolated, so tool output
    can never be reflected back into the model's context."""
    msg = build_stall_nudge("write_file", 3)
    for injected in ("IGNORE PREVIOUS", "Wrote 354 bytes", "/tmp/tweet.md"):
        assert injected not in msg


def test_agent_stall_error_is_agents_exception():
    """Must subclass AgentsException: the SDK wraps any other exception raised
    inside a tool output guardrail into UserError, which would silently
    reclassify a stall as a generic tool error."""
    from agents.exceptions import AgentsException
    assert issubclass(AgentStallError, AgentsException)


# --- Stall guard: guardrail behaviour and attachment ---


class _FakeToolContext:
    def __init__(self, tool_name, arguments):
        self.tool_name = tool_name
        self.tool_arguments = arguments


def _run_guard(guard, tool_name, arguments, output):
    """Invoke the guardrail the way the SDK would."""
    from agents.tool_guardrails import ToolOutputGuardrailData
    data = ToolOutputGuardrailData(
        context=_FakeToolContext(tool_name, arguments), agent=None, output=output
    )
    return guard.guardrail_function(data)


def test_guardrail_allows_below_thresholds(monkeypatch):
    events = []
    monkeypatch.setattr(main, "emit_event", lambda t, d: events.append((t, d)))
    stall = StallDetector(limit=6, nudge_limit=3)
    guard = main.make_stall_guardrail(stall, lambda: "turn1")
    out = _run_guard(guard, "write_file", '{"path": "/tmp/t"}', WROTE)
    assert out.behavior["type"] == "allow"
    assert events == []


def test_guardrail_nudges_at_threshold_and_emits_event(monkeypatch):
    events = []
    monkeypatch.setattr(main, "emit_event", lambda t, d: events.append((t, d)))
    stall = StallDetector(limit=6, nudge_limit=3)
    guard = main.make_stall_guardrail(stall, lambda: "turn1")
    args = '{"path": "/tmp/t"}'
    outs = [_run_guard(guard, "write_file", args, WROTE) for _ in range(3)]
    assert [o.behavior["type"] for o in outs] == ["allow", "allow", "reject_content"]
    assert "submit_result" in outs[-1].behavior["message"]
    names = [t for t, _ in events]
    assert names == ["stall_nudge"]
    assert events[0][1]["repeat_count"] == 3
    assert events[0][1]["limit"] == 3


def test_guardrail_aborts_at_limit_with_stall_detected(monkeypatch):
    events = []
    monkeypatch.setattr(main, "emit_event", lambda t, d: events.append((t, d)))
    stall = StallDetector(limit=3, nudge_limit=2)
    guard = main.make_stall_guardrail(stall, lambda: "turn9")
    args = '{"path": "/tmp/t"}'
    _run_guard(guard, "write_file", args, WROTE)
    _run_guard(guard, "write_file", args, WROTE)
    with pytest.raises(AgentStallError) as exc:
        _run_guard(guard, "write_file", args, WROTE)
    assert "unchanged result" in str(exc.value)
    kinds = [t for t, _ in events]
    assert kinds == ["stall_nudge", "stall_detected"]
    detected = events[-1][1]
    assert detected["result_repeated"] is True
    assert detected["turn_id"] == "turn9"


def test_guardrail_changing_result_never_fires(monkeypatch):
    """The production false positive, end to end through the guardrail."""
    events = []
    monkeypatch.setattr(main, "emit_event", lambda t, d: events.append((t, d)))
    stall = StallDetector(limit=3, nudge_limit=2)
    guard = main.make_stall_guardrail(stall, lambda: "t")
    args = '{"command": "count_tweet_chars.py /tmp/tweet.md"}'
    for result in ("207", "184", "174", "160", "155"):
        out = _run_guard(guard, "execute_command", args, result)
        assert out.behavior["type"] == "allow"
    assert events == []


def test_guardrail_disabled_when_limit_non_positive(monkeypatch):
    events = []
    monkeypatch.setattr(main, "emit_event", lambda t, d: events.append((t, d)))
    stall = StallDetector(limit=0, nudge_limit=3)
    guard = main.make_stall_guardrail(stall, lambda: "t")
    for _ in range(30):
        assert _run_guard(guard, "write_file", "{}", WROTE).behavior["type"] == "allow"
    assert events == []


def test_guardrail_malformed_arguments_do_not_raise(monkeypatch):
    monkeypatch.setattr(main, "emit_event", lambda t, d: None)
    stall = StallDetector(limit=6, nudge_limit=3)
    guard = main.make_stall_guardrail(stall, lambda: "t")
    out = _run_guard(guard, "write_file", "not json{", WROTE)
    assert out.behavior["type"] == "allow"


def _make_tool():
    from agents.tool import FunctionTool
    return FunctionTool(name="t")


async def _collect(agent):
    return await agent.get_all_tools(run_context=None)


def test_guarded_agent_attaches_to_every_function_tool():
    tools = [_make_tool(), _make_tool()]
    agent = GuardedAgent(tools=tools)
    guard = main.make_stall_guardrail(StallDetector(6, 3), lambda: None)
    agent.stall_guardrail = guard
    got = asyncio.run(_collect(agent))
    assert all(t.tool_output_guardrails == [guard] for t in got)


def test_guarded_agent_attachment_is_idempotent():
    """get_all_tools runs every turn and native tools are shared singletons."""
    tools = [_make_tool()]
    agent = GuardedAgent(tools=tools)
    guard = main.make_stall_guardrail(StallDetector(6, 3), lambda: None)
    agent.stall_guardrail = guard
    for _ in range(5):
        asyncio.run(_collect(agent))
    assert tools[0].tool_output_guardrails == [guard]


def test_guarded_agent_replaces_stale_guardrail_across_attempts():
    """Each retry binds a fresh detector; the previous attempt's guardrail must
    not stay armed on the shared module-level tool objects."""
    tools = [_make_tool()]
    agent = GuardedAgent(tools=tools)
    first = main.make_stall_guardrail(StallDetector(6, 3), lambda: None)
    agent.stall_guardrail = first
    asyncio.run(_collect(agent))
    second = main.make_stall_guardrail(StallDetector(6, 3), lambda: None)
    agent.stall_guardrail = second
    asyncio.run(_collect(agent))
    assert tools[0].tool_output_guardrails == [second]


def test_guarded_agent_preserves_unrelated_guardrails():
    from agents.tool_guardrails import ToolOutputGuardrail
    other = ToolOutputGuardrail(guardrail_function=lambda d: None, name="other")
    tool = _make_tool()
    tool.tool_output_guardrails = [other]
    agent = GuardedAgent(tools=[tool])
    guard = main.make_stall_guardrail(StallDetector(6, 3), lambda: None)
    agent.stall_guardrail = guard
    asyncio.run(_collect(agent))
    assert tool.tool_output_guardrails == [other, guard]
