## Why

The MCP server exposes tools for creating tasks, checking individual task status, reading task output, and viewing task logs — but there is no way to list tasks. Users (and LLM agents) cannot discover what tasks exist without already knowing a task UUID. The REST API has `GET /api/tasks` which powers the Kanban board, but this is not available through MCP.

## What Changes

- Add a `list_tasks` MCP tool that returns tasks currently visible on the board (i.e. not deleted or archived)
- Support an optional `status` filter parameter to narrow results by task status (e.g. `scheduled`, `completed`, `running`)
- Return a concise summary per task: UUID, title, and status (no description, to keep responses lightweight)

## Capabilities

### New Capabilities

- `mcp-list-tasks`: MCP tool for listing tasks with optional status filtering

### Modified Capabilities

_(none)_

## Impact

- **Code**: `errand/mcp_server.py` — new `@mcp.tool()` function
- **Database**: Read-only queries against the `tasks` table (no schema changes)
- **API**: New MCP tool exposed via the Streamable HTTP MCP endpoint
- **Tests**: New test coverage for the MCP tool (parameterised by status filter)
