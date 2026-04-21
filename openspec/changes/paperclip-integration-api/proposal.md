## Why

The Paperclip errand adapter needs MCP tools and API capabilities that don't currently exist in errand: creating tasks with a specific profile, listing available profiles, and retrieving structured task status. These enhancements are independently useful for any MCP consumer but are prerequisites for the Paperclip integration.

## What Changes

- Add `profile` parameter to `new_task` MCP tool — allows immediate task creation with a named profile, bypassing the 15-second scheduler promotion delay of `schedule_task`
- Add `title` parameter to `new_task` MCP tool — allows callers to set the task title directly, bypassing the LLM summariser. When set, the `description` parameter is stored verbatim as the task description
- Add `list_task_profiles` MCP tool — returns profile names, descriptions, and models for external consumers (currently profiles are only listable via the admin-only REST endpoint)
- Enhance `task_status` MCP tool to return structured JSON instead of plaintext — enables reliable status parsing by adapters and other programmatic consumers
- Add API key authentication option to the task log streaming REST endpoint (`GET /api/tasks/{id}/logs/stream`) — currently requires OIDC JWT, but MCP consumers (like the Paperclip adapter) only have an API key

## Capabilities

### New Capabilities
- `mcp-profile-tools`: MCP tools for listing task profiles and creating tasks with a specified profile and/or explicit title

### Modified Capabilities
- `mcp-server`: Enhanced `task_status` to return structured JSON; API key auth for log streaming endpoint

## Impact

- `errand/mcp_server.py` — modify `new_task`, `task_status`; add `list_task_profiles`
- `errand/main.py` — add API key auth option to log streaming endpoint
- No database changes
- No breaking changes to existing MCP tool interfaces (task_status gains a new optional `format` parameter, defaulting to current plaintext behaviour)
