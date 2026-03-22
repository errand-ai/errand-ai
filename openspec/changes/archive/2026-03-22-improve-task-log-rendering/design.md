# Design: Improve Task Log Rendering (Backend)

## Overview

Modify task-runner event emission to support turn-based log grouping and eliminate HTTP noise. All changes are in `task-runner/main.py`.

## Event Schema Changes

### New event: `llm_turn_start`

Emitted from `StreamEventEmitter.on_llm_start()`. Marks the beginning of each LLM turn.

```json
{"type": "llm_turn_start", "data": {"turn_id": "a1b2c3d4", "model": "claude-sonnet-4-5"}}
```

- `turn_id`: Short UUID (`str(uuid4())[:8]`) generated in `on_llm_start`, stored as `self._current_turn_id`
- `model`: Extracted from the model settings or environment variable

### New event: `mcp_connected`

Emitted once after all MCP servers are initialized, replacing the flood of raw httpx/logging lines.

```json
{"type": "mcp_connected", "data": {"servers": ["errand", "playwright", "hindsight", ...], "count": 8}}
```

### Modified events: add `turn_id`

All events emitted during streaming (`thinking`, `reasoning`, `tool_call`) include the current `turn_id`:

```json
{"type": "tool_call", "data": {"tool": "web_search", "args": {...}, "turn_id": "a1b2c3d4"}}
{"type": "thinking", "data": {"text": "...", "turn_id": "a1b2c3d4"}}
```

### Modified event: `tool_result` gains `duration_ms`

```json
{"type": "tool_result", "data": {"tool": "web_search", "output": "...", "length": 12736, "duration_ms": 1234, "turn_id": "a1b2c3d4"}}
```

## Implementation Details

### 1. Suppress httpx logging

Add after the existing `logging.basicConfig()` call (line 27):

```python
logging.getLogger("httpx").setLevel(logging.WARNING)
```

### 2. StreamEventEmitter state

Add instance state to `StreamEventEmitter`:

```python
class StreamEventEmitter(RunHooks):
    def __init__(self):
        self._current_turn_id: str | None = None
        self._tool_start_times: dict[str, float] = {}  # tool_name -> monotonic time
```

### 3. on_llm_start / on_llm_end

```python
async def on_llm_start(self, context, agent, *args, **kwargs):
    self._current_turn_id = str(uuid4())[:8]
    emit_event("llm_turn_start", {
        "turn_id": self._current_turn_id,
        "model": os.environ.get("MODEL", "unknown"),
    })

async def on_llm_end(self, context, agent, *args, **kwargs):
    pass  # No event needed; turn boundary is marked by next llm_turn_start
```

### 4. on_tool_start / on_tool_end

```python
async def on_tool_start(self, context, agent, tool):
    self._tool_start_times[tool.name] = time.monotonic()

async def on_tool_end(self, context, agent, tool, result):
    start = self._tool_start_times.pop(tool.name, None)
    duration_ms = int((time.monotonic() - start) * 1000) if start else None
    result_str = str(result)
    original_length = len(result_str)
    data = {
        "tool": tool.name,
        "output": _truncate(result_str),
        "length": original_length,
    }
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    if self._current_turn_id:
        data["turn_id"] = self._current_turn_id
    emit_event("tool_result", data)
```

### 5. Streaming loop modifications

In the `async for event in result.stream_events()` loop, add `turn_id` to emitted events:

```python
# For thinking events
emit_event("thinking", {"text": text, "turn_id": self._current_turn_id or ""})

# For tool_call events
emit_event("tool_call", {"tool": tool_name, "args": args, "turn_id": self._current_turn_id or ""})
```

Note: The streaming loop references the `StreamEventEmitter` instance passed to `Runner.run_streamed()`. We need to store the hooks instance in a variable so the streaming loop can access `hooks._current_turn_id`.

### 6. MCP connected event

After the MCP server initialization block (where servers are connected via `AsyncExitStack`), emit the summary:

```python
server_names = [name for name, _ in mcp_servers]
emit_event("mcp_connected", {"servers": server_names, "count": len(server_names)})
```

The existing raw log lines from httpx will be suppressed by step 1.

## Backward Compatibility

- `turn_id` is additive — existing frontend code ignores unknown fields in event data
- `duration_ms` is additive — existing `tool_result` handling doesn't reference it
- `llm_turn_start` and `mcp_connected` are new event types — existing frontend renders them as raw/unknown (harmless)
- No changes to stored `runner_logs` format — it remains raw stderr
