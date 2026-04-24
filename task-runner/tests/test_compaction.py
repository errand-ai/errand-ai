"""Tests for LLM-summarized context compaction in the task runner."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from main import (
    COMPACTION_SUMMARY_PREFIX,
    MAX_CONTEXT_TOKENS,
    _compact_context,
    _extract_file_operations,
    _format_file_lists,
    _is_compaction_summary,
    _serialize_messages_for_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_msg(content: str) -> dict:
    return {"role": "user", "content": content}


def _make_assistant_msg(content: str) -> dict:
    return {"role": "assistant", "content": content}


def _make_tool_call(name: str, args: dict) -> dict:
    return {"type": "function_call", "name": name, "arguments": json.dumps(args)}


def _make_tool_result(output: str) -> dict:
    return {"type": "function_call_output", "output": output}


def _big_messages(n: int = 10, size: int = 60_000) -> list:
    """Build a list of n large messages that together exceed MAX_CONTEXT_TOKENS."""
    chunk = "x" * size
    msgs = [_make_user_msg("initial task")]
    for i in range(n - 1):
        msgs.append(_make_assistant_msg(chunk))
    return msgs


def _mock_openai_response(summary_text: str):
    """Return a mock sync OpenAI client whose create() returns summary_text."""
    choice = MagicMock()
    choice.message.content = summary_text
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


# ---------------------------------------------------------------------------
# 5.1 Compaction triggers when tokens exceed budget and produces structured summary
# ---------------------------------------------------------------------------

def test_compaction_triggers_and_produces_summary():
    messages = _big_messages()
    summary_text = "## Goal\nTest task\n## Progress\n### Done\nNothing\n### In Progress\nTesting\n### Blocked\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"

    mock_client = _mock_openai_response(summary_text)
    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4", "OPENAI_BASE_URL": "http://localhost", "OPENAI_API_KEY": "test"}):
        result = _compact_context(messages)

    assert len(result) < len(messages)
    first = result[0]
    assert first["role"] == "user"
    assert first["content"].startswith(COMPACTION_SUMMARY_PREFIX)
    assert "<summary>" in first["content"]
    assert summary_text.strip() in first["content"]


# ---------------------------------------------------------------------------
# 5.2 Compaction does not trigger when tokens are under budget
# ---------------------------------------------------------------------------

def test_compaction_no_trigger_under_budget():
    messages = [_make_user_msg("hello"), _make_assistant_msg("hi")]
    result = _compact_context(messages)
    assert result is messages  # unchanged — same object


# ---------------------------------------------------------------------------
# 5.3 Subsequent compaction uses merge prompt and preserves prior summary
# ---------------------------------------------------------------------------

def test_subsequent_compaction_uses_merge_prompt():
    prior_summary = (
        COMPACTION_SUMMARY_PREFIX
        + "\n\n<summary>\n## Goal\nOld goal\n## Progress\n### Done\nStep 1\n"
        "### In Progress\nStep 2\n### Blocked\n\n## Key Decisions\nDecision A\n"
        "## Next Steps\nStep 3\n## Critical Context\nFoo\n</summary>"
    )
    summary_msg = {"role": "user", "content": prior_summary}

    # Build a large message list: existing summary + many new messages.
    # Each filler message is ~62000 chars → ~20667 tokens (> KEEP_RECENT_TOKENS=20000),
    # and 8 of them → ~165333 tokens > MAX_CONTEXT_TOKENS=150000, triggering compaction.
    filler = "y" * 62_000
    messages = [summary_msg] + [_make_assistant_msg(filler)] * 8

    merge_result_text = "## Goal\nOld goal\n## Progress\n### Done\nStep 1, Step 2\n### In Progress\nStep 3\n### Blocked\n\n## Key Decisions\nDecision A, Decision B\n## Next Steps\nStep 4\n## Critical Context\nFoo, Bar\n"

    mock_client = _mock_openai_response(merge_result_text)
    captured_calls = []

    def capture_create(**kwargs):
        captured_calls.append(kwargs)
        choice = MagicMock()
        choice.message.content = merge_result_text
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    mock_client.chat.completions.create.side_effect = capture_create

    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4", "OPENAI_BASE_URL": "http://localhost", "OPENAI_API_KEY": "test"}):
        result = _compact_context(messages)

    # Should have called the LLM exactly once
    assert len(captured_calls) == 1
    # The user prompt sent to the LLM should include the merge prompt text (existing summary)
    user_msg_content = captured_calls[0]["messages"][1]["content"]
    assert "Existing summary" in user_msg_content or "existing summary" in user_msg_content
    assert "Old goal" in user_msg_content

    # Result should be compacted
    assert result[0]["content"].startswith(COMPACTION_SUMMARY_PREFIX)
    assert merge_result_text.strip() in result[0]["content"]


# ---------------------------------------------------------------------------
# 5.4 File operation extraction from execute_command tool calls
# ---------------------------------------------------------------------------

def test_extract_file_operations_read_commands():
    msgs = [
        _make_tool_call("execute_command", {"command": "cat /workspace/main.py"}),
        _make_tool_call("execute_command", {"command": "head -n 20 /workspace/utils.py"}),
        _make_tool_call("execute_command", {"command": "grep -r 'def foo' /workspace/src/helpers.py"}),
        _make_tool_call("execute_command", {"command": "tail -n 5 /workspace/log.txt"}),
    ]
    read_files, modified_files = _extract_file_operations(msgs)
    assert "/workspace/main.py" in read_files
    assert "/workspace/utils.py" in read_files
    assert "/workspace/log.txt" in read_files
    assert not modified_files


def test_extract_file_operations_write_commands():
    msgs = [
        _make_tool_call("execute_command", {"command": "echo 'hello' > /workspace/out.txt"}),
        _make_tool_call("execute_command", {"command": "echo 'more' >> /workspace/out.txt"}),
        _make_tool_call("execute_command", {"command": "sed -i 's/foo/bar/' /workspace/main.py"}),
        _make_tool_call("execute_command", {"command": "tee /workspace/result.json"}),
        _make_tool_call("execute_command", {"command": "cp /workspace/a.py /workspace/b.py"}),
    ]
    read_files, modified_files = _extract_file_operations(msgs)
    assert "/workspace/out.txt" in modified_files
    assert "/workspace/main.py" in modified_files
    assert "/workspace/result.json" in modified_files
    assert "/workspace/b.py" in modified_files


def test_extract_file_operations_ignores_non_execute_command():
    msgs = [
        _make_tool_call("some_other_tool", {"command": "cat /secret.py"}),
        _make_tool_result("output text"),
        _make_user_msg("cat /not_a_tool_call.py"),
    ]
    read_files, modified_files = _extract_file_operations(msgs)
    assert not read_files
    assert not modified_files


# ---------------------------------------------------------------------------
# 5.5 File lists are carried forward across compactions
# ---------------------------------------------------------------------------

def test_file_lists_carried_forward():
    prior_summary = (
        COMPACTION_SUMMARY_PREFIX
        + "\n\n<summary>\n## Goal\nTest\n\n"
        "<read-files>\n/workspace/old_read.py\n</read-files>\n"
        "<modified-files>\n/workspace/old_modified.py\n</modified-files>\n"
        "</summary>"
    )
    summary_msg = {"role": "user", "content": prior_summary}
    new_tool_call = _make_tool_call("execute_command", {"command": "cat /workspace/new_read.py"})
    # Place tool_call early so it lands in the summarized portion (before recent window).
    # Each filler is ~62000 chars → ~20667 tokens > KEEP_RECENT_TOKENS, so only the
    # last filler is kept as recent context; everything before it (including new_tool_call)
    # is summarized.  8 fillers → ~165k tokens > MAX_CONTEXT_TOKENS, triggering compaction.
    filler = "z" * 62_000
    messages = [summary_msg, new_tool_call] + [_make_assistant_msg(filler)] * 8

    merge_text = "## Goal\nTest\n## Progress\n### Done\n\n### In Progress\n\n### Blocked\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"
    mock_client = _mock_openai_response(merge_text)

    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4", "OPENAI_BASE_URL": "http://localhost", "OPENAI_API_KEY": "test"}):
        result = _compact_context(messages)

    content = result[0]["content"]
    assert "/workspace/old_read.py" in content
    assert "/workspace/new_read.py" in content
    assert "/workspace/old_modified.py" in content


# ---------------------------------------------------------------------------
# 5.6 Message serialization truncates tool results to ~2k chars
# ---------------------------------------------------------------------------

def test_serialize_truncates_tool_results():
    long_output = "A" * 5000
    msgs = [_make_tool_result(long_output)]
    serialized = _serialize_messages_for_summary(msgs)
    # Truncated at 2000 chars + "... [truncated]"
    assert "... [truncated]" in serialized
    assert "A" * 5000 not in serialized


def test_serialize_preserves_short_tool_results():
    short_output = "short result"
    msgs = [_make_tool_result(short_output)]
    serialized = _serialize_messages_for_summary(msgs)
    assert short_output in serialized
    assert "... [truncated]" not in serialized


def test_serialize_includes_role_labels():
    msgs = [
        _make_user_msg("user content"),
        _make_assistant_msg("assistant content"),
        _make_tool_call("execute_command", {"command": "ls"}),
        _make_tool_result("file.txt"),
    ]
    serialized = _serialize_messages_for_summary(msgs)
    assert "[USER]" in serialized
    assert "[ASSISTANT]" in serialized
    assert "[TOOL CALL: execute_command]" in serialized
    assert "[TOOL RESULT]" in serialized
    assert "<conversation>" in serialized
    assert "</conversation>" in serialized


# ---------------------------------------------------------------------------
# 5.7 COMPACTION_MODEL env var is used when set, falls back to OPENAI_MODEL
# ---------------------------------------------------------------------------

def test_compaction_model_env_var_used_when_set():
    messages = _big_messages()
    summary_text = "## Goal\nX\n## Progress\n### Done\n\n### In Progress\n\n### Blocked\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"
    captured = {}

    def fake_create(**kwargs):
        captured["model"] = kwargs.get("model")
        choice = MagicMock()
        choice.message.content = summary_text
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {
             "OPENAI_MODEL": "gpt-4",
             "COMPACTION_MODEL": "gpt-4.1-mini",
             "OPENAI_BASE_URL": "http://localhost",
             "OPENAI_API_KEY": "test",
         }):
        _compact_context(messages)

    assert captured["model"] == "gpt-4.1-mini"


def test_compaction_model_falls_back_to_openai_model():
    messages = _big_messages()
    summary_text = "## Goal\nX\n## Progress\n### Done\n\n### In Progress\n\n### Blocked\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"
    captured = {}

    def fake_create(**kwargs):
        captured["model"] = kwargs.get("model")
        choice = MagicMock()
        choice.message.content = summary_text
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    env = {"OPENAI_MODEL": "gpt-4", "OPENAI_BASE_URL": "http://localhost", "OPENAI_API_KEY": "test"}
    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, env, clear=False):
        # Ensure COMPACTION_MODEL is absent
        os.environ.pop("COMPACTION_MODEL", None)
        _compact_context(messages)

    assert captured["model"] == "gpt-4"


# ---------------------------------------------------------------------------
# 5.8 Compaction with 2 or fewer messages returns unchanged
# ---------------------------------------------------------------------------

def test_compaction_unchanged_for_two_messages():
    messages = [_make_user_msg("hi"), _make_assistant_msg("hello")]
    result = _compact_context(messages)
    assert result is messages


def test_compaction_unchanged_for_one_message():
    messages = [_make_user_msg("single message")]
    result = _compact_context(messages)
    assert result is messages


def test_compaction_unchanged_for_empty():
    result = _compact_context([])
    assert result == []


# ---------------------------------------------------------------------------
# Additional: _is_compaction_summary
# ---------------------------------------------------------------------------

def test_is_compaction_summary_true():
    msg = {"role": "user", "content": COMPACTION_SUMMARY_PREFIX + "\n\n<summary>...</summary>"}
    assert _is_compaction_summary(msg) is True


def test_is_compaction_summary_false_for_regular_message():
    msg = {"role": "user", "content": "This is a regular user message"}
    assert _is_compaction_summary(msg) is False


def test_is_compaction_summary_false_for_non_dict():
    assert _is_compaction_summary("not a dict") is False  # type: ignore


# ---------------------------------------------------------------------------
# Additional: _format_file_lists merging
# ---------------------------------------------------------------------------

def test_format_file_lists_merge_with_existing():
    existing = "<read-files>\n/workspace/a.py\n</read-files>\n<modified-files>\n/workspace/b.py\n</modified-files>"
    result = _format_file_lists({"/workspace/c.py"}, {"/workspace/d.py"}, existing)
    assert "/workspace/a.py" in result
    assert "/workspace/c.py" in result
    assert "/workspace/b.py" in result
    assert "/workspace/d.py" in result


def test_format_file_lists_empty_when_no_files():
    result = _format_file_lists(set(), set(), "")
    assert result == ""
