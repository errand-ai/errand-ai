## Context

The errand task-runner constructs `AsyncOpenAI(base_url=..., api_key=..., timeout=...)` in `task-runner/main.py:main()` and registers it via `set_default_openai_client(client)` so the agents-SDK uses it for all chat completions. The agents-SDK then calls `client.chat.completions.create(...)` internally and normalises the result into a `RunResult` whose `final_output` is a string and whose `new_items` contains structured tool-call entries. By the time the agent loop's `extract_output` runs, `reasoning_content` has been discarded — the empty-response detection cannot see it.

To rescue tool calls emitted as XML inside `reasoning_content`, the response must be mutated **before** the agents-SDK consumes it. This means hooking the OpenAI Python client at the `chat.completions.create` boundary.

## Goals / Non-Goals

**Goals:**
- Rescue a chat-completion response whose model emitted a tool call as Qwen-XML in `reasoning_content` so the agent loop can act on it instead of raising EmptyResponseError.
- Cover the two Qwen-XML variants seen in the wild and JSON-blob argument bodies.
- Be transparent: well-behaved responses pass through with zero observable change.
- Emit a `tool_call_recovered_from_reasoning` event on every successful rescue.

**Non-Goals:**
- Fix the upstream chat templates or LiteLLM-side parse hooks.
- Recover responses where the model emitted something other than tool calls in `reasoning_content` (e.g. prose answers).
- Handle vendor-specific dialects beyond Qwen-XML (Claude tool-use blocks, model-card-specific JSON shapes).
- Translate well-formed responses to a different dialect.

## Decisions

### Hook point: wrap `client.chat.completions.create`

The cleanest layer is the OpenAI Python client. The agents-SDK calls `client.chat.completions.create(...)` for every turn; intercepting that one call point covers every code path that uses the client. Alternative options considered:

- **Custom httpx transport** — works at the byte level; rejected as too invasive (would need to parse the OpenAI wire format ourselves and is brittle across SDK versions).
- **Monkey-patch the SDK** — rejected; couples us to internal SDK structure.
- **Layer at `extract_output`** — rejected; the SDK has already discarded `reasoning_content` by then.

The wrapper SHALL be implemented by constructing a small `_RecoveringChatCompletions` adapter that holds a reference to the real `client.chat.completions` and exposes the same `create()` signature, post-processing the response before returning it. The adapter is installed by assigning `client.chat.completions = adapter` on the `AsyncOpenAI` instance prior to `set_default_openai_client(client)`. Subclassing `AsyncOpenAI` is rejected as more invasive — direct attribute swap on a single instance is contained to the runner's `main()` function.

### Streaming vs non-streaming paths

The openai-agents SDK calls `client.chat.completions.create(stream=True)` (see `agents/models/openai_chatcompletions.py`), so `create()` returns an `AsyncStream[ChatCompletionChunk]`, not a `ChatCompletion`. A non-streaming-only post-processor is silently a no-op because the stream object has no `choices[0].message` attribute. The wrapper therefore inspects `kwargs.get("stream")` and branches:

- **Non-streaming**: the response is a `ChatCompletion`. Apply detection criteria to `choices[0].message` directly and mutate `message.tool_calls` in place.
- **Streaming**: the response is an `AsyncStream[ChatCompletionChunk]`. Return an async generator that (a) forwards every original chunk untouched (preserves streaming UX), (b) accumulates `delta.content`, `delta.tool_calls`-presence, and `delta.reasoning_content` across chunks, and (c) after the stream ends, runs the same detection criteria against the accumulated state. If recovery applies, the generator yields one additional synthesised `ChatCompletionChunk` whose `delta.tool_calls` contains the recovered calls and whose `finish_reason="tool_calls"` — the agents-SDK stream handler accumulates this exactly as it would a model-emitted tool call.

### Detection criteria (all must hold to trigger recovery)

1. `choices[0].message.content` is `""` or `None`.
2. `choices[0].message.tool_calls` is `None` or `[]`.
3. `getattr(choices[0].message, "reasoning_content", None)` is a non-empty string.
4. The reasoning_content contains at least one `<tool_call>` substring.

If any condition fails, the wrapper returns the response unchanged.

This conjunction is deliberately strict to avoid false positives: a well-behaved response has `content` set or `tool_calls` set, so it short-circuits at step 1 or 2. A reasoning-only response with no `<tool_call>` markup is also a pass-through.

### Parser: regex first, then per-call structural parse

The parser SHALL extract every `<tool_call>...</tool_call>` block from `reasoning_content` (re.findall with DOTALL). For each block it SHALL:

1. Extract the function name. Two patterns are supported:
   - `<function=NAME>` (attribute form)
   - `<function_name>NAME</function_name>` (element form)
2. Extract arguments. Three argument shapes are supported, tried in order:
   - `<arguments>{...JSON...}</arguments>` — JSON blob. The regex uses greedy `.*` anchored to the closing `</arguments>` tag so nested-object JSON (e.g. `{"server": {"host": "x"}, "retries": 3}`) is captured in full; a non-greedy match would truncate at the first `}` and silently fail recovery for any tool with nested arguments.
   - One or more `<parameter=key>value</parameter>` tags — key/value form.
   - `<parameter><name>key</name><value>value</value></parameter>` — verbose form.

   The first matching shape wins. For key/value form, all parameter values are passed through verbatim as strings (the agent-side tool definition will coerce types where needed).

Each successfully parsed block produces one `ChatCompletionMessageToolCall`:

```python
{
  "id": f"call_recovered_{secrets.token_hex(6)}",
  "type": "function",
  "function": {"name": <name>, "arguments": json.dumps(<args_dict>)}
}
```

