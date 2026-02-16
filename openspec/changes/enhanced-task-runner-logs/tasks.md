## 1. Task Runner: Structured Event Emission

- [x] 1.1 Create `emit_event(type, data)` helper function that writes a single-line JSON object (`{"type": "...", "data": {...}}`) to stderr
- [x] 1.2 Replace `ToolCallLogger` with `StreamEventEmitter` RunHooks class implementing `on_agent_start`, `on_tool_start`, `on_tool_end`, `on_agent_end` using `emit_event`, and `on_llm_start`/`on_llm_end` at DEBUG level
- [x] 1.3 Switch from `Runner.run()` to `Runner.run_streamed()` with event loop iterating `result.stream_events()`, emitting `thinking` events for `MessageOutputItem` and `reasoning` events for `ReasoningItem`
- [x] 1.4 Add `ModelSettings(reasoning=Reasoning(effort=..., generate_summary="auto"))` with `REASONING_EFFORT` env var (default `medium`)

## 2. Task Runner: SDK Structured Output

- [x] 2.1 Add `output_type=TaskRunnerOutput` to Agent configuration
- [x] 2.2 Remove `OVERARCHING_PROMPT` constant and the combined instructions logic that appends it to the system prompt
- [x] 2.3 Remove `extract_json()` function and its three-strategy parsing logic
- [x] 2.4 Update `main()` to read `result.final_output` directly as a `TaskRunnerOutput` (serialise with `model_dump_json()`) with fallback wrapper for SDK structured output failures
- [x] 2.5 Emit `error` event to stderr when agent execution fails, before exiting with code 1

## 3. Task Runner Tests

- [x] 3.1 Update `test_main.py`: remove `extract_json` tests, add tests for `emit_event` helper
- [x] 3.2 Add tests for `StreamEventEmitter` hook callbacks verifying correct JSON event structure on stderr
- [x] 3.3 Add test for `REASONING_EFFORT` env var parsing and default value
- [x] 3.4 Add test verifying the agent is configured with `output_type=TaskRunnerOutput`

## 4. Worker: Structured Event Publishing

- [x] 4.1 Update `process_task_in_container` stderr streaming loop to parse each line as JSON and publish structured `{"event": "task_event", "type": "...", "data": {...}}` messages to Valkey
- [x] 4.2 Add fallback for non-JSON stderr lines: publish as `{"event": "task_event", "type": "raw", "data": {"line": "..."}}`
- [x] 4.3 Verify `task_log_end` sentinel is still published after container exit (no change needed, just verify)

## 5. Worker Tests

- [x] 5.1 Add test for structured event parsing from stderr line to Valkey message
- [x] 5.2 Add test for non-JSON stderr line fallback to raw event
- [x] 5.3 Verify existing worker tests still pass with updated Valkey message format

## 6. Frontend: Rich Log Viewer

- [x] 6.1 Rewrite `TaskLogModal.vue` to handle `task_event` messages (with `type` and `data` fields) instead of `task_log` messages (with `line` field)
- [x] 6.2 Implement `thinking` event renderer: italic muted-colour block, collapsible when exceeding 3 lines
- [x] 6.3 Implement `reasoning` event renderer: styled block with left border accent, collapsible when exceeding 3 lines
- [x] 6.4 Implement `tool_call` event renderer: collapsible card with tool name header, JSON-formatted args body, collapsed by default
- [x] 6.5 Implement `tool_result` event renderer: appended to preceding tool_call card, showing output length, monospace font, collapsible when exceeding 3 lines
- [x] 6.6 Implement `agent_start`, `agent_end`, and `error` event renderers (status line, status line, red alert block respectively)
- [x] 6.7 Implement `raw` event renderer: plain monospace text line
- [x] 6.8 Maintain auto-scroll behaviour with manual scroll detection (scroll to bottom unless user has scrolled up)

## 7. Frontend Tests

- [x] 7.1 Update `TaskLogModal.test.ts` to test structured event rendering for each event type
- [x] 7.2 Add test for collapsible behaviour on long thinking/reasoning/tool_result content
- [x] 7.3 Add test for tool_result appending to preceding tool_call card
- [x] 7.4 Add test for auto-scroll / manual scroll detection
