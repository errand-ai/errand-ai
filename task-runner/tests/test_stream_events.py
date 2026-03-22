"""Tests for StreamEventEmitter turn tracking, timing, and event enrichment."""

import asyncio
import json
import logging
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from main import StreamEventEmitter, emit_event


# --- httpx logging suppression ---


def test_httpx_logger_level_is_warning():
    """httpx INFO logging is suppressed to eliminate HTTP request noise."""
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING


# --- StreamEventEmitter unit tests ---


@pytest.fixture
def emitter():
    return StreamEventEmitter()


@pytest.fixture
def captured_events(monkeypatch):
    """Capture emit_event calls."""
    events = []

    def mock_emit(event_type, data):
        events.append({"type": event_type, "data": data})

    monkeypatch.setattr("main.emit_event", mock_emit)
    return events


class TestOnLlmStart:
    def test_emits_llm_turn_start_event(self, emitter, captured_events):
        """on_llm_start emits llm_turn_start with turn_id and model."""
        with patch.dict(os.environ, {"OPENAI_MODEL": "claude-sonnet-4-5"}):
            asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt["type"] == "llm_turn_start"
        assert "turn_id" in evt["data"]
        assert len(evt["data"]["turn_id"]) == 8
        assert evt["data"]["model"] == "claude-sonnet-4-5"

    def test_sets_current_turn_id(self, emitter, captured_events):
        """on_llm_start stores turn_id on the emitter instance."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        assert emitter._current_turn_id is not None
        assert len(emitter._current_turn_id) == 8
        # turn_id in event matches the stored one
        assert captured_events[0]["data"]["turn_id"] == emitter._current_turn_id

    def test_generates_unique_turn_ids(self, emitter, captured_events):
        """Each on_llm_start call generates a new turn_id."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        first_id = emitter._current_turn_id

        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        second_id = emitter._current_turn_id

        assert first_id != second_id

    def test_prefers_openai_model_env_var(self, emitter, captured_events):
        """Model name prefers OPENAI_MODEL over MODEL, defaults to 'unknown'."""
        # OPENAI_MODEL takes precedence
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4o", "MODEL": "fallback"}, clear=False):
            asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        assert captured_events[0]["data"]["model"] == "gpt-4o"

    def test_falls_back_to_model_env_var(self, emitter, captured_events):
        """Falls back to MODEL env var when OPENAI_MODEL is not set."""
        with patch.dict(os.environ, {"MODEL": "my-model"}, clear=False):
            os.environ.pop("OPENAI_MODEL", None)
            asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        assert captured_events[0]["data"]["model"] == "my-model"

    def test_defaults_to_unknown(self, emitter, captured_events):
        """Defaults to 'unknown' when neither env var is set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_MODEL", None)
            os.environ.pop("MODEL", None)
            asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        assert captured_events[0]["data"]["model"] == "unknown"


class TestOnToolStart:
    def test_records_start_time(self, emitter):
        """on_tool_start records monotonic time for the tool."""
        tool = MagicMock()
        tool.name = "web_search"

        before = time.monotonic()
        asyncio.run(emitter.on_tool_start(None, MagicMock(), tool))
        after = time.monotonic()

        assert "web_search" in emitter._tool_start_times
        assert before <= emitter._tool_start_times["web_search"] <= after


class TestOnToolEnd:
    def test_emits_tool_result_with_duration_and_turn_id(self, emitter, captured_events):
        """on_tool_end includes duration_ms and turn_id in tool_result."""
        emitter._current_turn_id = "abc12345"
        emitter._tool_start_times["web_search"] = time.monotonic() - 1.5  # 1.5s ago

        tool = MagicMock()
        tool.name = "web_search"

        asyncio.run(emitter.on_tool_end(None, MagicMock(), tool, "result text"))

        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt["type"] == "tool_result"
        assert evt["data"]["tool"] == "web_search"
        assert evt["data"]["turn_id"] == "abc12345"
        assert "duration_ms" in evt["data"]
        # Should be approximately 1500ms (allow some tolerance)
        assert 1400 <= evt["data"]["duration_ms"] <= 2000

    def test_omits_duration_when_no_start_time(self, emitter, captured_events):
        """duration_ms is omitted if on_tool_start wasn't called."""
        tool = MagicMock()
        tool.name = "unknown_tool"

        asyncio.run(emitter.on_tool_end(None, MagicMock(), tool, "result"))

        evt = captured_events[0]
        assert "duration_ms" not in evt["data"]

    def test_omits_turn_id_when_none(self, emitter, captured_events):
        """turn_id is omitted if no LLM turn has started."""
        assert emitter._current_turn_id is None
        tool = MagicMock()
        tool.name = "test_tool"

        asyncio.run(emitter.on_tool_end(None, MagicMock(), tool, "result"))

        evt = captured_events[0]
        assert "turn_id" not in evt["data"]

    def test_removes_start_time_after_use(self, emitter, captured_events):
        """Start time entry is cleaned up after on_tool_end."""
        emitter._tool_start_times["web_search"] = time.monotonic()
        tool = MagicMock()
        tool.name = "web_search"

        asyncio.run(emitter.on_tool_end(None, MagicMock(), tool, "result"))

        assert "web_search" not in emitter._tool_start_times


# --- mcp_connected event (tested via emit_event directly) ---


def test_mcp_connected_event_format(capsys):
    """mcp_connected event has correct server names and count."""
    server_names = ["errand", "playwright", "hindsight", "litellm_github"]
    emit_event("mcp_connected", {"servers": server_names, "count": len(server_names)})

    captured = capsys.readouterr()
    evt = json.loads(captured.err.strip())
    assert evt["type"] == "mcp_connected"
    assert evt["data"]["servers"] == server_names
    assert evt["data"]["count"] == 4
