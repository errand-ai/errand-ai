## MODIFIED Requirements

### Requirement: MCP server mounted at /mcp

The backend SHALL mount an MCP Streamable HTTP server at the `/mcp` path using the official MCP Python SDK (`mcp` package). The server SHALL use `MCPServer` from `mcp.server.mcpserver` and mount `streamable_http_app()` onto the FastAPI application with `streamable_http_path="/"` so the endpoint is accessible at `/mcp`. The MCP session manager SHALL be started and stopped via the application's lifespan context manager. The server SHALL use `stateless_http=True` and `json_response=True`.

#### Scenario: MCP endpoint responds to POST

- **WHEN** a client sends a valid MCP JSON-RPC request to `POST /mcp`
- **THEN** the server returns a valid MCP JSON-RPC response

#### Scenario: MCP endpoint listed in tool discovery

- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** the response includes the tools: `new_task`, `task_status`, `task_output`, `task_logs`, `schedule_task`, `post_tweet`, `web_search`, `read_url`, `list_emails`, `read_email`, `list_email_folders`, `move_email`, `send_email`, `forward_email`

The `post_tweet` tool SHALL delegate to the platform registry's `TwitterPlatform.post()` method instead of calling the Tweepy API directly. The tool's interface (parameters, return format) SHALL remain unchanged.

#### Scenario: post_tweet delegates to platform abstraction

- **WHEN** a client calls `post_tweet` with a valid message
- **THEN** the MCP tool calls `registry.get("twitter").post(message)` and returns the result

#### Scenario: post_tweet with no platform configured

- **WHEN** a client calls `post_tweet` and the Twitter platform has no credentials (DB or env var)
- **THEN** the tool returns "Error: Twitter API credentials not configured"
