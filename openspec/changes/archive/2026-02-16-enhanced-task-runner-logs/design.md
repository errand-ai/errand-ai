## Context

The live-task-logs change (in progress) established the infrastructure for streaming task runner stderr to the frontend: per-task Valkey pub/sub channels (`task_logs:{task_id}`), a dedicated WebSocket endpoint (`/api/ws/tasks/{task_id}/logs`), and a `TaskLogModal` component with terminal-style rendering. Currently the content streamed is raw stderr log lines — timestamped messages like `TOOL_CALL [execute_command]` and `TOOL_RESULT [execute_command] (342 chars): ...`.

The task runner uses the OpenAI Agents SDK (v0.8.4) with `Runner.run()` (blocking), a `ToolCallLogger` RunHooks subclass that only hooks `on_tool_start`/`on_tool_end`, and manual JSON extraction from the agent's final output. The agent is instructed via an "overarching prompt" to output JSON matching `TaskRunnerOutput`, and `extract_json()` implements three fallback strategies to find valid JSON in the raw LLM response.

The models in use are Claude Haiku and Sonnet via LiteLLM's OpenAI-compatible proxy. LiteLLM supports the OpenAI Responses API for Anthropic models and translates `reasoning_effort` to Anthropic's thinking parameter, though full mapping is currently documented for Opus 4.5 only.

## Goals / Non-Goals

**Goals:**

- Replace opaque stderr log lines with structured, typed events that describe what the agent is doing in human-readable terms
- Surface the agent's intermediate text output (its "thinking aloud" between tool calls) to the user
- Attempt reasoning/thinking summaries via `ModelSettings(reasoning=...)` with graceful fallback for unsupported models
- Simplify structured output handling with prompt-based `OUTPUT_INSTRUCTIONS` and JSON parsing with fallback (SDK `output_type` was evaluated but doesn't work reliably through LiteLLM)
- Render structured events in the frontend with rich formatting: collapsible tool calls, syntax-highlighted output, distinct thinking/reasoning sections
- Maintain the existing streaming infrastructure (Valkey pub/sub, WebSocket endpoint) — only change the message content format

**Non-Goals:**

- Multi-agent handoffs (single agent is sufficient for current use cases)
- Guardrails (input/output validation beyond structured output)
- Session/conversation memory across task runs
- OpenAI tracing integration (disabled in sandboxed containers, no tracing endpoint)
- Persisting individual structured events in the database (full `runner_logs` stored post-execution as before, just in the new format)
- Token-by-token streaming to the frontend (events are emitted at the semantic level: complete tool calls, complete messages)

## Decisions

### 1. Use `Runner.run_streamed()` with event loop instead of blocking `Runner.run()`

**Decision**: Switch to `Runner.run_streamed()` and iterate `result.stream_events()` to emit structured events in real-time.

**Alternatives considered**:
- *Keep `Runner.run()` with enhanced RunHooks*: Would give lifecycle callbacks but not true streaming — the entire run must complete before we can process results. RunHooks write to stderr which is already streamed, but the hooks fire synchronously during the run, so they actually work for real-time output. However, `run_streamed()` gives us access to the full `RunItemStreamEvent` including message content, which hooks don't expose.
- *Use RunHooks only for event emission*: Simpler change but hooks don't expose model text output (the `on_llm_end` response object doesn't directly give us the message text in a clean way for all model types). Streaming events give us `MessageOutputItem` content directly.

**Rationale**: `run_streamed()` is the idiomatic way to get real-time events from the SDK. It provides `RunItemStreamEvent` objects that cleanly separate tool calls, tool results, message outputs, and reasoning items. The event loop replaces both the blocking run call and the hooks-based logging.

### 2. Structured event protocol on stderr

**Decision**: The task runner emits one JSON object per line on stderr, each with a `type` field and a `data` field. Event types:

| Type | Data | Description |
|------|------|-------------|
| `agent_start` | `{"agent": "TaskRunner"}` | Agent loop begins |
| `thinking` | `{"text": "..."}` | Model's intermediate text output between tool calls |
| `reasoning` | `{"text": "..."}` | Reasoning/thinking summary (from ReasoningItem, if model supports it) |
| `tool_call` | `{"tool": "name", "args": {...}}` | Tool invocation starting |
| `tool_result` | `{"tool": "name", "output": "...", "length": N}` | Tool returned a result |
| `agent_end` | `{"output": {...}}` | Agent produced final output |
| `error` | `{"message": "..."}` | Error during execution |

Each line is `json.dumps({"type": "...", "data": {...}})`. The task runner's final structured output (TaskRunnerOutput) is still written to stdout as before.

**Alternatives considered**:
- *Mixed format (some plain text, some JSON)*: Would require the worker to detect format per-line. Fragile.
- *Single log level with embedded structure*: E.g., `INFO EVENT {"type": "tool_call", ...}`. Adds a parsing step for no benefit.

**Rationale**: Pure JSON on stderr is simple to parse in the worker, carries type information, and is forward-compatible (new event types can be added without breaking parsers). The worker already reads stderr line-by-line.

