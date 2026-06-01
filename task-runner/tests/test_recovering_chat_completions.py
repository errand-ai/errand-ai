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


class _FakeChunkChoice:
    def __init__(self, index, delta, finish_reason=None):
        self.index = index
        self.delta = delta
        self.finish_reason = finish_reason


class _FakeChunkDelta:
    def __init__(self, role=None, content=None, tool_calls=None, reasoning_content=None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content


class _FakeChunkToolCall:
    def __init__(self, index, id, type, function):
        self.index = index
        self.id = id
        self.type = type
        self.function = function


class _FakeChunkToolCallFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeChunk:
    def __init__(self, id, model, created, choices, object="chat.completion.chunk"):
        self.id = id
        self.model = model
        self.created = created
        self.choices = choices
        self.object = object


# Mock the openai chunk types so the wrapper's synthesis import succeeds
_FakeChunkMod = type(sys)("openai.types.chat.chat_completion_chunk")
_FakeChunkMod.Choice = _FakeChunkChoice
_FakeChunkMod.ChoiceDelta = _FakeChunkDelta
_FakeChunkMod.ChoiceDeltaToolCall = _FakeChunkToolCall
_FakeChunkMod.ChoiceDeltaToolCallFunction = _FakeChunkToolCallFunction
sys.modules["openai.types.chat.chat_completion_chunk"] = _FakeChunkMod
_chat_mod = sys.modules["openai.types.chat"]
_chat_mod.ChatCompletionChunk = _FakeChunk

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
async def test_dangling_close_tag_emits_recovery_failed(_capture_events):
    """Real prod failure mode: model emits only `</tool_call>` (and `</function>`,
    `</parameter>`) without the opener. Nothing to recover, but operators still
    need the diagnostic so they can quantify this pattern."""
    reasoning = (
        "The file wasn't created at all. The warning about 'parents' being "
        "stringified suggests the API call failed silently. Let me try a "
        "different approach.\n</parameter>\n</function>\n</tool_call>"
    )
    response = _make_response(
        content="", tool_calls=None, reasoning_content=reasoning, model="qwen3.6"
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    # Nothing rescued (correct — there's no function name to invoke)
    assert response.choices[0].message.tool_calls is None
    # …but recovery_failed IS emitted with the dangling-closer sample
    failed = [e for e in _capture_events if e[0] == "tool_call_recovery_failed"]
    assert len(failed) == 1
    payload = failed[0][1]
    assert payload["model"] == "qwen3.6"
    assert payload["match_count"] == 0  # no `<tool_call>` openers
    assert payload["sample"] is not None
    assert "</tool_call>" in payload["sample"]


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
async def test_truncated_tool_call_marker_emits_recovery_failed(_capture_events):
    """Truncated markup with no closing </tool_call> finds zero closed blocks
    via the parser, but the opener was present. The wrapper must still emit
    recovery_failed so operators can spot the truncation pattern."""
    reasoning = (
        "I'll start a tool call but cut off mid-thought\n"
        "<tool_call><function=fetch><parameter=url>https://example.com"
        # no </parameter></function></tool_call> — truncated
    )
    response = _make_response(
        content="", tool_calls=None, reasoning_content=reasoning, model="qwen3.6"
    )
    wrapper = main._RecoveringChatCompletions(_FakeInner(response))

    await wrapper.create()

    # Nothing recovered
    assert response.choices[0].message.tool_calls is None
    # …but the failure IS reported
    failed = [e for e in _capture_events if e[0] == "tool_call_recovery_failed"]
    assert len(failed) == 1
    payload = failed[0][1]
    assert payload["model"] == "qwen3.6"
    assert payload["match_count"] == 1  # one <tool_call> opener
    assert payload["sample"] is not None
    assert payload["sample"].startswith("<tool_call>")


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


def _make_chunks_for_reasoning(reasoning_text: str, model: str = "qwen3.6") -> list:
    """Split reasoning_text across two chunks (simulating real LiteLLM stream)
    plus a final empty chunk with finish_reason='stop'."""
    mid = len(reasoning_text) // 2
    return [
        _FakeChunk(id="c1", model=model, created=1, choices=[
            _FakeChunkChoice(0, _FakeChunkDelta(role="assistant", reasoning_content=reasoning_text[:mid])),
        ]),
        _FakeChunk(id="c1", model=model, created=1, choices=[
            _FakeChunkChoice(0, _FakeChunkDelta(reasoning_content=reasoning_text[mid:])),
        ]),
        _FakeChunk(id="c1", model=model, created=1, choices=[
            _FakeChunkChoice(0, _FakeChunkDelta(), finish_reason="stop"),
        ]),
    ]


class _FakeStreamInner:
    """Inner chat.completions returning an async iterator over chunks when stream=True."""
    def __init__(self, chunks):
        self._chunks = chunks
        self._closed = False

    async def create(self, *args, **kwargs):
        chunks = self._chunks
        outer_self = self

        class _Stream:
            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                for c in chunks:
                    yield c

            async def aclose(self):
                outer_self._closed = True

        return _Stream()


@pytest.mark.asyncio
async def test_streaming_recovers_xml_tool_call_from_reasoning_content(_capture_events):
    """Replicates prod failure mode: agents-SDK calls create(stream=True);
    LiteLLM yields chunks with reasoning_content carrying Qwen-XML; the
    last chunk has finish_reason=stop and no tool_calls. Wrapper must
    yield a synthesized tool-call chunk so downstream sees the tool call."""
    reasoning = (
        "Let me verify\n\n"
        "<tool_call>\n"
        "<function=execute_command>\n"
        "<parameter=command>\ngrep -in foo /workspace/verify.md | tail -20\n</parameter>\n"
        "<parameter=working_directory>\n/workspace\n</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    chunks = _make_chunks_for_reasoning(reasoning, model="qwen3.6-35b-a3b-ud-mlx")
    inner = _FakeStreamInner(chunks)
    wrapper = main._RecoveringChatCompletions(inner)

    stream = await wrapper.create(stream=True)
    received = []
    async for c in stream:
        received.append(c)

    # Original 3 chunks + 1 synthesized tool-call chunk
    assert len(received) == 4
    synth = received[-1]
    assert synth.choices[0].finish_reason == "tool_calls"
    tcs = synth.choices[0].delta.tool_calls
    assert len(tcs) == 1
    assert tcs[0].function.name == "execute_command"
    args = json.loads(tcs[0].function.arguments)
    assert args["command"].strip().startswith("grep -in foo")
    assert args["working_directory"] == "/workspace"
    assert tcs[0].id.startswith("call_recovered_")

    # Event emitted
    recovered = [e for e in _capture_events if e[0] == "tool_call_recovered_from_reasoning"]
    assert len(recovered) == 1
    payload = recovered[0][1]
    assert payload["model"] == "qwen3.6-35b-a3b-ud-mlx"
    assert payload["calls_recovered"] == 1
    assert payload["function_names"] == ["execute_command"]


@pytest.mark.asyncio
async def test_streaming_passthrough_when_tool_calls_seen(_capture_events):
    """A well-formed streaming response that already delivers tool_calls
    must pass through unchanged; no synthesized chunk."""
    chunks = [
        _FakeChunk(id="c", model="m", created=1, choices=[
            _FakeChunkChoice(0, _FakeChunkDelta(
                tool_calls=[_FakeChunkToolCall(0, "call_real", "function",
                    _FakeChunkToolCallFunction("ls", '{"path":"/"}'))],
            )),
        ]),
        _FakeChunk(id="c", model="m", created=1, choices=[
            _FakeChunkChoice(0, _FakeChunkDelta(), finish_reason="tool_calls"),
        ]),
    ]
    wrapper = main._RecoveringChatCompletions(_FakeStreamInner(chunks))

    received = []
    async for c in (await wrapper.create(stream=True)):
        received.append(c)

    assert len(received) == 2  # no synthetic chunk added
    assert _capture_events == []


@pytest.mark.asyncio
async def test_streaming_dangling_close_tag_emits_recovery_failed(_capture_events):
    """Same as the non-streaming dangling-closer case but delivered via
    chunked reasoning_content deltas."""
    reasoning = (
        "Trying again, but the schema doesn't fit.\n"
        "</parameter>\n</function>\n</tool_call>"
    )
    chunks = _make_chunks_for_reasoning(reasoning, model="qwen3.6-35b-a3b-ud-mlx")
    wrapper = main._RecoveringChatCompletions(_FakeStreamInner(chunks))

    received = []
    async for c in (await wrapper.create(stream=True)):
        received.append(c)

    # No synthetic chunk added — there's nothing to call
    assert len(received) == 3
    failed = [e for e in _capture_events if e[0] == "tool_call_recovery_failed"]
    assert len(failed) == 1
    payload = failed[0][1]
    assert payload["model"] == "qwen3.6-35b-a3b-ud-mlx"
    assert payload["match_count"] == 0
    assert payload["sample"] is not None
    assert "</tool_call>" in payload["sample"]


@pytest.mark.asyncio
async def test_streaming_passthrough_when_no_xml_markup(_capture_events):
    """Prose-only reasoning with no <tool_call> markup must not trigger
    recovery — the agent's existing empty-response handling still applies."""
    chunks = _make_chunks_for_reasoning("I should think about this but I have no plan.")
    wrapper = main._RecoveringChatCompletions(_FakeStreamInner(chunks))

    received = []
    async for c in (await wrapper.create(stream=True)):
        received.append(c)

    assert len(received) == 3  # original chunks only
    assert _capture_events == []


@pytest.mark.asyncio
async def test_inner_create_is_awaited_with_arguments_passed_through(_capture_events):
    response = _make_response(content="hi", tool_calls=None)
    inner = _FakeInner(response)
    wrapper = main._RecoveringChatCompletions(inner)

    out = await wrapper.create(model="x", messages=[{"role": "user", "content": "hi"}])

    assert out is response
    assert inner.create_calls == 1
