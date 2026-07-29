"""Tests for LLM-summarized context compaction in the task runner."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from main import (
    COMPACTION_SUMMARY_PREFIX,
    FIRST_COMPACTION_PROMPT,
    KEEP_RECENT_TOKENS,
    MERGE_COMPACTION_PROMPT,
    _compaction_backoff,
    _compaction_summary,
    _estimate_tokens,
    _compact_context,
    _reset_compaction_summary,
    _extract_file_operations,
    _format_file_lists,
    _is_compaction_summary,
    _reset_compaction_backoff,
    _serialize_messages_for_summary,
    _snap_split_forward,
    _trim_context_window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_compaction_backoff():
    """Compaction backoff and the held summary are module-level state.

    Both leak between tests. A test that provokes a failure would otherwise
    suppress compaction in the next one, which then sees no LLM call and no log
    output; a test that leaves a held summary would send the next one down the
    merge path — or short-circuit it entirely, with no LLM call to inspect.

    Both dicts are imported by name rather than through the module. That is only
    safe because they are mutated in place and never reassigned — a rebind in
    main.py would leave these references stale.
    """
    _reset_compaction_backoff()
    _reset_compaction_summary()
    yield
    _reset_compaction_backoff()
    _reset_compaction_summary()


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
    first = result[1]
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
    messages = [summary_msg] + [_make_assistant_msg(filler) for _ in range(8)]

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


def test_extract_file_operations_file_tools():
    """File tools (read_file, write_file, edit_file) are tracked."""
    msgs = [
        _make_tool_call("read_file", {"path": "/workspace/config.yaml"}),
        _make_tool_call("write_file", {"path": "/workspace/output.txt", "content": "hello"}),
        _make_tool_call("edit_file", {"path": "/workspace/main.py", "old_text": "foo", "new_text": "bar"}),
        _make_tool_call("read_file", {"path": "/workspace/utils.py", "offset": 10, "limit": 20}),
    ]
    read_files, modified_files = _extract_file_operations(msgs)
    assert "/workspace/config.yaml" in read_files
    assert "/workspace/utils.py" in read_files
    assert "/workspace/output.txt" in modified_files
    assert "/workspace/main.py" in modified_files
    assert len(read_files) == 2
    assert len(modified_files) == 2


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
    messages = [summary_msg, new_tool_call] + [_make_assistant_msg(filler) for _ in range(8)]

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


# ---------------------------------------------------------------------------
# Compaction request configuration: timeout and token budget
#
# 30s could never cover 2048 tokens of generation on a local or free-tier
# model (25-50s at 40-80 tok/s before any prefill), which is why every
# compaction against such a model timed out.
# ---------------------------------------------------------------------------

def _capture_client(summary_text: str = "## Goal\nX\n"):
    """Return (mock_OpenAI_factory, captured) recording constructor + create kwargs."""
    captured: dict = {}

    def fake_create(**kwargs):
        captured["create_kwargs"] = kwargs
        choice = MagicMock()
        choice.message.content = summary_text
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    client = MagicMock()
    client.chat.completions.create.side_effect = fake_create

    def factory(**kwargs):
        captured["client_kwargs"] = kwargs
        return client

    return factory, captured


_BASE_ENV = {
    "OPENAI_MODEL": "gpt-4",
    "OPENAI_BASE_URL": "http://localhost",
    "OPENAI_API_KEY": "test",
}


def test_compaction_timeout_default_is_generous():
    """Default must exceed the ~50s a local model needs to generate its budget."""
    factory, captured = _capture_client()
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _compact_context(_big_messages())

    assert captured["client_kwargs"]["timeout"] >= 120.0


def test_compaction_timeout_from_env():
    factory, captured = _capture_client()
    env = {**_BASE_ENV, "COMPACTION_TIMEOUT_SECONDS": "240"}
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, env, clear=True):
        _compact_context(_big_messages())

    assert captured["client_kwargs"]["timeout"] == 240.0


def test_compaction_timeout_invalid_falls_back_to_default():
    factory, captured = _capture_client()
    env = {**_BASE_ENV, "COMPACTION_TIMEOUT_SECONDS": "not-a-number"}
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, env, clear=True):
        _compact_context(_big_messages())

    assert captured["client_kwargs"]["timeout"] >= 120.0


def test_compaction_timeout_does_not_inherit_llm_request_timeout():
    """The streaming agent loop's timeout must not constrain this call."""
    factory, captured = _capture_client()
    env = {**_BASE_ENV, "LLM_REQUEST_TIMEOUT": "30"}
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, env, clear=True):
        _compact_context(_big_messages())

    assert captured["client_kwargs"]["timeout"] >= 120.0


