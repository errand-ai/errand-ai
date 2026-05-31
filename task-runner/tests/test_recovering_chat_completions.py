"""Tests for the _RecoveringChatCompletions wrapper in task-runner/main.py.

These tests use a fake inner ``chat.completions`` that returns crafted
``ChatCompletion``-shaped objects (plain attribute holders are sufficient
because the wrapper only uses ``getattr``).
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Ensure the (mocked) openai submodule paths the wrapper imports lazily
# resolve to something. The conftest mocks openai/openai.types — extend it
# with the chat-completion tool-call submodule so the `from ... import`
# inside _post_process succeeds.
sys.modules.setdefault("openai.types.chat", MagicMock())
_mock_tc_mod = MagicMock()


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, id, type, function):
        self.id = id
        self.type = type
        self.function = function


_mock_tc_mod.ChatCompletionMessageToolCall = _FakeToolCall
_mock_tc_mod.Function = _FakeFunction
sys.modules["openai.types.chat.chat_completion_message_tool_call"] = _mock_tc_mod

import main  # noqa: E402


def _make_response(*, content, tool_calls, reasoning_content=None, model="m1"):
    """Build a ChatCompletion-shaped object the wrapper can inspect/mutate."""
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], model=model)


class _FakeInner:
    def __init__(self, response):
        self._response = response
        self.create_calls = 0

    async def create(self, *args, **kwargs):
        self.create_calls += 1
        return self._response


@pytest.fixture(autouse=True)
def _capture_events(monkeypatch):
    """Capture emit_event invocations from main."""
    events: list[tuple[str, dict]] = []

    def fake_emit(event_type: str, data: dict) -> None:
        events.append((event_type, data))

    monkeypatch.setattr(main, "emit_event", fake_emit)
    return events


@pytest.mark.asyncio
async def test_recovers_xml_tool_call_from_reasoning_content(_capture_events):
    reasoning = (
        "I need to list the directory.\n"
        "<tool_call><function=execute_command>"
        "<parameter=command>ls</parameter>"
        "</function></tool_call>"
    )
    response = _make_response(
        content="", tool_calls=None, reasoning_content=reasoning, model="qwen3.6"
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    out = await wrapper.create()

    assert out is response
    assert isinstance(response.choices[0].message.tool_calls, list)
    assert len(response.choices[0].message.tool_calls) == 1
    tc = response.choices[0].message.tool_calls[0]
    assert tc.function.name == "execute_command"
    assert json.loads(tc.function.arguments) == {"command": "ls"}
    assert tc.id.startswith("call_recovered_")

    recovered_events = [e for e in _capture_events if e[0] == "tool_call_recovered_from_reasoning"]
    assert len(recovered_events) == 1
    payload = recovered_events[0][1]
    assert payload["model"] == "qwen3.6"
    assert payload["calls_recovered"] == 1
    assert payload["function_names"] == ["execute_command"]


@pytest.mark.asyncio
async def test_non_empty_content_passthrough(_capture_events):
    response = _make_response(
        content="Here is your answer",
        tool_calls=None,
        reasoning_content="<tool_call><function=ls></function></tool_call>",
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    assert response.choices[0].message.tool_calls is None
    assert _capture_events == []


@pytest.mark.asyncio
async def test_non_empty_tool_calls_passthrough(_capture_events):
    existing = [SimpleNamespace(id="call_existing", type="function")]
    response = _make_response(
        content="",
        tool_calls=existing,
        reasoning_content="<tool_call><function=ls></function></tool_call>",
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    assert response.choices[0].message.tool_calls is existing
    assert _capture_events == []


@pytest.mark.asyncio
async def test_prose_only_reasoning_passthrough(_capture_events):
    response = _make_response(
        content="",
        tool_calls=None,
        reasoning_content="I should think before I act, but I don't know what to do yet.",
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    assert response.choices[0].message.tool_calls is None
    assert _capture_events == []


@pytest.mark.asyncio
async def test_reasoning_content_accessed_via_getattr(_capture_events):
    """Even if `message` lacks `reasoning_content` attribute, getattr should default to None."""
    message = SimpleNamespace(content="", tool_calls=None)
    # reasoning_content intentionally absent
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)], model="m")
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    assert getattr(message, "tool_calls", "untouched") is None
    assert _capture_events == []


@pytest.mark.asyncio
async def test_unparseable_xml_emits_recovery_failed_event(_capture_events):
    reasoning = "<tool_call>garbage without function tag</tool_call>"
    response = _make_response(
        content="", tool_calls=None, reasoning_content=reasoning, model="qwen3.6"
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    # tool_calls remains untouched (None) — passthrough so EmptyResponseError still raises
    assert response.choices[0].message.tool_calls is None

    failed_events = [e for e in _capture_events if e[0] == "tool_call_recovery_failed"]
    assert len(failed_events) == 1
    payload = failed_events[0][1]
    assert payload["model"] == "qwen3.6"
    assert payload["match_count"] == 1
    assert payload["sample"] is not None
    assert "garbage" in payload["sample"]


@pytest.mark.asyncio
async def test_mixed_recovered_and_failed_blocks_emits_both_events(_capture_events):
    """When a response has one parseable and one unparseable <tool_call>,
    operators still need to see the failed-event sample so dialect variants
    don't get silently dropped."""
    reasoning = (
        "<tool_call>garbage with no function tag</tool_call>\n"
        "<tool_call><function=ls><parameter=path>/tmp</parameter></function></tool_call>"
    )
    response = _make_response(
        content="", tool_calls=None, reasoning_content=reasoning, model="qwen3.6"
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    # The good block was recovered…
    assert isinstance(response.choices[0].message.tool_calls, list)
    assert len(response.choices[0].message.tool_calls) == 1
    assert response.choices[0].message.tool_calls[0].function.name == "ls"

    # …and BOTH events are emitted
    recovered = [e for e in _capture_events if e[0] == "tool_call_recovered_from_reasoning"]
    failed = [e for e in _capture_events if e[0] == "tool_call_recovery_failed"]
    assert len(recovered) == 1
    assert recovered[0][1]["calls_recovered"] == 1
    assert len(failed) == 1
    assert failed[0][1]["match_count"] == 2
    assert "garbage" in failed[0][1]["sample"]


@pytest.mark.asyncio
async def test_inner_create_is_awaited_with_arguments_passed_through(_capture_events):
    response = _make_response(content="hi", tool_calls=None)
    inner = _FakeInner(response)
    wrapper = main._RecoveringChatCompletions(inner)

    out = await wrapper.create(model="x", messages=[{"role": "user", "content": "hi"}])

    assert out is response
    assert inner.create_calls == 1
