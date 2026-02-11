## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL display a heading "Settings" and three sections: "System Prompt", "MCP Server Configuration", and "LLM Models". Each section SHALL have a card-style container with a title and form content. The "LLM Models" section SHALL contain both the title-generation model selector and the task processing model selector.

#### Scenario: Settings page renders sections
- **WHEN** an admin views the Settings page
- **THEN** the page displays a "Settings" heading and three sections: "System Prompt", "MCP Server Configuration", and "LLM Models"

### Requirement: LLM model selector on settings page
The Settings page SHALL display a "LLM Model" section with a dropdown to select the active LLM model. The dropdown SHALL be populated by calling `GET /api/llm/models`. The current selection SHALL be loaded from `GET /api/settings` (key `llm_model`). If no `llm_model` setting exists, the dropdown SHALL default to `claude-haiku-4-5-20251001`. Changing the selection SHALL immediately save the choice via `PUT /api/settings` with `{"llm_model": "<selected>"}`. The dropdown SHALL be labelled "Title Generation Model" to distinguish it from the task processing model.

#### Scenario: Model dropdown loads with current selection
- **WHEN** the Settings page loads and the `llm_model` setting is "gpt-4o-mini"
- **THEN** the dropdown shows available models with "gpt-4o-mini" selected

#### Scenario: Model dropdown with default
- **WHEN** the Settings page loads and no `llm_model` setting exists
- **THEN** the dropdown shows available models with "claude-haiku-4-5-20251001" selected

#### Scenario: Change model selection
- **WHEN** the admin selects a different model from the dropdown
- **THEN** the frontend sends `PUT /api/settings` with the new `llm_model` value and shows a success indication

#### Scenario: Models endpoint unavailable
- **WHEN** the Settings page loads and `GET /api/llm/models` fails
- **THEN** the dropdown is disabled and an error message is displayed indicating the model list could not be loaded

## ADDED Requirements

### Requirement: Task processing model selector on settings page
The Settings page SHALL display a "Task Processing Model" dropdown within the "LLM Models" section. The dropdown SHALL be populated by calling `GET /api/llm/models` (same endpoint as the title-generation model). The current selection SHALL be loaded from `GET /api/settings` (key `task_processing_model`). If no `task_processing_model` setting exists, the dropdown SHALL default to `claude-sonnet-4-5-20250929`. Changing the selection SHALL immediately save the choice via `PUT /api/settings` with `{"task_processing_model": "<selected>"}`.

#### Scenario: Task processing model dropdown loads with current selection
- **WHEN** the Settings page loads and the `task_processing_model` setting is "claude-sonnet-4-5-20250929"
- **THEN** the "Task Processing Model" dropdown shows available models with "claude-sonnet-4-5-20250929" selected

#### Scenario: Task processing model dropdown with default
- **WHEN** the Settings page loads and no `task_processing_model` setting exists
- **THEN** the "Task Processing Model" dropdown shows available models with "claude-sonnet-4-5-20250929" selected

#### Scenario: Change task processing model
- **WHEN** the admin selects a different model from the "Task Processing Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with the new `task_processing_model` value and shows a success indication

#### Scenario: Models endpoint unavailable disables both dropdowns
- **WHEN** the Settings page loads and `GET /api/llm/models` fails
- **THEN** both model dropdowns are disabled and an error message is displayed

### Requirement: MCP server configuration validation
The Settings page SHALL validate the MCP server configuration JSON before saving. The configuration SHALL conform to the format `{"mcpServers": {"<name>": {"url": "<endpoint>", "headers": {…}}}}`. Each server entry MUST have a `url` field (string). The `headers` field is optional (object of string key-value pairs). The Settings page SHALL reject any server entry that contains `command` or `args` fields (STDIO pattern) and display a validation error explaining that only HTTP Streaming MCP servers are supported. The Settings page SHALL reject malformed JSON with a parse error message.

#### Scenario: Valid HTTP Streaming configuration saved
- **WHEN** an admin enters `{"mcpServers": {"argocd": {"url": "http://localhost:4000/argocd/mcp", "headers": {"x-litellm-api-key": "Bearer sk-1234"}}}}` in the MCP configuration field
- **THEN** the configuration is accepted and saved via `PUT /api/settings`

#### Scenario: STDIO configuration rejected
- **WHEN** an admin enters `{"mcpServers": {"local": {"command": "npx", "args": ["-y", "some-mcp-server"]}}}` in the MCP configuration field
- **THEN** the save is blocked and a validation error is displayed: "Only HTTP Streaming MCP servers are supported. Server 'local' uses STDIO transport (command/args) which is not allowed."

#### Scenario: Mixed valid and invalid servers rejected
- **WHEN** an admin enters a configuration with one HTTP Streaming server and one STDIO server
- **THEN** the save is blocked and a validation error identifies the STDIO server by name

#### Scenario: Missing url field rejected
- **WHEN** an admin enters `{"mcpServers": {"test": {"headers": {"key": "value"}}}}` (no `url` field)
- **THEN** the save is blocked and a validation error is displayed: "Server 'test' is missing required 'url' field."

#### Scenario: Invalid JSON rejected
- **WHEN** an admin enters malformed JSON in the MCP configuration field
- **THEN** the save is blocked and a validation error is displayed indicating the JSON is invalid