### 3. Prompt-based structured output with JSON parsing fallback

**Decision**: Append `OUTPUT_INSTRUCTIONS` to the system prompt instructing the agent to respond with JSON matching the `TaskRunnerOutput` schema. The task runner parses `result.final_output` as JSON and validates against the schema, with a fallback wrapper for unparseable output. The worker retains `extract_json()` to handle any preamble text or code fences in stdout.

**Alternatives considered**:
- *SDK-native `output_type=TaskRunnerOutput`*: Attempted during implementation, but does not work reliably through the LiteLLM proxy for all models — the proxy's translation of SDK structured output enforcement is inconsistent across providers.
- *Remove `extract_json()` entirely*: Risky since prompt-based enforcement is best-effort — the agent may occasionally wrap output in code fences or add preamble text.

**Rationale**: The prompt-based approach works reliably across all models via LiteLLM. Keeping `extract_json()` in the worker provides defence-in-depth for edge cases where the agent doesn't produce clean JSON. The `OUTPUT_INSTRUCTIONS` prompt is minimal (a few lines) so token overhead is negligible.

### 4. Reasoning with graceful fallback via `ModelSettings`

**Decision**: Configure the agent with `ModelSettings(reasoning=Reasoning(effort="medium", generate_summary="auto"))`. If the model/provider doesn't support reasoning, the SDK either ignores the parameter or the LiteLLM proxy drops it — either way, the agent still works. When `ReasoningItem` objects appear in the streamed events, emit them as `reasoning` events. When they don't appear (model doesn't support it), the log simply doesn't show reasoning sections.

**Alternatives considered**:
- *Don't attempt reasoning, only use intermediate model text*: Simpler, but leaves capability on the table for models that support it.
- *Detect model capability at runtime and conditionally enable*: Over-engineered — the fallback behavior (parameter ignored) is already graceful.

**Rationale**: The cost of attempting reasoning on an unsupported model is zero (parameter ignored). The benefit on supported models is significant (users see the model's structured thinking). No conditional logic needed — just emit `reasoning` events when `ReasoningItem` appears in the stream.

### 5. Worker publishes typed events to Valkey (format change)

**Decision**: Change the Valkey message format on `task_logs:{task_id}` from `{"event": "task_log", "line": "..."}` to `{"event": "task_event", "type": "...", "data": {...}}`. The `task_log_end` sentinel remains as `{"event": "task_log_end"}`.

**Alternatives considered**:
- *Wrap structured events inside the existing `{"event": "task_log", "line": "..."}`*: Would require double-parsing on the frontend. The frontend would receive a `task_log` event, then parse `line` as JSON to get the structured event.

**Rationale**: Since backwards compatibility is not required, we use the cleaner format. The worker parses each stderr line (which is already JSON) and re-publishes with the `event: "task_event"` wrapper. The frontend handles `task_event` messages with their `type` and `data` fields directly.

### 6. Rich frontend rendering with collapsible sections

**Decision**: Rewrite `TaskLogModal` to render structured events with:
- **Thinking/reasoning**: Styled as a distinct block with a muted/italic appearance, collapsible by default when long
- **Tool calls**: Collapsible card showing tool name as header, with args and result expandable. Tool name is always visible. Args shown as formatted JSON. Result shown with length indicator; full content expandable.
- **Agent messages**: Rendered as markdown (using existing `marked` + `DOMPurify` pipeline from `TaskOutputModal`)
- **Errors**: Red-styled alert block
- **Status indicators**: Spinner for in-progress tool calls, checkmark for completed ones

**Alternatives considered**:
- *Minimal text rendering with icons*: Lower effort but doesn't justify the protocol change. If we're structuring the data, we should render it richly.

**Rationale**: The structured event protocol exists precisely to enable this rich rendering. Users can scan tool call headers without reading verbose output, expand details when investigating, and see the agent's reasoning flow clearly.

## Risks / Trade-offs

**[Reasoning parameter may be silently ignored]** → Accepted. The fallback is simply not showing reasoning sections. The `thinking` events (intermediate model text) still provide insight into the agent's process even without formal reasoning.

**[Prompt-based structured output is best-effort]** → Mitigation: The worker's `extract_json()` handles common failure modes (code fences, preamble text, brace extraction). If all strategies fail, the task is retried with exponential backoff.

**[Streaming loop may behave differently from blocking run for edge cases]** → Mitigation: `run_streamed()` follows the same agent loop as `run()` (reason → act → observe → repeat). The only difference is event delivery timing. Test with the same prompts and tools to verify equivalent output.

**[Existing `runner_logs` data in the database is in the old format]** → Accepted trade-off. User has agreed to clear existing records. The `TaskOutputModal` (which shows post-completion output) continues to render markdown from the `output` field which is unaffected.

**[Large tool results in structured events could be verbose]** → Mitigation: Truncate tool result `output` in events to the existing 500-char limit. The full result is available in the agent's context but not streamed to the frontend.
