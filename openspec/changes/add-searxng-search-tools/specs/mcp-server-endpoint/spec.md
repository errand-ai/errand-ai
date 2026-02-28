## MODIFIED Requirements

### Requirement: MCP server mounted at /mcp

The backend SHALL mount an MCP Streamable HTTP server at the `/mcp` path using the official MCP Python SDK (`mcp` package). The server SHALL use `MCPServer` from `mcp.server.mcpserver` and mount `streamable_http_app()` onto the FastAPI application with `streamable_http_path="/"` so the endpoint is accessible at `/mcp`. The MCP session manager SHALL be started and stopped via the application's lifespan context manager. The server SHALL use `stateless_http=True` and `json_response=True`.

#### Scenario: MCP endpoint responds to POST

- **WHEN** a client sends a valid MCP JSON-RPC request to `POST /mcp`
- **THEN** the server returns a valid MCP JSON-RPC response

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

### Requirement: web_search MCP tool

The MCP server SHALL expose a `web_search` tool that accepts `query` (str, required) and optional parameters: `categories` (str), `time_range` (str), `language` (str), `safesearch` (int), `pageno` (int). The tool SHALL load SearXNG platform credentials from the database. If no credentials exist, it SHALL use the default URL (`https://search.errand.cloud`) without authentication. The tool SHALL call `SearXNGPlatform.search()` and return the result as a JSON string.

#### Scenario: Web search with default configuration

- **WHEN** a client calls `web_search` with `query="python web frameworks"` and no SearXNG credentials are configured
- **THEN** the tool searches `https://search.errand.cloud` and returns a JSON string with `query`, `results`, `suggestions`, and `number_of_results`

#### Scenario: Web search with configured credentials

- **WHEN** a client calls `web_search` and SearXNG credentials are stored with a custom URL and basic auth
- **THEN** the tool searches the custom URL with authentication

#### Scenario: Web search with filters

- **WHEN** a client calls `web_search` with `query="news"`, `time_range="day"`, `categories="news"`
- **THEN** the SearXNG request includes the filter parameters

#### Scenario: Web search with SearXNG unavailable

- **WHEN** a client calls `web_search` and the SearXNG instance is unreachable
- **THEN** the tool returns a JSON string with an `error` key describing the failure

### Requirement: read_url MCP tool

The MCP server SHALL expose a `read_url` tool that accepts `url` (str, required) and `max_length` (int, optional, default 50000). The tool SHALL fetch the URL, convert HTML to markdown, and return a JSON string with `url`, `title`, and `content` keys. On failure, it SHALL return a JSON string with an `error` key.

#### Scenario: Read URL successfully

- **WHEN** a client calls `read_url` with a valid URL
- **THEN** the tool returns a JSON string with the page URL, title, and markdown content

#### Scenario: Read URL with error

- **WHEN** a client calls `read_url` with an unreachable URL
- **THEN** the tool returns a JSON string with an `error` key
