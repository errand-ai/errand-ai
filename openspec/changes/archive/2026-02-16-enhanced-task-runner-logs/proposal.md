## Why

The live-task-logs change streams raw stderr lines from the task runner to the frontend, but the content is opaque — timestamped log lines like `TOOL_CALL [execute_command]` that require developer-level knowledge to interpret. The task runner agent generates rich intermediate output (model text between tool calls, tool arguments, tool results, reasoning) that is discarded. By switching to the OpenAI Agents SDK's streaming API and structured output handling, we can surface what the agent is actually doing in a way users can understand, while also simplifying the task runner codebase.

## What Changes

- **BREAKING**: Replace raw stderr log streaming with structured JSON events from the task runner. Each event has a type (`agent_thinking`, `tool_call`, `tool_result`, `agent_message`, `reasoning`, `complete`, `error`) and typed payload. Existing `runner_logs` content becomes the new structured format.
- Switch task runner from `Runner.run()` to `Runner.run_streamed()` to emit events in real-time as the agent loop progresses
- Replace manual `extract_json()` output parsing with SDK-native `output_type=TaskRunnerOutput` on the Agent, removing ~40 lines of parsing code and the overarching JSON instruction prompt
- Expand `RunHooks` from tool-only logging (`on_tool_start`/`on_tool_end`) to full lifecycle logging (`on_llm_start`/`on_llm_end`/`on_agent_start`/`on_agent_end`)
- Enable `ModelSettings(reasoning=Reasoning(...))` with graceful fallback for models that support extended thinking/reasoning summaries
- Replace the plain-text terminal log viewer in `TaskLogModal` with a rich structured event renderer (collapsible tool calls, syntax-highlighted output, thinking/reasoning bubbles, distinct message sections)
- Worker parses structured events from task runner stderr and publishes them to Valkey with their type information preserved

## Capabilities

### New Capabilities
- `structured-task-events`: Defines the structured event protocol between task runner, worker, and frontend — event types, JSON schemas, and rendering rules for the rich log viewer

### Modified Capabilities
- `task-runner-agent`: Replace `Runner.run()` with `Runner.run_streamed()`, use SDK `output_type` for structured output instead of manual JSON extraction, add `ModelSettings` with optional reasoning support
- `task-runner-tool-call-logging`: Expand `RunHooks` to full agent lifecycle (LLM start/end, agent start/end) and change output format from plain log lines to structured JSON events on stderr
- `live-task-log-streaming`: The Valkey message format changes from `{"event": "task_log", "line": "..."}` to typed event objects like `{"event": "task_event", "type": "tool_call", "data": {...}}`

## Impact

- **task-runner/main.py**: Major refactor — streaming agent loop, structured event emission, SDK output_type, removal of extract_json and overarching prompt, enhanced RunHooks, ModelSettings with reasoning
- **task-runner/test_main.py**: Tests updated for new streaming behavior and structured output; extract_json tests removed
- **task-runner/requirements.txt**: Pin openai-agents version that supports all used features (>=0.8.0)
- **backend/worker.py**: `process_task_in_container` parses structured events from stderr instead of raw lines; Valkey message format changes
- **backend/tests/test_worker.py**: Tests for new event parsing
- **frontend/src/components/TaskLogModal.vue**: Complete rewrite from terminal-style text viewer to rich structured event renderer with collapsible sections, syntax highlighting, and reasoning display
- **frontend/src/components/__tests__/TaskLogModal.test.ts**: Tests for structured event rendering
- **Database**: Existing task `runner_logs` and `output` fields may contain old-format data — acceptable to clear since we are not maintaining backwards compatibility
