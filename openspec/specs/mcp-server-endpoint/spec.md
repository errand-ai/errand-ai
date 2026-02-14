## ADDED Requirements

### Requirement: MCP server mounted at /mcp

The backend SHALL mount an MCP Streamable HTTP server at the `/mcp` path using the official MCP Python SDK (`mcp` package). The server SHALL use `MCPServer` from `mcp.server.mcpserver` and mount `streamable_http_app()` onto the FastAPI application with `streamable_http_path="/"` so the endpoint is accessible at `/mcp`. The MCP session manager SHALL be started and stopped via the application's lifespan context manager. The server SHALL use `stateless_http=True` and `json_response=True`.

#### Scenario: MCP endpoint responds to POST

- **WHEN** a client sends a valid MCP JSON-RPC request to `POST /mcp`
- **THEN** the server returns a valid MCP JSON-RPC response

#### Scenario: MCP endpoint listed in tool discovery

- **WHEN** a client sends a `tools/list` request to `/mcp`
- **THEN** the response includes the tools: `new_task`, `task_status`, `task_output`, `list_skills`, `get_skill`, `post_tweet`

### Requirement: API key authentication via TokenVerifier

The MCP server SHALL require Bearer token authentication. The server SHALL use a custom `TokenVerifier` implementation that validates the provided token against the `mcp_api_key` stored in the `settings` table. The comparison SHALL use `secrets.compare_digest` for timing-safe validation. If the token is invalid or missing, the MCP SDK SHALL return an appropriate error response.

#### Scenario: Valid API key accepted

- **WHEN** a client sends an MCP request with `Authorization: Bearer <valid-api-key>`
- **THEN** the request is processed and a valid response is returned

#### Scenario: Invalid API key rejected

- **WHEN** a client sends an MCP request with `Authorization: Bearer invalid-key`
- **THEN** the server returns an authentication error

#### Scenario: Missing Authorization header rejected

- **WHEN** a client sends an MCP request without an Authorization header
- **THEN** the server returns an authentication error

### Requirement: API key auto-generation on startup

The backend SHALL generate an MCP API key on application startup if one does not already exist. The key SHALL be a 64-character hex string generated via `secrets.token_hex(32)`. The key SHALL be stored in the `settings` table with key `mcp_api_key`. If a key already exists, it SHALL NOT be overwritten.

#### Scenario: First startup generates key

- **WHEN** the backend starts and no `mcp_api_key` setting exists
- **THEN** a new 64-character hex API key is generated and stored in the `settings` table

#### Scenario: Subsequent startup preserves key

- **WHEN** the backend starts and an `mcp_api_key` setting already exists
- **THEN** the existing key is preserved unchanged

### Requirement: new_task tool

The MCP server SHALL expose a `new_task` tool that accepts a `description` parameter (string). The tool SHALL create a new task using the same logic as the existing `POST /api/tasks` endpoint: insert a row into the `tasks` table with the description as both `title` and `description`, status `"new"`, category `"one-off"`, and the next available position. The tool SHALL use the LLM title-generation function to generate a short title if available, falling back to the raw description. The tool SHALL return the UUID of the created task. The tool SHALL publish a `task_created` WebSocket event.

#### Scenario: Create task via MCP

- **WHEN** a client calls the `new_task` tool with `description: "Research the latest Python frameworks"`
- **THEN** a new task is created with a generated title, the task UUID is returned, and a `task_created` WebSocket event is published

#### Scenario: Create task with title generation unavailable

- **WHEN** a client calls the `new_task` tool and the LLM title generation fails
- **THEN** the task is created using the description as the title and the UUID is returned

### Requirement: task_status tool

The MCP server SHALL expose a `task_status` tool that accepts a `task_id` parameter (string, UUID format). The tool SHALL query the task from the database and return its current status, title, category, and timestamps (created_at, updated_at). If the task does not exist, the tool SHALL return an error message.

#### Scenario: Get status of existing task

- **WHEN** a client calls the `task_status` tool with a valid task UUID
- **THEN** the tool returns the task's title, status, category, created_at, and updated_at

#### Scenario: Get status of non-existent task

- **WHEN** a client calls the `task_status` tool with a UUID that does not exist
- **THEN** the tool returns an error message indicating the task was not found

### Requirement: task_output tool

The MCP server SHALL expose a `task_output` tool that accepts a `task_id` parameter (string, UUID format). The tool SHALL query the task from the database. If the task status is `"completed"` or `"review"`, the tool SHALL return the task's `output` field. If the task is not in a terminal state, the tool SHALL return a message indicating the task is still in progress with its current status. If the task does not exist, the tool SHALL return an error message.

#### Scenario: Get output of completed task

- **WHEN** a client calls the `task_output` tool with the UUID of a task in `"completed"` status
- **THEN** the tool returns the task's output content

#### Scenario: Get output of review task

- **WHEN** a client calls the `task_output` tool with the UUID of a task in `"review"` status
- **THEN** the tool returns the task's output content

#### Scenario: Get output of running task

- **WHEN** a client calls the `task_output` tool with the UUID of a task in `"running"` status
- **THEN** the tool returns a message like "Task is still in progress (status: running)"

#### Scenario: Get output of non-existent task

- **WHEN** a client calls the `task_output` tool with a UUID that does not exist
- **THEN** the tool returns an error message indicating the task was not found
