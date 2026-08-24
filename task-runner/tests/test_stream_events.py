"""Tests for StreamEventEmitter turn tracking, timing, and event enrichment."""

import asyncio
import json
import logging
import os
import time
from types import SimpleNamespace
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


class TestOnLlmEnd:
    """on_llm_end reports the provider's own accounting for the turn."""

    @staticmethod
    def _response(input_tokens=None, output_tokens=None, cached_tokens=None, usage=True):
        """Build a stand-in ModelResponse. usage=False models a provider that
        returns no usage block at all."""
        response = SimpleNamespace()
        if not usage:
            response.usage = None
            return response
        response.usage = SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(input_tokens or 0) + (output_tokens or 0),
            input_tokens_details=(
                SimpleNamespace(cached_tokens=cached_tokens) if cached_tokens is not None else None
            ),
        )
        return response

    def test_emits_llm_turn_end(self, emitter, captured_events):
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        captured_events.clear()

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(38204, 512)))

        assert [e["type"] for e in captured_events] == ["llm_turn_end"]

    def test_carries_the_turn_id_of_its_turn_start(self, emitter, captured_events):
        """The badge attaches usage to a rendered turn by turn_id, so the pairing
        is the whole point of the event."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        start_turn_id = captured_events[0]["data"]["turn_id"]

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(38204, 512)))

        assert captured_events[1]["data"]["turn_id"] == start_turn_id

    def test_reports_provider_usage_not_the_internal_estimate(self, emitter, captured_events):
        """_estimate_tokens drives compaction; reporting it here would put a
        number on screen that disagrees with the provider's own accounting."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(38204, 512)))

        data = captured_events[-1]["data"]
        assert data["input_tokens"] == 38204
        assert data["output_tokens"] == 512

    def test_reports_cached_token_details_when_supplied(self, emitter, captured_events):
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(
            emitter.on_llm_end(None, MagicMock(), self._response(38204, 512, cached_tokens=1024))
        )

        assert captured_events[-1]["data"]["cached_tokens"] == 1024

    def test_omits_cached_tokens_when_provider_supplies_none(self, emitter, captured_events):
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(38204, 512)))

        assert "cached_tokens" not in captured_events[-1]["data"]

    def test_reports_turn_duration(self, emitter, captured_events):
        """Context size alone does not explain a slow task: every turn re-prefills
        the whole context, so duration is what makes the size actionable."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))
        emitter._turn_start_time -= 1.5  # backdate the turn by 1.5s

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(38204, 512)))

        assert 1400 <= captured_events[-1]["data"]["duration_ms"] <= 2000

    def test_response_keyword_argument_is_accepted(self, emitter, captured_events):
        """The SDK may pass the response by keyword."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(
            emitter.on_llm_end(None, MagicMock(), response=self._response(1234, 56))
        )

        assert captured_events[-1]["data"]["input_tokens"] == 1234

    def test_missing_usage_completes_the_turn_without_token_fields(self, emitter, captured_events):
        """A provider with no usage block must not break the turn."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(usage=False)))

        data = captured_events[-1]["data"]
        assert captured_events[-1]["type"] == "llm_turn_end"
        assert "input_tokens" not in data
        assert "output_tokens" not in data
        assert "duration_ms" in data

    def test_all_zero_usage_is_treated_as_no_measurement(self, emitter, captured_events):
        """A provider that sends a usage block of zeros has reported nothing, and a
        confident `0` on the badge is worse than no figure. Observed for real:
        LiteLLM omits the streaming usage chunk unless asked for it, and the SDK
        only asks when the client points at api.openai.com."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(0, 0, cached_tokens=0)))

        data = captured_events[-1]["data"]
        assert captured_events[-1]["type"] == "llm_turn_end"
        assert "input_tokens" not in data
        assert "output_tokens" not in data
        assert "cached_tokens" not in data
        assert "duration_ms" in data

    def test_a_real_turn_with_no_output_tokens_still_reports(self, emitter, captured_events):
        """Only a zero *prompt* is impossible. A turn that produced no output is
        merely unusual, so the prompt size still gets reported."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(1200, 0)))

        assert captured_events[-1]["data"]["input_tokens"] == 1200

    def test_absent_response_does_not_raise(self, emitter, captured_events):
        """Called with no response at all, the turn still completes."""
        asyncio.run(emitter.on_llm_start(None, MagicMock(name="agent")))

        asyncio.run(emitter.on_llm_end(None, MagicMock()))

        assert captured_events[-1]["type"] == "llm_turn_end"
        assert "input_tokens" not in captured_events[-1]["data"]

    def test_end_without_a_start_still_emits(self, emitter, captured_events):
        """No turn_id and no start time is degenerate, not fatal."""
        asyncio.run(emitter.on_llm_end(None, MagicMock(), self._response(100, 10)))

        data = captured_events[-1]["data"]
        assert captured_events[-1]["type"] == "llm_turn_end"
        assert "turn_id" not in data
        assert "duration_ms" not in data
        assert data["input_tokens"] == 100


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
