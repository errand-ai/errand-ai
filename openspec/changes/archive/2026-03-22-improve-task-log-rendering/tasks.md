# Tasks: Improve Task Log Rendering (Backend)

## Suppress httpx logging

- [x] Add `logging.getLogger("httpx").setLevel(logging.WARNING)` after `logging.basicConfig()` in `task-runner/main.py`

## Add turn tracking to StreamEventEmitter

- [x] Add `import time` and `from uuid import uuid4` to imports in `task-runner/main.py`
- [x] Add `__init__` to `StreamEventEmitter` with `_current_turn_id: str | None = None` and `_tool_start_times: dict[str, float] = {}`
- [x] Implement `on_llm_start`: generate `turn_id`, store in `self._current_turn_id`, emit `llm_turn_start` event with `turn_id` and model name from `MODEL` env var
- [x] Implement `on_tool_start`: record `time.monotonic()` in `self._tool_start_times[tool.name]`
- [x] Modify `on_tool_end`: calculate `duration_ms` from stored start time, include `duration_ms` and `turn_id` in `tool_result` event
- [x] Store hooks instance in a variable before passing to `Runner.run_streamed()` so the streaming loop can access `hooks._current_turn_id`
- [x] Add `turn_id` to `thinking` events emitted in the streaming loop
- [x] Add `turn_id` to `reasoning` events emitted in the streaming loop
- [x] Add `turn_id` to `tool_call` events emitted in the streaming loop

## Emit MCP connected summary event

- [x] After MCP server initialization loop completes, emit `mcp_connected` event with server names list and count

## Tests

- [x] Add test: httpx logger level is WARNING after module initialization
- [x] Add test: `on_llm_start` emits `llm_turn_start` event with `turn_id` and `model`
- [x] Add test: `on_tool_start` records start time
- [x] Add test: `on_tool_end` emits `tool_result` with `duration_ms` and `turn_id`
- [x] Add test: streaming loop events include `turn_id` (thinking, reasoning, tool_call)
- [x] Add test: `mcp_connected` event emitted with correct server names and count