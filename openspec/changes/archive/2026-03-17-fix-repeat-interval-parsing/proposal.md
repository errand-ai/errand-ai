## Why

The `parse_interval` function only accepts compact duration format (`15m`, `1h`, `1d`, `1w`) but LLM agents using the `schedule_task` MCP tool naturally produce human-readable formats like `7 days`, `2 hours`, `weekly`. This causes repeating tasks to silently fail rescheduling — the task completes but is never cloned, with only a warning log message as evidence. Additionally, the `schedule_task` tool description doesn't specify the expected format, leaving LLMs to guess.

## What Changes

- Make `parse_interval` normalise human-readable duration strings (e.g. `7 days` → `7d`, `weekly` → `1w`) before applying the compact format regex
- Add explicit format documentation to the `schedule_task` MCP tool's `repeat_interval` parameter description
- Add input validation in `schedule_task` that calls `parse_interval` before storing, returning an immediate error to the caller if the interval is unparseable

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `repeating-task-rescheduling`: `parse_interval` must normalise human-readable durations before parsing
- `mcp-schedule-task`: Tool description must document accepted `repeat_interval` formats; tool must validate `repeat_interval` before storing

## Impact

- **Code**: `errand/task_manager.py` (`parse_interval`), `errand/mcp_server.py` (`schedule_task` tool description + validation)
- **Tests**: `errand/tests/test_worker.py` (new `parse_interval` test cases), existing errand tests
- **Breaking changes**: None — all existing compact formats still work, new formats are additive
