## Why

External AI coding tools (Claude Code, GitHub Copilot, Cursor) support MCP servers as tool providers. Exposing the content manager's task operations via an MCP endpoint would allow developers to create tasks, check status, and retrieve output directly from their IDE without switching to the web UI.

## What Changes

- Add an MCP server endpoint at `/mcp` on the backend using the MCP Python SDK with Streamable HTTP transport
- Implement API key authentication for the `/mcp` endpoint (separate from existing OIDC/JWT auth) — the key is passed in the `Authorization` header as a Bearer token
- Auto-generate an API key on backend startup if one does not already exist, stored in the `settings` table
- Expose three MCP tools: `new_task` (create a task, return UUID), `task_status` (get task state by UUID), `task_output` (get completed task output by UUID)
- Add an "MCP Server" section to the settings page displaying the API key and a copyable example MCP server configuration block suitable for claude-code and copilot
- Add a "Regenerate API Key" button to the settings page

## Capabilities

### New Capabilities
- `mcp-server-endpoint`: The backend MCP server implementation — `/mcp` route, API key auth middleware, and the three MCP tools (new_task, task_status, task_output)

### Modified Capabilities
- `admin-settings-api`: Add `POST /api/settings/regenerate-mcp-key` endpoint for regenerating the API key, and include the API key in the settings GET response
- `admin-settings-ui`: Add "MCP Server" section to the settings page showing the API key (masked with reveal toggle), copyable example configuration, and regenerate button

## Impact

- **Backend**: New MCP route module, new dependency on `mcp` Python SDK, API key generation utility, startup hook modification
- **Frontend**: New settings section component for MCP server configuration display
- **Database**: API key stored as a setting in existing `settings` table (no migration needed)
- **Helm/Docker**: No changes needed — the `/mcp` endpoint runs on the same backend service
- **Dependencies**: `mcp` Python SDK added to `requirements.txt`
