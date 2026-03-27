## Context

The MCP server (`errand/mcp_server.py`) exposes task tools (`new_task`, `task_status`, `task_output`, `task_logs`, `schedule_task`) but has no way to list tasks. The REST API (`GET /api/tasks` in `main.py`) already provides this for the frontend Kanban board — it returns all non-deleted, non-archived tasks ordered by position/created_at, with completed tasks sorted by updated_at descending.

All existing MCP tools follow the same pattern: `@mcp.tool()` async functions that open an `async_session()`, query the `Task` model, and return plain text strings (or JSON where structured data is needed).

## Goals / Non-Goals

**Goals:**
- Expose task listing through the MCP interface so LLM agents can discover existing tasks
- Support optional status filtering to narrow results
- Return concise, structured JSON output (uuid, title, status)

**Non-Goals:**
- Pagination (task volumes are low enough that full listing is practical)
- Sorting options (use the same ordering as the board API)
- Returning task descriptions or full details (use `task_status` for that)

## Decisions

1. **Return JSON, not plain text.** Other MCP tools return formatted strings, but a list of tasks is better served as JSON for machine consumption. This matches the `schedule_task` tool which already returns structured data.

2. **Reuse the board query logic.** The default (no filter) should match what the board shows: all tasks except deleted and archived. When a status filter is provided, query only that status.

3. **Single optional `status` parameter.** Accepts any valid task status string. Invalid values return an error message listing valid options. Valid board-visible statuses: `scheduled`, `pending`, `running`, `review`, `completed`.

4. **Ordering.** Match the board: active tasks by position ASC then created_at ASC; completed tasks by updated_at DESC. When filtering by a specific status, use the appropriate ordering for that status.

## Risks / Trade-offs

- **No pagination**: If task volume grows significantly, the response could become large. Acceptable for now given typical usage patterns; can add `limit` parameter later if needed.
- **JSON vs text**: Departing from the plain-text pattern of `task_status`/`task_output`, but structured output is more useful for list data and consistent with how LLMs parse tool responses.
