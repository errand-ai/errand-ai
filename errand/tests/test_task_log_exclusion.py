"""Tests for the live-path exclusion of diagnostic task events.

Diagnostic events are large and exist for retrospective analysis. Publishing
them and filtering client-side would still carry the payload across the wire and
would displace real entries in the bounded replay buffer, so they are dropped
server-side before either operation.

The failure mode here is invisible by construction — an over-broad denylist
silently swallows real log lines — so these tests assert both directions.
"""

import json

import pytest

from task_manager import LIVE_EXCLUDED_EVENT_TYPES, TaskManager, _live_log_message


class FakeValkey:
    """Records what the worker publishes and what it appends to the buffer."""

    def __init__(self, publish_fails=False):
        self.published: list[tuple[str, str]] = []
        self.buffered: list[str] = []
        self._publish_fails = publish_fails

    async def publish(self, channel, message):
        if self._publish_fails:
            raise RuntimeError("valkey unavailable")
        self.published.append((channel, message))

    def pipeline(self, transaction=False):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, valkey):
        self._valkey = valkey
        self._pending: list[str] = []

    def rpush(self, key, message):
        self._pending.append(message)

    def ltrim(self, key, start, end):
        pass

    def expire(self, key, ttl):
        pass

    async def execute(self):
        self._valkey.buffered.extend(self._pending)
        self._pending = []


@pytest.fixture
def manager():
    tm = TaskManager.__new__(TaskManager)
    tm._task_log_buffer_max_entries = 100
    tm._task_log_buffer_ttl_seconds = 3600
    return tm


def _event_line(event_type, data):
    return json.dumps({"type": event_type, "data": data})


# --- Message mapping --------------------------------------------------------


class TestLiveLogMessage:
    def test_structured_event_becomes_a_task_event(self):
        msg = _live_log_message(_event_line("tool_call", {"tool": "execute_command"}))

        assert json.loads(msg) == {
            "event": "task_event",
            "type": "tool_call",
            "data": {"tool": "execute_command"},
        }

    def test_non_json_line_becomes_a_raw_event(self):
        line = "Traceback (most recent call last):"

        assert json.loads(_live_log_message(line)) == {
            "event": "task_event",
            "type": "raw",
            "data": {"line": line},
        }

    def test_json_without_the_event_shape_becomes_a_raw_event(self):
        line = json.dumps({"type": "tool_call"})  # no data key

        assert json.loads(_live_log_message(line))["type"] == "raw"

    def test_unhashable_type_value_does_not_raise(self):
        """The parser consumes arbitrary container stderr, not only the runner's
        own events — a subprocess the agent runs can put any JSON on that stream.
        Testing set membership on a non-string `type` raises TypeError, and the
        caller sits inside the log-streaming loop's single try/except, so one such
        line would end log capture for the rest of the task.

        The pre-existing code never hashed the value, so this is a regression
        guard rather than a hypothetical.
        """
        line = json.dumps({"type": {"nested": 1}, "data": {}})

        msg = _live_log_message(line)

        assert msg is not None
        assert json.loads(msg)["type"] == {"nested": 1}

    def test_list_type_value_does_not_raise(self):
        line = json.dumps({"type": ["a"], "data": {}})

        assert _live_log_message(line) is not None

    def test_excluded_type_yields_no_message(self):
        line = _event_line("context_snapshot", {"top_contributors": []})

        assert _live_log_message(line) is None

    def test_context_snapshot_is_the_excluded_type(self):
        assert "context_snapshot" in LIVE_EXCLUDED_EVENT_TYPES

    def test_the_other_new_event_types_are_not_excluded(self):
        """Only the large diagnostic payload is withheld; the per-turn events are
        exactly what the live view is for."""
        assert "llm_turn_end" not in LIVE_EXCLUDED_EVENT_TYPES
        assert "context_pressure" not in LIVE_EXCLUDED_EVENT_TYPES


# --- Worker forwarding ------------------------------------------------------


class TestForwardLogLine:
    async def test_excluded_event_is_not_published(self, manager):
        valkey = FakeValkey()

        await manager._forward_log_line(
            valkey, _event_line("context_snapshot", {"message_count": 40}), "ch", "buf"
        )

        assert valkey.published == []

    async def test_excluded_event_is_not_buffered(self, manager):
        """Publish and buffer are separate operations, and excluding only the
        publish would leave the payload in the replay buffer."""
        valkey = FakeValkey()

        await manager._forward_log_line(
            valkey, _event_line("context_snapshot", {"message_count": 40}), "ch", "buf"
        )

        assert valkey.buffered == []

    async def test_non_excluded_event_is_published_and_buffered(self, manager):
        valkey = FakeValkey()
        line = _event_line("llm_turn_end", {"turn_id": "abc12345", "input_tokens": 38204})

        await manager._forward_log_line(valkey, line, "ch", "buf")

        assert len(valkey.published) == 1
        channel, msg = valkey.published[0]
        assert channel == "ch"
        assert json.loads(msg)["type"] == "llm_turn_end"
        assert valkey.buffered == [msg]

    async def test_raw_lines_still_flow(self, manager):
        valkey = FakeValkey()

        await manager._forward_log_line(valkey, "some library log line", "ch", "buf")

        assert json.loads(valkey.published[0][1])["type"] == "raw"
        assert len(valkey.buffered) == 1

    async def test_buffer_is_skipped_when_the_publish_fails(self, manager):
        """The buffer mirrors what subscribers actually received."""
        valkey = FakeValkey(publish_fails=True)

        await manager._forward_log_line(valkey, "a line", "ch", "buf")

        assert valkey.buffered == []
