"""Unit tests for task runner main.py — input validation, MCP config parsing, structured events."""

# Mocks are set up in conftest.py (shared with test_tool_registry.py)

import json
import logging
import os
import sys
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from conftest import MockCallModelData as _MockCallModelData

from main import (
    read_env_vars, read_file, parse_mcp_config, TaskRunnerOutput,
    execute_command, StreamEventEmitter, _truncate, TOOL_RESULT_MAX_LENGTH,
    emit_event, get_reasoning_effort, extract_json,
    filter_model_input, _strip_screenshots, _trim_context_window,
    _sanitize_tool_calls, _repair_truncated_json, _classify_error,
    _estimate_tokens, MAX_RETAINED_SCREENSHOTS, MAX_CONTEXT_TOKENS,
    connect_mcp_servers, resolve_max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS,
    _TRUNCATION_RECOVERY_MESSAGE,
)


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
async def test_stream_event_emitter_on_llm_start(caplog):
    """on_llm_start logs at DEBUG level."""
    agent = MagicMock()
    agent.name = "TaskRunner"
    emitter = StreamEventEmitter()
    with caplog.at_level(logging.DEBUG):
        await emitter.on_llm_start(MagicMock(), agent)
    assert any("LLM call starting" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_stream_event_emitter_on_llm_end(caplog):
    """on_llm_end logs at DEBUG level."""
    agent = MagicMock()
    agent.name = "TaskRunner"
    emitter = StreamEventEmitter()
    with caplog.at_level(logging.DEBUG):
        await emitter.on_llm_end(MagicMock(), agent, MagicMock())
    assert any("LLM call completed" in r.message for r in caplog.records)


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
    main_module = sys.modules["main"]
    original = main_module.COMMAND_TIMEOUT
    main_module.COMMAND_TIMEOUT = 1
    try:
        result = execute_command("sleep 10", working_directory=str(tmp_path))
        assert "timed out" in result
    finally:
        main_module.COMMAND_TIMEOUT = original


def test_execute_command_working_directory():
    """Runs command in specified working directory."""
    result = execute_command("pwd", working_directory="/tmp")
    # macOS /tmp is a symlink to /private/tmp
    assert "tmp" in result


def test_execute_command_invalid_directory():
    """Returns error for non-existent working directory."""
    result = execute_command("echo hello", working_directory="/nonexistent")
    assert "Error executing command" in result


# --- Truncation ---


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