If `_no_ block can be parsed_` (regex match found, but neither name nor any argument shape could be extracted), the wrapper passes the original response through and emits a `tool_call_recovery_failed` event with the partial match for diagnostics. The agents-SDK will then raise EmptyResponseError as it does today — the runner is no worse off than before.

The wrapper SHALL emit `tool_call_recovery_failed` even when **some** blocks were successfully recovered but **others** were unparseable in the same response. The recovered-event is also fired (carrying the rescued calls); the failed-event carries the diagnostic sample of the first unparseable block. Without this, operators would lose visibility into new dialect variants that happen to appear alongside well-formed blocks.

For the **truncated-opener** case (a `<tool_call>` substring is present but `_TOOL_CALL_BLOCK_RE` matches zero closed blocks — e.g. the model emitted `<tool_call><function=foo` and stopped), the trigger is `reasoning_content.count("<tool_call>") > len(recovered_dicts)`, not the closed-block count. The sample is built from the first opener forward (≤ 256 chars) so the truncation shape is visible.

For the **dangling-closer** case (`</tool_call>` is present in `reasoning_content` but no `<tool_call>` opener exists — model emitted closing scaffolding only), nothing is recoverable (there is no function name to invoke), but the wrapper SHALL still emit `tool_call_recovery_failed` with `match_count=0` and a ≤ 256-character window centred on the first `</tool_call>`. This distinct failure mode is observed in prod alongside genuine empty responses; without the event operators cannot distinguish it from other empty-response causes.

### Response mutation: in-place on the dataclass-like SDK object

For the **non-streaming** path, `openai>=1.x` returns `ChatCompletion` Pydantic objects whose `message` is mutable. The wrapper SHALL:

1. Set `choices[0].message.tool_calls` to the list of recovered calls.
2. Leave `content` as is (empty), since the recovered calls are the actual content.
3. Optionally strip the `<tool_call>` blocks from `reasoning_content`, leaving just the prose preamble. Default: leave intact, so debugging still has the full reasoning trail; the agents-SDK does not look at `reasoning_content` anyway.
4. Leave `finish_reason` as is.

Other fields are unchanged. The wrapper SHALL NOT touch `usage` — the model's own token counts remain the truth.

For the **streaming** path, the existing chunks pass through untouched (`message` doesn't exist on chunks) and the rescue is delivered as **one additional synthesised chunk** appended after the inner stream ends. The synthesised chunk SHALL have:

- `delta.role="assistant"` and `delta.tool_calls=[ChoiceDeltaToolCall(...)]` with each recovered call's `id`, `name`, and full JSON-encoded `arguments`.
- `finish_reason="tool_calls"` so the agents-SDK stream handler treats the turn as complete.
- `id`, `model`, `created` copied from the last real chunk for consistency.

The agents-SDK stream handler accumulates `delta.tool_calls` chunk-by-chunk into its `state.function_calls` dict; one final chunk carrying the complete tool-call set is therefore equivalent to the model emitting it natively.

### Event semantics

- `tool_call_recovered_from_reasoning` event payload: `{ model, calls_recovered: <int>, function_names: <list[str]> }`. Emitted on every successful rescue (whether all blocks succeeded or only some).
- `tool_call_recovery_failed` event payload: `{ model, match_count: <int>, sample: <truncated string up to 256 chars> }`. Emitted in every failure shape:
  - `match_count > 0` and `sample` non-null: at least one `<tool_call>` opener was present and at least one block was unparseable (covers all-malformed, partial recovery, truncated opener).
  - `match_count == 0` and `sample` non-null: dangling-closer pattern — `</tool_call>` present without an opener.

These give operators four distinct Loki signals to monitor: (a) how often the dialect hits us and from which models, (b) when the parser falls short and needs more patterns, (c) when models emit truncated openers (typically generation cutoff), and (d) when models emit only closing scaffolding without an opener (typically the model giving up mid-thought).

### No setting / no opt-out

The behaviour is always-on. Detection is strict enough that there is no realistic way to harm a well-behaved response. Adding a setting now would be premature complexity.

## Risks / Trade-offs

- [Risk] A future model emits something that *looks like* `<tool_call>` markup but isn't (e.g. quoted in a code block as part of an explanation). The parser would extract a malformed call and the agent would try to invoke a non-existent tool. → Mitigation: detection only triggers when `content == ""` AND `tool_calls is None` (i.e. the agent has nothing else to act on). The recovered tool call is no worse than EmptyResponseError; if the agent invokes a missing tool, the existing tool-error path handles it gracefully.
- [Risk] Future LiteLLM or OpenAI SDK versions might restructure `ChatCompletion` so `reasoning_content` is no longer a string attribute. → Mitigation: detection uses `getattr(..., "reasoning_content", None)` with a string-type check; an unexpected shape causes pass-through, not crash.
- [Trade-off] The wrapper adds an O(n) regex sweep over `reasoning_content` for every chat completion. n is small in practice (reasoning bodies are bounded by the model's output budget). Acceptable.

## Migration Plan

1. Ship the wrapper with detection always on. No DB migration, no feature flag.
2. Existing tasks behave unchanged unless they previously hit the bug — those now succeed.
3. Rollback: revert the wrapper installation. No state.

## Open Questions

- Should we also handle responses where the model emits a tool call in `content` as XML (not `reasoning_content`)? Not observed yet; defer until we see it in Loki. Adding now would expand the detector and false-positive risk for no current benefit.
- Should the parser support multi-step tool plans inside a single reasoning block (a sequence of `<tool_call>` followed by `<thought>` followed by `<tool_call>`)? The agents-SDK typically expects one turn = one tool-call batch; emitting multiple is fine, but interleaved thought+call is rare. Defer until observed.
