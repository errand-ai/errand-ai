## MODIFIED Requirements

### Requirement: MCP server mounted at /mcp

The backend SHALL mount an MCP Streamable HTTP server at the `/mcp` path using the official MCP Python SDK (`mcp` package), version 2.x. The server SHALL use `MCPServer` from `mcp.server.mcpserver`, constructed with its identity and authentication parameters only. Transport configuration SHALL be passed to `streamable_http_app()`, which v2 requires and the constructor no longer accepts: `streamable_http_path="/"` so the endpoint is reachable at `/mcp`, `stateless_http=True`, and `json_response=True`. The resulting ASGI app SHALL be mounted onto the FastAPI application. The MCP session manager SHALL be started and stopped via the application's lifespan context manager.

The server SHALL pass `transport_security` explicitly to `streamable_http_app()`. It SHALL NOT rely on the default, because `streamable_http_app()` defaults to `host="127.0.0.1"` and auto-enables DNS rebinding protection when no `transport_security` is supplied, whose auto-allowlist matches `host:port` patterns and rejects a request carrying a bare `Host` header with `421 Invalid Host header`. errand authenticates MCP clients with an API key and is reached through an ingress under its own hostname, so rebinding protection is not the applicable control.

The `mcp` requirement SHALL carry an upper bound below the next major version. It SHALL NOT request the `[http]` extra, which v2 does not publish.

#### Scenario: MCP endpoint responds to POST

- **WHEN** a client sends a valid MCP JSON-RPC request to `POST /mcp`
- **THEN** the server returns a valid MCP JSON-RPC response

#### Scenario: Request carrying a real hostname is accepted

- **WHEN** an authenticated client sends an MCP request to `/mcp` with a `Host` header naming the deployment's hostname, with or without a port
- **THEN** the server processes the request
- **AND** the server does NOT respond `421 Invalid Host header`

#### Scenario: Requirement does not admit the next major version

- **WHEN** the `mcp` entry in `errand/requirements.txt` is inspected
- **THEN** it specifies an upper bound below the next major version
- **AND** it does not request the `[http]` extra

#### Scenario: MCP endpoint listed in tool discovery

- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** the response includes the tools: `new_task`, `task_status`, `task_output`, `task_logs`, `schedule_task`, `post_tweet`, `list_emails`, `read_email`, `list_email_folders`, `move_email`, `send_email`, `forward_email`, `web_search`, `read_url`

The `post_tweet` tool SHALL delegate to the platform registry's `TwitterPlatform.post()` method instead of calling the Tweepy API directly. The tool's interface (parameters, return format) SHALL remain unchanged.

#### Scenario: post_tweet delegates to platform abstraction

- **WHEN** a client calls `post_tweet` with a valid message
- **THEN** the MCP tool calls `registry.get("twitter").post(message)` and returns the result

#### Scenario: post_tweet with no platform configured

- **WHEN** a client calls `post_tweet` and the Twitter platform has no credentials (DB or env var)
- **THEN** the tool returns "Error: Twitter API credentials not configured"

## ADDED Requirements

### Requirement: MCP tool signatures unchanged across the SDK major

The SDK migration SHALL NOT change the MCP surface observed by clients. Every tool exposed before the migration SHALL be exposed after it, under the same name, with the same parameters and the same return format. No tool SHALL be added, removed, or renamed as part of the migration.

#### Scenario: Tool catalogue is identical across the migration

- **WHEN** `tools/list` responses from before and after the migration are compared
- **THEN** the set of tool names is identical
- **AND** each tool's parameter names, types and required flags are identical

#### Scenario: A v1 client can call a v2 server

- **WHEN** a client built on mcp SDK v1 connects to the migrated server and invokes a tool
- **THEN** the call succeeds and returns the same result shape it returned before the migration
