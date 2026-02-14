## MODIFIED Requirements

### Requirement: MCP endpoint listed in tool discovery
- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** the response includes the tools: `new_task`, `task_status`, `task_output`, `list_skills`, `get_skill`, `post_tweet`
