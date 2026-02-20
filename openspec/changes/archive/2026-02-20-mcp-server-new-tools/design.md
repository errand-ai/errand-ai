## Context

The MCP server (`backend/mcp_server.py`) currently exposes four tools: `new_task`, `task_status`, `task_output`, and `post_tweet`. The Task model already has `runner_logs` (Text) and scheduling fields (`execute_at`, `repeat_interval`, `repeat_until`) — these are set by the worker and LLM respectively but not directly exposed through the MCP interface.

The `new_task` tool delegates to `generate_title()` in `backend/llm.py`, which returns an `LLMResult` containing `title`, `category`, and timing fields. For `schedule_task`, we need title generation but want the caller to control scheduling rather than the LLM.

## Goals / Non-Goals

**Goals:**
- Expose task-runner logs via a new `task_logs` MCP tool
- Allow MCP clients to create scheduled/repeating tasks with explicit timing parameters via `schedule_task`
- Keep the implementation simple — both tools follow existing patterns in `mcp_server.py`

**Non-Goals:**
- Modifying the existing `new_task` tool behaviour
- Adding log streaming (this retrieves stored logs only)
- Validating `repeat_interval` format beyond basic non-empty string checks — the scheduler already handles parsing

## Decisions

### task_logs returns raw runner_logs text
The `runner_logs` field is stored as a Text column. The tool returns this as-is, consistent with how `task_output` returns the `output` field. No parsing or formatting is applied.

**Alternative considered**: Returning structured JSON with metadata (status, timestamps). Rejected — adds complexity without benefit since the caller can use `task_status` separately.

### schedule_task uses generate_title() but ignores category
The `schedule_task` tool calls `generate_title()` for title generation (same as `new_task`) but discards the returned `category` field, since the category is deterministic from the parameters: `"repeating"` if `repeat_interval` is provided, otherwise `"scheduled"`. This avoids duplicating the LLM prompt while keeping scheduling logic explicit.

**Alternative considered**: A separate LLM prompt that only generates titles (no category). Rejected — `generate_title()` already works and the extra fields in the response are simply ignored.

### schedule_task requires execute_at
The `execute_at` parameter is required for `schedule_task` — a scheduled task without a start time doesn't make sense. `repeat_interval` and `repeat_until` are optional (only needed for repeating tasks).

### Both tools follow existing auth and session patterns
Both new tools use `@mcp.tool()` decorator, `async_session()` context manager, and the same UUID lookup pattern as `task_status`/`task_output`. No new infrastructure needed.

## Risks / Trade-offs

- **[Large logs]** `runner_logs` could be very large for long-running tasks → The MCP protocol handles large text responses; no truncation needed at this layer. Clients can handle display.
- **[Invalid datetime strings]** Callers may pass malformed `execute_at`/`repeat_until` values → We parse with `datetime.fromisoformat()` and return a clear error on failure.
