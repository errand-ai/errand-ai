## 1. Bump version and create feature branch

- [x] 1.1 Bump `VERSION` to `0.124.x` (minor — new feature, backwards-compatible; subsequent patch bumps applied for review iterations)
- [x] 1.2 Create feature branch `recover-xml-tool-calls-from-reasoning`

## 2. Parser module

- [x] 2.1 Add a new module `task-runner/xml_tool_call_recovery.py` (kept separate from `main.py` for unit-test isolation and reuse)
- [x] 2.2 Implement `parse_xml_tool_calls(reasoning_content: str) -> tuple[list[dict], int, str | None]` returning `(recovered_calls, total_blocks_matched, sample_of_failed_block_or_None)`. Each `recovered_call` is the OpenAI dict shape: `{"id": ..., "type": "function", "function": {"name": ..., "arguments": ...}}` with `arguments` as a JSON-encoded string.
- [x] 2.3 Implement function-name extraction supporting `<function=NAME>` and `<function_name>NAME</function_name>` (first match wins)
- [x] 2.4 Implement argument extraction supporting in order: `<arguments>{JSON}</arguments>`, `<parameter=KEY>VALUE</parameter>` repeated, `<parameter><name>KEY</name><value>VALUE</value></parameter>` verbose form
- [x] 2.5 Each recovered call SHALL have `id` of form `call_recovered_<12-hex-chars>` generated with `secrets.token_hex(6)`
- [x] 2.6 Skip individual malformed blocks rather than failing the whole parse; return the sample of the first failure (≤ 256 chars) for diagnostics

## 3. Wrapper around `client.chat.completions.create`

- [x] 3.1 In `task-runner/main.py`, add a private class `_RecoveringChatCompletions` that holds a reference to the real `client.chat.completions` object and exposes the same `create()` async method signature
- [x] 3.2 `create()` SHALL `await self._inner.create(*args, **kwargs)` to obtain the response, then call a private helper `_post_process(response)` before returning it
- [x] 3.3 `_post_process` SHALL apply the 4-condition detection (empty content, null/empty tool_calls, non-empty reasoning_content, contains `<tool_call>`). If any fails, return response unchanged.
- [x] 3.4 On match, call `parse_xml_tool_calls(reasoning_content)`. If `recovered_calls` is non-empty, mutate `response.choices[0].message.tool_calls` to that list and emit `tool_call_recovered_from_reasoning` event. If `recovered_calls` is empty but `total_blocks_matched > 0`, emit `tool_call_recovery_failed` event and return response unchanged.
- [x] 3.5 In `main()`, after constructing `client = AsyncOpenAI(**client_kwargs)`, install the wrapper: `client.chat.completions = _RecoveringChatCompletions(client.chat.completions)`. This must happen before `set_default_openai_client(client)`.
- [x] 3.6 Confirm the wrapper is on the hot path by adding a one-line INFO log on first use (`logger.info("XML tool call recovery active for chat.completions")`)

## 4. Event payload helpers

- [x] 4.1 Add `_emit_recovered_event(response, recovered_calls)` helper that builds the payload `{model, calls_recovered, function_names}` and calls `emit_event("tool_call_recovered_from_reasoning", payload)`
- [x] 4.2 Add `_emit_recovery_failed_event(response, match_count, sample)` helper that builds `{model, match_count, sample}` and calls `emit_event("tool_call_recovery_failed", payload)`

## 5. Tests

