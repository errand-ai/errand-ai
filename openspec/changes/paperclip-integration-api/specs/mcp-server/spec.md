## MODIFIED Requirements

### Requirement: Structured task status output
The `task_status` MCP tool SHALL support returning structured JSON in addition to plaintext.

#### Scenario: JSON format requested
- **WHEN** `task_status` is called with `format="json"`
- **THEN** the tool SHALL return a JSON string containing `id`, `title`, `status`, `category`, `created_at`, `updated_at`, and `has_output` fields

#### Scenario: Default text format
- **WHEN** `task_status` is called without a `format` parameter or with `format="text"`
- **THEN** the tool SHALL return the existing plaintext format (backward compatible)

## ADDED Requirements

### Requirement: Capture X-Client-Id header for task attribution
MCP tool handlers that create tasks SHALL read the `X-Client-Id` HTTP header from the request and use its value as the task's `created_by` field.

#### Scenario: Client sends X-Client-Id header
- **WHEN** an MCP request includes the header `X-Client-Id: paperclip`
- **AND** `new_task` or `schedule_task` creates a task
- **THEN** the task's `created_by` SHALL be `"paperclip"`

#### Scenario: Client does not send X-Client-Id header
- **WHEN** an MCP request does not include the `X-Client-Id` header
- **AND** `new_task` or `schedule_task` creates a task
- **THEN** the task's `created_by` SHALL be `"mcp"` (backward compatible)

### Requirement: API key authentication for log streaming
The log streaming SSE endpoint SHALL accept the MCP API key as an authentication token.

#### Scenario: API key used for log streaming
- **WHEN** `GET /api/tasks/{id}/logs/stream?token={mcp_api_key}` is requested with the MCP API key
- **THEN** the endpoint SHALL authenticate the request and stream logs

#### Scenario: JWT still accepted
- **WHEN** `GET /api/tasks/{id}/logs/stream?token={jwt}` is requested with a valid JWT
- **THEN** the endpoint SHALL authenticate the request as before (backward compatible)

#### Scenario: Invalid token
- **WHEN** `GET /api/tasks/{id}/logs/stream?token={invalid}` is requested with neither a valid JWT nor the MCP API key
- **THEN** the endpoint SHALL return 401 Unauthorized
