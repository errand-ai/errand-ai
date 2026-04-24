## Why

The Paperclip errand adapter needs MCP tools and API capabilities that don't currently exist in errand: creating tasks with a specific profile, listing available profiles, and retrieving structured task status. These enhancements are independently useful for any MCP consumer but are prerequisites for the Paperclip integration.

## What Changes

- Add `profile` parameter to `new_task` MCP tool — allows immediate task creation with a named profile, bypassing the 15-second scheduler promotion delay of `schedule_task`
- Add `title` parameter to `new_task` MCP tool — allows callers to set the task title directly, bypassing the LLM summariser. When set, the `description` parameter is stored verbatim as the task description
- Capture `X-Client-Id` HTTP header in MCP tool handlers — use the value to set `created_by` on tasks instead of the hard-coded `"mcp"`, enabling identification of tasks by source (e.g. `"paperclip"`)
- Skip `review` state for external client tasks — when a completed task has `needs_input` status and `created_by` matches an external client (e.g. `"paperclip"`), move it directly to `completed` instead of `review`, since clarification is handled by the external client
- Accept per-task encrypted environment variables via `new_task` and `schedule_task` — allows MCP clients to inject sensitive values (e.g. per-run JWT tokens for callback auth) into the task-runner container at execution time
- Expose skills management via MCP tools (`list_skills`, `upsert_skill`, `delete_skill`) — allows the Paperclip adapter to sync skill definitions into errand's skills system for injection into the task-runner
- Add `list_task_profiles` MCP tool — returns profile names, descriptions, and models for external consumers (currently profiles are only listable via the admin-only REST endpoint)
- Enhance `task_status` MCP tool to return structured JSON instead of plaintext — enables reliable status parsing by adapters and other programmatic consumers
- Add API key authentication option to the task log streaming REST endpoint (`GET /api/tasks/{id}/logs/stream`) — currently requires OIDC JWT, but MCP consumers (like the Paperclip adapter) only have an API key

## Capabilities

### New Capabilities
- `mcp-profile-tools`: MCP tools for listing task profiles and creating tasks with a specified profile and/or explicit title
- `mcp-skills-tools`: MCP tools for listing, upserting, and deleting skills
- `task-env-vars`: Per-task encrypted environment variables injected into the task-runner container

### Modified Capabilities
- `mcp-server`: Enhanced `task_status` to return structured JSON; API key auth for log streaming endpoint

## Impact

- `errand/mcp_server.py` — modify `new_task`, `schedule_task`, `task_status`; add `list_task_profiles`, `list_skills`, `upsert_skill`, `delete_skill`; capture `X-Client-Id` header via MCP `Context`
- `errand/task_manager.py` — add `created_by` to `DequeuedTask`; modify task wrap-up to skip `review` state for external client tasks; decrypt and inject per-task env vars at runtime
- `errand/models.py` — add `encrypted_env` column to Task model
- `errand/main.py` — add API key auth option to log streaming endpoint
- `errand/alembic/` — migration for `encrypted_env` column on tasks table
- No breaking changes to existing MCP tool interfaces