def test_compaction_max_tokens_default_above_2048():
    factory, captured = _capture_client()
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _compact_context(_big_messages())

    assert captured["create_kwargs"]["max_tokens"] > 2048


def test_compaction_max_tokens_from_env():
    factory, captured = _capture_client()
    env = {**_BASE_ENV, "COMPACTION_MAX_TOKENS": "8192"}
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, env, clear=True):
        _compact_context(_big_messages())

    assert captured["create_kwargs"]["max_tokens"] == 8192


def test_compaction_max_tokens_invalid_falls_back_to_default():
    factory, captured = _capture_client()
    env = {**_BASE_ENV, "COMPACTION_MAX_TOKENS": "0"}
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, env, clear=True):
        _compact_context(_big_messages())

    assert captured["create_kwargs"]["max_tokens"] > 2048


# ---------------------------------------------------------------------------
# Empty-summary diagnostics
#
# 13 of 19 production failures were empty summaries. The call SUCCEEDS and
# returns no content, so the operator cannot tell a refusal from a budget
# consumed by reasoning tokens. Logged at WARNING because production runs the
# task runner above INFO.
# ---------------------------------------------------------------------------

def _empty_response_client(finish_reason: str = "length", reasoning: str | None = None):
    choice = MagicMock()
    choice.message.content = ""
    choice.finish_reason = finish_reason
    if reasoning is None:
        # Attribute must be genuinely absent, not a truthy MagicMock.
        del choice.message.reasoning_content
    else:
        choice.message.reasoning_content = reasoning
    resp = MagicMock()
    resp.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = resp
    return client


def test_empty_summary_logs_finish_reason_and_reasoning(caplog):
    """Budget exhausted by thinking: the signature we could not previously see."""
    client = _empty_response_client(finish_reason="length", reasoning="thinking " * 500)
    with patch("main.OpenAI", return_value=client), \
         patch.dict(os.environ, _BASE_ENV, clear=True), \
         caplog.at_level("WARNING"):
        _compact_context(_big_messages())

    text = caplog.text
    assert "length" in text, "finish_reason must be reported"
    assert "reasoning" in text.lower(), "presence of a reasoning field must be reported"


def test_empty_summary_logs_content_length_when_no_reasoning(caplog):
    client = _empty_response_client(finish_reason="stop", reasoning=None)
    with patch("main.OpenAI", return_value=client), \
         patch.dict(os.environ, _BASE_ENV, clear=True), \
         caplog.at_level("WARNING"):
        _compact_context(_big_messages())

    assert "stop" in caplog.text


def test_empty_summary_still_falls_back_to_trim(caplog):
    messages = _big_messages()
    client = _empty_response_client()
    with patch("main.OpenAI", return_value=client), \
         patch.dict(os.environ, _BASE_ENV, clear=True), \
         caplog.at_level("WARNING"):
        result = _compact_context(messages)

    assert len(result) < len(messages)


# ---------------------------------------------------------------------------
# Consecutive-failure backoff
#
# _compact_context runs from filter_model_input, which the SDK calls before
# EVERY model request. Without suppression a broken configuration costs one
# failed LLM call per turn for the life of the task — the production spiral.
# ---------------------------------------------------------------------------

def _failing_client(exc: Exception | None = None):
    client = MagicMock()
    client.chat.completions.create.side_effect = exc or RuntimeError("boom")
    return client


def _call_count(client) -> int:
    return client.chat.completions.create.call_count


