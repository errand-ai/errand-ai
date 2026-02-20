## Why

The MCP server currently exposes `new_task`, `task_status`, `task_output`, and `post_tweet` tools. Two gaps limit its usefulness for AI agents: (1) there is no way to retrieve task-runner execution logs, making it hard to debug failed or unexpected task results, and (2) creating scheduled or repeating tasks requires embedding timing instructions in the description and relying on LLM categorisation, which is unreliable and opaque to the caller.

## What Changes

- Add a `task_logs` MCP tool that retrieves the stored `runner_logs` field for a given task UUID
- Add a `schedule_task` MCP tool that accepts explicit scheduling parameters (`execute_at`, `repeat_interval`, `repeat_until`) alongside the task description, bypassing LLM category detection for scheduling
- Update the MCP tool discovery response to include the two new tools

## Capabilities

### New Capabilities
- `mcp-task-logs`: MCP tool to retrieve task-runner execution logs by task UUID
- `mcp-schedule-task`: MCP tool to create scheduled/repeating tasks with explicit timing parameters

### Modified Capabilities
- `mcp-server-endpoint`: Tool discovery response must include the two new tools (`task_logs`, `schedule_task`)

## Impact

- **Code**: `backend/mcp_server.py` — two new tool functions added
- **APIs**: MCP `tools/list` response gains two entries; no REST API changes
- **Tests**: New backend test cases for both tools
- **Specs**: New specs for each tool, delta spec for `mcp-server-endpoint` tool discovery
