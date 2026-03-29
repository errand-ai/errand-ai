## Why

The task-runner uses a fragile text-based output contract: the LLM must emit raw JSON text (`{"status": "completed", "result": "..."}`) as its final message. This causes two systemic problems:

1. **Empty response failures** — 15 out of 22 task errors in a 4-day sample (Mar 25–29) are `EmptyResponseError`. The pattern is consistent: the model calls `retain()` (Hindsight memory), gets confirmation back, then produces an empty final turn — confusing "save to memory" with "deliver result". Each failure triggers a container restart + retry, wasting compute and risking duplicate side effects (e.g., tweets posted twice).

2. **Raw JSON display in frontend** — When the JSON wrapper leaks through the double-parse chain (task-runner serializes → Valkey callback → server re-parses with `extract_json`), the `output` column stores the full `{"status": "completed", "result": "..."}` wrapper instead of just the result content. The frontend then renders raw JSON instead of the markdown report.

Both problems stem from the same root cause: output delivery is a weak text convention while tool calls are a strong structured affordance. The LLM has explicit tools for everything else (`web_search`, `retain`, `discover_tools`) but must "just know" to produce a specific JSON format as plain text.

## What Changes

- Add `submit_result` as a native `@function_tool` in the task-runner, giving the LLM an explicit tool call for delivering its output — same affordance level as `retain` and other tools
- Update `OUTPUT_INSTRUCTIONS` in the system prompt to instruct models to call `submit_result()` instead of emitting raw JSON text
- Add an empty-response nudge: when the agent produces empty output after calling tools (especially `retain`), inject a follow-up message prompting it to call `submit_result`, avoiding a full container restart
- Update the callback payload to post the already-extracted `result` string rather than the full JSON wrapper, eliminating the server-side double-parse
- Keep text-based JSON output as a backward-compatible fallback during transition
- Add system prompt guidance reinforcing that `retain` saves to memory for future tasks, while `submit_result` delivers the result to the user

## Capabilities

### New Capabilities

- `submit-result-tool`: The `submit_result` function tool, its integration into the agent loop, the empty-response nudge mechanism, and updated output instructions

### Modified Capabilities

- `task-runner-agent`: Agent loop changes to prefer `submit_result` tool call output over text-based JSON parsing, and the empty-response nudge injection
- `task-result-callback`: Callback payload format changes from full JSON wrapper to extracted result fields

## Impact

- **task-runner/main.py**: New `submit_result` function_tool, updated agent loop output extraction, empty-response nudge logic, updated `OUTPUT_INSTRUCTIONS`
- **task-runner/tool_registry.py**: Possibly extend `ToolVisibilityContext` to carry submitted result state
- **errand/task_manager.py**: Server-side parsing may simplify — callback now posts clean data, reducing reliance on `extract_json` heuristics
- **Backward compatibility**: Text-based JSON output remains as fallback — existing task-runner containers continue to work during rollout
- **No database changes**: The `output` column format is unchanged (stores the result string)
- **No frontend changes**: The frontend already expects a plain markdown string in `output` — fixing the pipeline means it gets one consistently