def test_backoff_suppresses_the_turn_after_a_failure():
    _reset_compaction_backoff()
    client = _failing_client()
    with patch("main.OpenAI", return_value=client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _compact_context(_big_messages())   # attempt 1: fails
        assert _call_count(client) == 1
        _compact_context(_big_messages())   # suppressed
        assert _call_count(client) == 1, "suppressed turn must not call the LLM"


def test_backoff_window_widens_with_consecutive_failures():
    _reset_compaction_backoff()
    client = _failing_client()
    with patch("main.OpenAI", return_value=client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        # Drive 40 turns; a widening window must yield far fewer calls than turns.
        for _ in range(40):
            _compact_context(_big_messages())

    assert _call_count(client) < 10, (
        f"expected bounded attempts under backoff, got {_call_count(client)} in 40 turns"
    )


def test_backoff_resets_after_a_success():
    _reset_compaction_backoff()
    summary = "## Goal\nX\n## Progress\n### Done\n\n### In Progress\n\n### Blocked\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"
    failing = _failing_client()
    ok_factory, _ = _capture_client(summary)

    with patch("main.OpenAI", return_value=failing), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _compact_context(_big_messages())          # fail -> backoff armed

    with patch("main.OpenAI", side_effect=ok_factory), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _reset_compaction_backoff()           # simulate the reset path
        result = _compact_context(_big_messages())

    assert result[1]["content"].startswith(COMPACTION_SUMMARY_PREFIX)


def test_successful_compaction_clears_backoff_state():
    """A success must re-arm compaction for the next over-limit turn."""
    _reset_compaction_backoff()
    summary = "## Goal\nX\n## Progress\n### Done\n\n### In Progress\n\n### Blocked\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"
    factory, _ = _capture_client(summary)
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _compact_context(_big_messages())
        _compact_context(_big_messages())

    assert _compaction_backoff["consecutive_failures"] == 0
    assert _compaction_backoff["suppress_until_turn"] == 0


def test_suppressed_turn_still_trims():
    """Suppression must not let the context grow unbounded."""
    _reset_compaction_backoff()
    messages = _big_messages()
    client = _failing_client()
    with patch("main.OpenAI", return_value=client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _compact_context(messages)              # fail
        result = _compact_context(messages)     # suppressed

    assert len(result) < len(messages), "suppressed turns must still trim"


def test_backoff_entry_is_logged_at_warning(caplog):
    _reset_compaction_backoff()
    client = _failing_client()
    with patch("main.OpenAI", return_value=client), \
         patch.dict(os.environ, _BASE_ENV, clear=True), \
         caplog.at_level("WARNING"):
        _compact_context(_big_messages())
        _compact_context(_big_messages())

    assert "compaction" in caplog.text.lower()
    assert "suppress" in caplog.text.lower(), "entering the backoff window must be visible"


# ---------------------------------------------------------------------------
# Log-level visibility
#
# Production runs the task runner at WARNING. Compaction's failure paths logged
# at WARNING and were visible; its trigger and success logged at INFO and were
# not. The result: 19 failures were observable in Loki over 14 days while a
# success would have been silent — exactly backwards for confirming a fix.
# ---------------------------------------------------------------------------

def test_compaction_success_is_visible_at_warning(caplog):
    summary = "## Goal\nX\n## Progress\n### Done\n\n### In Progress\n\n### Blocked\n\n## Key Decisions\n\n## Next Steps\n\n## Critical Context\n"
    factory, _ = _capture_client(summary)
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, _BASE_ENV, clear=True), \
         caplog.at_level("WARNING"):
        result = _compact_context(_big_messages())

    assert result[1]["content"].startswith(COMPACTION_SUMMARY_PREFIX)
    assert "compaction complete" in caplog.text.lower(), (
        "a successful compaction must be observable at the production log level"
    )


def test_compaction_trigger_is_visible_at_warning(caplog):
    summary = "## Goal\nX\n"
    factory, _ = _capture_client(summary)
    with patch("main.OpenAI", side_effect=factory), \
         patch.dict(os.environ, _BASE_ENV, clear=True), \
         caplog.at_level("WARNING"):
        _compact_context(_big_messages())

    assert "compaction triggered" in caplog.text.lower()


def test_trim_is_visible_at_warning(caplog):
    """Trimming discards history irrecoverably — it should not be silent."""
    messages = [{"role": "user", "content": "initial"}]
    for _ in range(40):
        messages.append({"role": "assistant", "content": "x" * 5000})

    with patch("main.MAX_CONTEXT_TOKENS", 20000), caplog.at_level("WARNING"):
        _trim_context_window(messages)

    assert "trimmed" in caplog.text.lower()


def test_compaction_skipped_is_visible_at_warning(caplog):
    """A missing model or key is a misconfiguration, not routine information."""
    env = {k: v for k, v in _BASE_ENV.items() if k != "OPENAI_API_KEY"}
    with patch.dict(os.environ, env, clear=True), caplog.at_level("WARNING"):
        _compact_context(_big_messages())

    assert "compaction skipped" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Split-point safety: a compaction boundary must never separate a
# function_call from its function_call_output (reduce-compaction-recomputation
# tasks 2.1-2.4)
# ---------------------------------------------------------------------------

def test_split_moved_forward_off_a_tool_pair_boundary():
    """A split landing between a call and its output moves past the output.

    Forward, not backward: cutting deeper is merely lossy, whereas retaining a
    larger tail can leave the conversation still over the limit after a
    compaction that reported success.
    """
    messages = [
        _make_user_msg("initial"),
        _make_assistant_msg("thinking"),
        _make_tool_call("read_file", {"path": "a.txt"}),
        _make_tool_result("file contents"),
        _make_assistant_msg("done"),
    ]
    # Boundary sits between the call (index 2) and its output (index 3).
    assert _snap_split_forward(messages, 3) == 4


def test_split_moves_past_several_parallel_tool_outputs():
    """Parallel tool calls produce consecutive outputs; all must move together."""
    messages = [
        _make_user_msg("initial"),
        _make_tool_call("a", {}),
        _make_tool_call("b", {}),
        _make_tool_result("out a"),
        _make_tool_result("out b"),
        _make_assistant_msg("done"),
    ]
    assert _snap_split_forward(messages, 3) == 5


def test_split_at_a_safe_boundary_is_left_alone():
    """A boundary that orphans nothing must not be moved."""
    messages = [
        _make_user_msg("initial"),
        _make_tool_call("a", {}),
        _make_tool_result("out a"),
        _make_assistant_msg("done"),
        _make_user_msg("next"),
    ]
    assert _snap_split_forward(messages, 3) == 3


def test_split_forward_stops_before_consuming_every_message():
    """Degenerate case: snapping must still leave at least one message kept.

    Otherwise the clamp that guarantees "at least one kept" would hand back a
    boundary the snap had just rejected.
    """
    messages = [
        _make_user_msg("initial"),
        _make_tool_call("a", {}),
        _make_tool_result("out a"),
        _make_tool_result("out b"),
    ]
    assert _snap_split_forward(messages, 2) == len(messages) - 1


def _messages_splitting_on_a_tool_pair() -> list:
    """Build a conversation whose natural split falls between a call and its output.

    The sizes matter and are not arbitrary. Walking backwards from the end:
    the tail (~16 tokens) and the output (~19,016 tokens) both fit inside
    KEEP_RECENT_TOKENS, but the call's large arguments (~1,340 tokens) push the
    running total past 20,000 — so the boundary lands between the call and the
    output it belongs to. A small call would simply fit, and the bug would not
    reproduce.
    """
    messages = [_make_user_msg("initial task")]
    for _ in range(9):
        messages.append(_make_assistant_msg("x" * 60_000))
    messages.append(_make_tool_call("write_file", {"path": "big.txt", "content": "z" * 4_000}))
    messages.append(_make_tool_result("y" * 57_000))
    messages.append(_make_assistant_msg("short tail"))
    return messages


def test_retained_portion_never_begins_with_an_orphaned_output():
    """End-to-end: the message after the summary is never a stray tool result."""
    messages = _messages_splitting_on_a_tool_pair()

    mock_client = _mock_openai_response("## Goal\nsummary\n")
    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        result = _compact_context(messages)

    assert result[1]["content"].startswith(COMPACTION_SUMMARY_PREFIX)
    assert result[2].get("type") != "function_call_output", (
        "retained portion starts with a tool result whose call was summarised away"
    )


def test_the_summarised_portion_keeps_the_pair_together():
    """The output must follow its call into the summary, not vanish between them."""
    messages = _messages_splitting_on_a_tool_pair()

    mock_client = _mock_openai_response("## Goal\nsummary\n")
    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        _compact_context(messages)

    sent = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "[TOOL CALL: write_file]" in sent
    assert "[TOOL RESULT]" in sent


def test_compaction_proceeds_when_snapping_retains_less_than_keep_recent():
    """Moving past a large pair retains little; compaction still runs.

    Snapping forward here leaves only the short tail — far below
    KEEP_RECENT_TOKENS. Refusing to compact would leave the conversation over
    the limit, which is worse than retaining less than the constant suggests.
    """
    messages = _messages_splitting_on_a_tool_pair()

    mock_client = _mock_openai_response("## Goal\nsummary\n")
    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        result = _compact_context(messages)

    # Preserved prompt, then the summary, then only the short tail.
    assert result == [messages[0], result[1], messages[-1]]
    assert _estimate_tokens(result[2:]) < KEEP_RECENT_TOKENS


# ---------------------------------------------------------------------------
# Held summary state: repeated compactions merge rather than re-summarising the
# whole prefix (reduce-compaction-recomputation tasks 3.1-3.5, 4.1)
# ---------------------------------------------------------------------------

def _summary_message_text(inner: str) -> str:
    return COMPACTION_SUMMARY_PREFIX + "\n\n<summary>\n" + inner + "\n</summary>"


def _prompt_sent(mock_client) -> str:
    return mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]


def _compact_with(messages: list, summary: str = "## Goal\nsummary\n"):
    mock_client = _mock_openai_response(summary)
    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        result = _compact_context(messages)
    return result, mock_client


def test_no_held_summary_uses_the_full_summarisation_prompt():
    _reset_compaction_summary()
    _, client = _compact_with(_big_messages())
    assert "Existing summary:" not in _prompt_sent(client)


def test_second_compaction_merges_when_the_held_summary_matches():
    """The whole point: a repeat compaction must not re-summarise the prefix.

    The SDK rebuilds history from its own items every turn, so the second
    compaction sees the original messages again, not the compacted list. The
    held record is what makes the merge path reachable at all.
    """
    _reset_compaction_summary()
    first = _big_messages(10)
    _compact_with(first)

    # Next turn: the SDK hands back the original conversation, plus new turns.
    second = first + [_make_assistant_msg("z" * 60_000), _make_assistant_msg("new work")]
    _, client = _compact_with(second)

    assert "Existing summary:" in _prompt_sent(client)


def test_merge_sends_only_the_messages_beyond_the_covered_prefix():
    _reset_compaction_summary()
    first = _big_messages(10)
    _compact_with(first)

    # The marker sits at the head of a filler that lands beyond the covered
    # prefix but ahead of the retained tail — i.e. in the newly-summarised
    # range. Serialisation truncates to ~2k chars, so it must lead the content.
    second = first + [
        _make_assistant_msg("MARKER-NEW " + "z" * 60_000),
        _make_assistant_msg("retained tail"),
    ]
    _, client = _compact_with(second)

    sent = _prompt_sent(client)
    new_conversation = sent.split("New conversation content to merge:", 1)[1]
    assert "MARKER-NEW" in new_conversation
    assert "initial task" not in new_conversation, (
        "the covered prefix was re-sent — the merge saved nothing"
    )


def test_content_mismatch_falls_back_to_a_full_summarisation():
    """A stale summary spliced onto unrelated messages is the failure to avoid.

    It raises no error and silently misrepresents history, so any doubt must
    take the full path.
    """
    _reset_compaction_summary()
    first = _big_messages(10)
    _compact_with(first)

    # Same shape and length, different content — a count check would pass here.
    tampered = list(first)
    tampered[3] = _make_assistant_msg("q" * 60_000)
    second = tampered + [_make_assistant_msg("z" * 60_000), _make_assistant_msg("new")]
    _, client = _compact_with(second)

    assert "Existing summary:" not in _prompt_sent(client)


def test_held_summary_is_cleared_on_agent_retry():
    """Reset on the same boundary as the backoff, so an attempt cannot inherit
    a summary describing the previous attempt's history."""
    _reset_compaction_summary()
    first = _big_messages(10)
    _compact_with(first)
    assert _compaction_summary["summary"]

    _reset_compaction_summary()

    second = first + [_make_assistant_msg("z" * 60_000), _make_assistant_msg("new")]
    _, client = _compact_with(second)
    assert "Existing summary:" not in _prompt_sent(client)


def test_a_failed_compaction_does_not_leave_a_held_summary():
    """An empty summary is a failure; recording it would merge onto nothing."""
    _reset_compaction_summary()
    _, _ = _compact_with(_big_messages(), summary="")
    assert not _compaction_summary["summary"]


def test_merge_and_full_paths_are_distinguishable_at_warning(caplog):
    """Whether chaining engaged must be readable, not inferred from timings."""
    _reset_compaction_summary()
    first = _big_messages(10)
    with caplog.at_level("WARNING"):
        _compact_with(first)
    assert "full summarisation" in caplog.text.lower()

    caplog.clear()
    second = first + [_make_assistant_msg("z" * 60_000), _make_assistant_msg("new")]
    with caplog.at_level("WARNING"):
        _compact_with(second)
    assert "merge" in caplog.text.lower()


def test_the_digest_is_what_rejects_a_mismatch():
    """Mutation guard: neutralise the digest and the stale merge happens.

    Without this, `test_content_mismatch_falls_back_to_a_full_summarisation`
    could pass for the wrong reason — a count check, or the merge path simply
    not engaging — and the protection would be decorative. Here the digest is
    forced to agree, and the tampered history is merged onto after all. That it
    changes the outcome is the evidence that the real check does the work.
    """
    _reset_compaction_summary()
    first = _big_messages(10)
    tampered = list(first)
    tampered[3] = _make_assistant_msg("q" * 60_000)
    second = tampered + [_make_assistant_msg("z" * 60_000), _make_assistant_msg("new")]

    # The patch must span both compactions: storing a real digest and comparing
    # a constant one would mismatch for the wrong reason and prove nothing.
    with patch("main._digest_messages", lambda messages: "constant"):
        _compact_with(first)
        _, client = _compact_with(second)

    assert "Existing summary:" in _prompt_sent(client), (
        "with the digest neutralised the merge should proceed; if it does not, "
        "the mismatch test is passing for some other reason"
    )


def test_file_lists_carry_forward_across_a_held_state_merge():
    """`File operation tracking across compactions` must survive the new path.

    The held summary is stored with its file blocks attached, so the next merge
    can read them back out — the same contract the marker-based path had.
    """
    _reset_compaction_summary()
    # The tool call must sit inside the summarised portion, not the retained
    # tail — a trailing call is kept verbatim and never reaches the file lists.
    first = [_make_user_msg("initial task")]
    for _ in range(7):
        first.append(_make_assistant_msg("x" * 60_000))
    first.append(_make_tool_call("execute_command", {"command": "cat /workspace/early.py"}))
    first.append(_make_assistant_msg("x" * 60_000))
    _compact_with(first)
    assert "/workspace/early.py" in _compaction_summary["summary"]

    second = list(first) + [
        _make_assistant_msg("z" * 60_000),
        _make_tool_call("execute_command", {"command": "cat /workspace/later.py"}),
        _make_assistant_msg("z" * 60_000),
    ]
    result, _ = _compact_with(second)

    summary = result[1]["content"]
    assert "/workspace/early.py" in summary, "file list from the previous summary was dropped"
    assert "/workspace/later.py" in summary, "file list from the new messages was dropped"


def test_nothing_new_reuses_the_held_summary_without_an_llm_call():
    """Merging an empty conversation would spend a call to reproduce what we hold."""
    _reset_compaction_summary()
    messages = _big_messages(10)
    _compact_with(messages)
    held = _compaction_summary["summary"]

    mock_client = _mock_openai_response("should not be called")
    with patch("main.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, _BASE_ENV, clear=True):
        result = _compact_context(messages)

    mock_client.chat.completions.create.assert_not_called()
    assert held in result[1]["content"]


# ---------------------------------------------------------------------------
# The initial task prompt survives compaction
# (pin-constraints-across-compaction tasks 3.x, 4.x, 5.x)
# ---------------------------------------------------------------------------

_PROMPT_TEXT = "Do not open pull requests, push commits, or modify the repository."


def _messages_with_real_prompt(n: int = 10, first: str = _PROMPT_TEXT) -> list:
    msgs = [_make_user_msg(first)]
    for _ in range(n - 1):
        msgs.append(_make_assistant_msg("x" * 60_000))
    return msgs


def test_first_message_is_present_and_byte_identical_after_compaction():
    """The task's own instructions must not depend on what the summariser kept."""
    _reset_compaction_summary()
    messages = _messages_with_real_prompt()
    original = dict(messages[0])

    result, _ = _compact_with(messages)

    assert result[0] == original


def test_the_summary_follows_the_preserved_prompt():
    _reset_compaction_summary()
    result, _ = _compact_with(_messages_with_real_prompt())

    assert result[1]["content"].startswith(COMPACTION_SUMMARY_PREFIX)


def test_first_message_is_not_sent_for_summarisation():
    """Preserved verbatim means excluded from the summarised portion, not merely
    duplicated ahead of it — otherwise it is paraphrased and pinned at once."""
    _reset_compaction_summary()
    _, client = _compact_with(_messages_with_real_prompt())

    assert _PROMPT_TEXT not in _prompt_sent(client)


def test_a_large_first_message_is_preserved_in_full():
    """Truncating a constraint mid-sentence is the exact failure this prevents."""
    _reset_compaction_summary()
    big_prompt = _PROMPT_TEXT + " " + "detail " * 8_000
    messages = _messages_with_real_prompt(first=big_prompt)

    result, _ = _compact_with(messages)

    assert result[0]["content"] == big_prompt


def test_trimming_and_compaction_agree_about_the_first_message():
    """Both context-management paths must treat the prompt as load-bearing."""
    _reset_compaction_summary()
    messages = _messages_with_real_prompt()

    trimmed = _trim_context_window(messages)
    compacted, _ = _compact_with(messages)

    assert trimmed[0] == messages[0]
    assert compacted[0] == messages[0]


def test_preservation_is_logged_at_warning(caplog):
    """Production runs above INFO; a task that lost its prompt must be detectable."""
    _reset_compaction_summary()
    with caplog.at_level("WARNING"):
        _compact_with(_messages_with_real_prompt())

    assert "preserv" in caplog.text.lower()


def test_both_compaction_prompts_ask_for_constraints():
    """Covers constraints arriving after the first message — from a skill, a tool
    result, or a follow-up — which preservation cannot protect."""
    for prompt in (FIRST_COMPACTION_PROMPT, MERGE_COMPACTION_PROMPT):
        lowered = prompt.lower()
        assert "constraint" in lowered
        assert "original wording" in lowered


def test_a_conversation_without_constraints_still_summarises_normally():
    _reset_compaction_summary()
    result, _ = _compact_with(_big_messages())

    assert result[1]["content"].startswith(COMPACTION_SUMMARY_PREFIX)
    assert "## Goal" in result[1]["content"]


def test_the_clamp_reserves_room_for_the_preserved_prompt():
    """With messages[0] reserved the lower bound is 2, not 1.

    At 1 the summarised portion would be `messages[1:1]` — empty — and
    compaction would spend an LLM call summarising nothing.

    The fixture must make the token walk itself return `split_idx == 1`, so the
    clamp is what raises it to 2. That needs a LARGE `messages[0]` with the
    remaining messages small enough to fit inside `KEEP_RECENT_TOKENS`: walking
    backwards, the tail messages accumulate cheaply and `messages[0]` is the one
    that busts the budget, giving `split_idx = 0 + 1`. An earlier version of
    this test put the large message in the middle, which made the walk return 2
    on its own — so `max(1, ...)` and `max(2, ...)` agreed and the test pinned
    nothing.
    """
    _reset_compaction_summary()
    messages = [
        _make_user_msg(_PROMPT_TEXT + " " + "pad " * 115_000),
        _make_assistant_msg("MARKER-MIDDLE small message"),
        _make_assistant_msg("tail"),
    ]

    _, client = _compact_with(messages)

    # split_idx == 2 means messages[1] is summarised. Under the old lower bound
    # of 1 there would be nothing to summarise at all.
    sent = _prompt_sent(client)
    assert "MARKER-MIDDLE" in sent, (
        "summarised portion was empty — the clamp did not reserve room for the "
        "preserved prompt"
    )
    assert _PROMPT_TEXT not in sent


def test_a_summary_at_position_zero_is_not_treated_as_the_prompt():
    """A summary there means the real prompt was already summarised away.

    Preserving it verbatim would pin a summary permanently and stop it ever
    being merged again — worse than not preserving at all.
    """
    _reset_compaction_summary()
    prior = _summary_message_text("## Goal\nOld goal\n")
    messages = [{"role": "user", "content": prior}]
    for _ in range(8):
        messages.append(_make_assistant_msg("y" * 62_000))

    result, client = _compact_with(messages)

    assert result[0]["content"].startswith(COMPACTION_SUMMARY_PREFIX)
    assert "Old goal" in _prompt_sent(client), "the stale summary was pinned instead of merged"
