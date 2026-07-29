"""Tests for context pressure signalling and diagnostic snapshots.

The events under test exist to answer "how full is the window, and what filled
it" after the fact. Two properties matter more than the rest: pressure is
signalled on a *change* rather than continuously, and snapshots carry names and
sizes but never message content.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import main


@pytest.fixture
def captured_events(monkeypatch):
    events = []
    monkeypatch.setattr("main.emit_event", lambda t, d: events.append({"type": t, "data": d}))
    return events


@pytest.fixture(autouse=True)
def reset_context_state():
    """Threshold crossings and compaction backoff are remembered across turns, so
    state leaks between tests unless it is reset."""
    main._reset_context_tracking()
    main._reset_compaction_backoff()
    yield
    main._reset_context_tracking()
    main._reset_compaction_backoff()


@pytest.fixture
def limit(monkeypatch):
    """A round ceiling keeps the arithmetic in the tests readable."""
    monkeypatch.setattr(main, "MAX_CONTEXT_TOKENS", 100_000)
    return 100_000


def _usage(input_tokens):
    return SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=100,
            total_tokens=input_tokens + 100,
            input_tokens_details=None,
        )
    )


def _turn(emitter, input_tokens):
    """Run one complete model turn reporting the given prompt size."""
    asyncio.run(emitter.on_llm_start(None, MagicMock()))
    asyncio.run(emitter.on_llm_end(None, MagicMock(), _usage(input_tokens)))


def _of_type(events, event_type):
    return [e for e in events if e["type"] == event_type]


@pytest.fixture
def emitter():
    return main.StreamEventEmitter()


# --- Message fixtures -------------------------------------------------------

SECRET = "s3cret-customer-record-do-not-log"


def _messages_with_a_large_tool_result():
    return [
        {"role": "user", "content": "do the thing"},
        {"type": "function_call", "call_id": "c1", "name": "execute_command",
         "arguments": '{"command": "ls"}'},
        {"type": "function_call_output", "call_id": "c1", "output": SECRET * 2000},
        {"role": "assistant", "content": "done"},
    ]


# --- context_pressure -------------------------------------------------------


class TestContextPressure:
    def test_crossing_a_threshold_signals_once(self, emitter, captured_events, limit):
        _turn(emitter, 76_000)  # 76% — crosses 75%

        pressure = _of_type(captured_events, "context_pressure")
        assert len(pressure) == 1
        assert pressure[0]["data"]["threshold"] == 0.75
        assert pressure[0]["data"]["input_tokens"] == 76_000
        assert pressure[0]["data"]["limit"] == limit

    def test_remaining_above_a_crossed_threshold_does_not_re_signal(
        self, emitter, captured_events, limit
    ):
        """Continuous warnings would be noise; the operator needs to know when the
        situation changes, not that it persists."""
        _turn(emitter, 76_000)
        _turn(emitter, 78_000)
        _turn(emitter, 80_000)

        assert len(_of_type(captured_events, "context_pressure")) == 1

    def test_below_all_thresholds_is_silent(self, emitter, captured_events, limit):
        _turn(emitter, 20_000)
        _turn(emitter, 50_000)

        assert _of_type(captured_events, "context_pressure") == []

    def test_crossing_a_second_threshold_signals_again(self, emitter, captured_events, limit):
        _turn(emitter, 76_000)
        _turn(emitter, 91_000)

        pressure = _of_type(captured_events, "context_pressure")
        assert [p["data"]["threshold"] for p in pressure] == [0.75, 0.90]

    def test_passing_several_thresholds_in_one_turn_signals_the_highest_once(
        self, emitter, captured_events, limit
    ):
        """One turn is one change of situation, however many lines it stepped over."""
        _turn(emitter, 95_000)

        pressure = _of_type(captured_events, "context_pressure")
        assert len(pressure) == 1
        assert pressure[0]["data"]["threshold"] == 0.90

    def test_falling_back_and_re_crossing_signals_again(self, emitter, captured_events, limit):
        """Compaction pulls the context back down; climbing to the threshold again
        is a new event, and that sawtooth is the signal worth seeing."""
        _turn(emitter, 76_000)
        _turn(emitter, 40_000)  # compaction pulled it back
        _turn(emitter, 76_000)

        assert len(_of_type(captured_events, "context_pressure")) == 2

    def test_silent_when_the_provider_reports_no_usage(self, emitter, captured_events, limit):
        asyncio.run(emitter.on_llm_start(None, MagicMock()))
        asyncio.run(emitter.on_llm_end(None, MagicMock(), SimpleNamespace(usage=None)))

        assert _of_type(captured_events, "context_pressure") == []


# --- context_snapshot -------------------------------------------------------


class TestContextSnapshot:
    def test_ordinary_turns_produce_no_snapshot(self, emitter, captured_events, limit):
        _turn(emitter, 20_000)

        assert _of_type(captured_events, "context_snapshot") == []

    def test_snapshot_accompanies_a_threshold_crossing(self, emitter, captured_events, limit):
        main._record_model_input(_messages_with_a_large_tool_result())

        _turn(emitter, 76_000)

        snapshots = _of_type(captured_events, "context_snapshot")
        assert len(snapshots) == 1
        assert snapshots[0]["data"]["reason"] == "threshold_crossed"
        assert snapshots[0]["data"]["input_tokens"] == 76_000
        assert snapshots[0]["data"]["message_count"] == 4

    def test_snapshot_on_compaction_trigger(self, captured_events, monkeypatch):
        monkeypatch.setattr(main, "MAX_CONTEXT_TOKENS", 10)  # force the trigger
        # No model configured, so compaction bails out immediately after the
        # trigger rather than making a summarisation call.
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.delenv("COMPACTION_MODEL", raising=False)

        main._compact_context(_messages_with_a_large_tool_result())

        snapshots = _of_type(captured_events, "context_snapshot")
        assert [s["data"]["reason"] for s in snapshots] == ["compaction_triggered"]
        assert snapshots[0]["data"]["message_count"] == 4

    def test_snapshot_on_compaction_failure(self, captured_events):
        main._record_compaction_failure(_messages_with_a_large_tool_result())

        snapshots = _of_type(captured_events, "context_snapshot")
        assert [s["data"]["reason"] for s in snapshots] == ["compaction_failed"]

    def test_contributors_identify_role_tool_and_size(self, captured_events, limit, emitter):
        main._record_model_input(_messages_with_a_large_tool_result())

        _turn(emitter, 76_000)

        contributors = _of_type(captured_events, "context_snapshot")[0]["data"]["top_contributors"]
        largest = contributors[0]
        assert largest["tool"] == "execute_command"
        assert largest["role"] == "tool_result"
        assert largest["chars"] > 10_000

    def test_contributors_are_ranked_by_size(self, captured_events, limit, emitter):
        main._record_model_input(_messages_with_a_large_tool_result())

        _turn(emitter, 76_000)

        contributors = _of_type(captured_events, "context_snapshot")[0]["data"]["top_contributors"]
        sizes = [c["chars"] for c in contributors]
        assert sizes == sorted(sizes, reverse=True)

    def test_contributors_are_capped(self, captured_events, limit, emitter):
        main._record_model_input(
            [{"role": "user", "content": f"message {i}"} for i in range(50)]
        )

        _turn(emitter, 76_000)

        contributors = _of_type(captured_events, "context_snapshot")[0]["data"]["top_contributors"]
        assert len(contributors) <= main.SNAPSHOT_TOP_CONTRIBUTORS

    def test_snapshot_carries_no_message_content(self, captured_events, limit, emitter):
        """The diagnostic question is which inputs consumed the window, which names
        and sizes answer. Content would add nothing and would place task data into
        log retention."""
        main._record_model_input(_messages_with_a_large_tool_result())

        _turn(emitter, 76_000)

        payload = json.dumps(_of_type(captured_events, "context_snapshot")[0])
        assert SECRET not in payload
        assert "do the thing" not in payload
        assert "ls" not in payload

    def test_snapshot_reports_the_estimate_alongside_the_measurement(
        self, captured_events, limit, emitter
    ):
        """The estimate drives compaction and has never been checked against the
        provider's own count; carrying both makes the divergence observable."""
        main._record_model_input(_messages_with_a_large_tool_result())

        _turn(emitter, 76_000)

        data = _of_type(captured_events, "context_snapshot")[0]["data"]
        assert data["input_tokens"] == 76_000
        assert data["estimated_tokens"] > 0

    def test_snapshot_survives_an_unrecorded_context(self, captured_events, limit, emitter):
        """No messages recorded yet is degenerate, not fatal."""
        _turn(emitter, 76_000)

        snapshots = _of_type(captured_events, "context_snapshot")
        assert len(snapshots) == 1
        assert snapshots[0]["data"]["message_count"] == 0
        assert snapshots[0]["data"]["top_contributors"] == []