- [x] 5.1 Add `task-runner/tests/test_xml_tool_call_recovery.py` parser tests covering: (a) attribute-form function + key/value parameters, (b) element-form function + JSON arguments, (c) verbose parameter form, (d) multiple tool calls in one block, (e) malformed block skipped with sample returned, (f) no `<tool_call>` markup returns empty list
- [x] 5.2 Add `task-runner/tests/test_recovering_chat_completions.py` wrapper tests using a fake inner `chat.completions` that returns crafted `ChatCompletion` instances: (a) empty content + null tool_calls + XML reasoning → tool_calls populated, (b) non-empty content → passthrough, (c) non-empty tool_calls → passthrough, (d) empty content + null tool_calls + prose-only reasoning → passthrough, (e) detection happens with `reasoning_content` set as a `getattr` attribute (model objects vary across SDK versions)
- [x] 5.3 Add event-emission tests: assert `tool_call_recovered_from_reasoning` is emitted with the correct payload on successful rescue, and `tool_call_recovery_failed` on detected-but-unparseable markup
- [x] 5.4 Run the full test suite: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ task-runner/tests/ -v` and confirm no regressions

## 6. Local verification

- [x] 6.1 Build and start the stack: `docker compose -f testing/docker-compose.yml up --build`
- [x] 6.2 With LM Studio or a mock OpenAI server, return a crafted response that puts a Qwen-XML tool call in `reasoning_content` and confirm the task progresses past the would-be EmptyResponseError. (For local dev without LMStudio: a small Python script using `respx` mocking is acceptable.)
- [x] 6.3 Stop the stack: `docker compose -f testing/docker-compose.yml down`

## 7. PR and deploy

- [x] 7.1 Push branch, open PR with title `feat: recover tool calls emitted in reasoning_content as Qwen XML`
- [x] 7.2 Confirm CI builds image + Helm chart successfully (immutable tag check, no duplicates)
- [x] 7.3 Verify ArgoCD dry-run / staging apply succeeds against the new chart
- [ ] 7.4 Merge PR, delete local branch, pull `main`

## 8. Post-deploy verification

- [x] 8.1 Inspect Loki for `tool_call_recovered_from_reasoning` events post-deploy; confirm they appear for tasks that previously failed with empty-response
- [x] 8.2 Inspect Loki for `tool_call_recovery_failed` events; if any appear, capture the `sample` field and extend the parser to cover that dialect variant
- [x] 8.3 Re-run one of the historically-failing tasks (e.g. one that hit EmptyResponseError on qwen3.6) and confirm it now completes — task `892153ea-ebcf-4374-a559-a8d8330eaa72` previously failed on first qualifying turn, now runs 38 min through 72 LLM turns with 2 successful Qwen-XML rescues (Loki: `tool_call_recovered_from_reasoning` events at 11:19:08 and 11:19:39 UTC, model `qwen3.6-35b-a3b-ud-mlx`, function `bash`)

## 10. Streaming support (emergent — required for prod)

- [x] 10.1 Discover during prod testing that openai-agents calls `create(stream=True)` so the wrapper's `_post_process` was a silent no-op on `AsyncStream`
- [x] 10.2 Add `_wrap_streaming_response()` that returns an async generator: forwards all inner chunks, accumulates `delta.{content,tool_calls,reasoning_content}` across them, and on stream end runs the same detection criteria against the accumulated state
- [x] 10.3 Implement `_build_synthetic_tool_call_chunk()` constructing a single `ChatCompletionChunk` with `delta.role="assistant"`, `delta.tool_calls=[ChoiceDeltaToolCall(...)]`, and `finish_reason="tool_calls"` that the agents-SDK stream handler accumulates as a normal model-emitted tool call
- [x] 10.4 In `_RecoveringChatCompletions.create()`, branch on `kwargs.get("stream")` so the non-streaming path is unchanged and streaming responses are wrapped
- [x] 10.5 Add streaming tests covering: end-to-end recovery from chunked reasoning_content, passthrough when the model emitted tool_calls correctly, passthrough when reasoning_content has no XML markup, and the streaming dangling-closer / truncated-opener / mixed-block cases

## 11. Diagnostic visibility hardening

- [x] 11.1 Emit `tool_call_recovery_failed` whenever any `<tool_call>` opener was present but at least one block could not be parsed — covers mixed-recovered-and-failed responses where operators previously lost the diagnostic sample (Copilot review)
- [x] 11.2 Emit `tool_call_recovery_failed` for the truncated-opener case (opener present but `_TOOL_CALL_BLOCK_RE` matches zero closed blocks) using `reasoning_content.count("<tool_call>")` as `match_count` and a sample from the first opener onwards (Copilot review)
- [x] 11.3 Emit `tool_call_recovery_failed` for the dangling-closer case (`</tool_call>` present without an opener), with `match_count=0` and a sample window centred on the first `</tool_call>` — observed in prod on task 892153ea's final empty-response turn
- [x] 11.4 Make `_ARGUMENTS_JSON_RE` greedy and anchor to `</arguments>` so nested-object JSON like `{"server": {"host": "x"}, "retries": 3}` isn't truncated at the first `}` (Copilot review)
- [x] 11.5 Add regression tests for each of 11.1–11.4 in both streaming and non-streaming code paths

## 12. Archive

- [ ] 12.1 Run `/opsx:verify` to confirm implementation matches spec
- [ ] 12.2 Run `/opsx:archive` to finalize the change after merge
