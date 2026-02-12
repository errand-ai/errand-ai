## Requirements

### Requirement: Vue Router with two routes
The frontend SHALL use Vue Router with two routes: `/` rendering the Kanban board and `/settings` rendering the Settings page. The router SHALL be configured in history mode. The `App.vue` template SHALL use `<router-view>` in place of direct component rendering.

#### Scenario: Root route shows kanban board
- **WHEN** an authenticated user navigates to `/`
- **THEN** the Kanban board is rendered

#### Scenario: Settings route shows settings page
- **WHEN** an authenticated admin user navigates to `/settings`
- **THEN** the Settings page is rendered

### Requirement: Settings route requires admin role
The `/settings` route SHALL have a navigation guard that checks `isAdmin` from the auth store. If the user is not an admin, the guard SHALL redirect to `/`.

#### Scenario: Admin navigates to settings
- **WHEN** an admin user navigates to `/settings`
- **THEN** the Settings page is rendered

#### Scenario: Non-admin navigates to settings
- **WHEN** a non-admin user navigates to `/settings`
- **THEN** the user is redirected to `/`

#### Scenario: Unauthenticated user navigates to settings
- **WHEN** an unauthenticated user navigates to `/settings`
- **THEN** the user is redirected to `/auth/login` (handled by existing auth logic)

### Requirement: Settings page layout
The Settings page SHALL display a heading "Settings" and three sections: "System Prompt", "MCP Server Configuration", and "LLM Models". Each section SHALL have a card-style container with a title and form content. The "LLM Models" section SHALL contain both the title-generation model selector and the task processing model selector.

#### Scenario: Settings page renders sections
- **WHEN** an admin views the Settings page
- **THEN** the page displays a "Settings" heading and three sections: "System Prompt", "MCP Server Configuration", and "LLM Models"

### Requirement: System prompt editor
The Settings page SHALL display a textarea for editing the system prompt. The textarea SHALL load the current value from `GET /api/settings` on mount. A "Save" button SHALL send the updated value via `PUT /api/settings` with the key `system_prompt`.

#### Scenario: Load existing system prompt
- **WHEN** the Settings page loads and a `system_prompt` setting exists
- **THEN** the textarea displays the current system prompt value

#### Scenario: No existing system prompt
- **WHEN** the Settings page loads and no `system_prompt` setting exists
- **THEN** the textarea is empty

#### Scenario: Save system prompt
- **WHEN** the admin edits the system prompt text and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"system_prompt": "<new value>"}` and displays a success indication

### Requirement: MCP server configuration placeholder
The Settings page SHALL display an editable section for MCP server configuration. The section SHALL include an expandable text box (collapsed by default) where the admin can view and edit the MCP server configuration as JSON text. A "Save" button SHALL send the updated value via `PUT /api/settings` with the key `mcp_servers`. The section SHALL load the current value from `GET /api/settings` on mount.

#### Scenario: MCP section with no existing config
- **WHEN** the Settings page loads and no `mcp_servers` setting exists
- **THEN** the MCP section displays an empty expandable text box with placeholder text

#### Scenario: MCP section with existing config
- **WHEN** the Settings page loads and an `mcp_servers` setting exists
- **THEN** the MCP section displays the configuration as editable formatted JSON in the expandable text box

#### Scenario: Save MCP configuration
- **WHEN** the admin edits the MCP server configuration text and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"mcp_servers": <parsed JSON>}` and displays a success indication

#### Scenario: Invalid JSON rejected
- **WHEN** the admin enters invalid JSON in the MCP configuration text box and clicks "Save"
- **THEN** the frontend displays a validation error and does not send the API request

#### Scenario: Expand and collapse
- **WHEN** the admin clicks the MCP server configuration section header
- **THEN** the text box expands to show the full configuration, or collapses if already expanded

### Requirement: Settings page error handling
The Settings page SHALL display an error message if the `GET /api/settings` request fails or if a `PUT /api/settings` request fails. A 403 response SHALL display "Access denied -- admin role required."

#### Scenario: API returns 403
- **WHEN** the settings API returns HTTP 403
- **THEN** the page displays "Access denied -- admin role required."

#### Scenario: API returns network error
- **WHEN** the settings API request fails due to a network error
- **THEN** the page displays a generic error message

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

The Settings page SHALL display an additional section "Task Archiving" containing a number input labelled "Archive after (days)" for configuring how many days completed tasks remain on the board before being auto-archived. The input SHALL load its current value from `GET /api/settings` (key `archive_after_days`). If no `archive_after_days` setting exists, the input SHALL default to `3`. A "Save" button SHALL send the updated value via `PUT /api/settings` with `{"archive_after_days": <number>}`.

#### Scenario: Load default archive interval
- **WHEN** the Settings page loads and no `archive_after_days` setting exists
- **THEN** the "Archive after (days)" input displays `3`

#### Scenario: Load existing archive interval
- **WHEN** the Settings page loads and `archive_after_days` is set to `7`
- **THEN** the "Archive after (days)" input displays `7`

#### Scenario: Save archive interval
- **WHEN** the admin changes the archive interval to `5` and clicks "Save"
- **THEN** the frontend sends `PUT /api/settings` with `{"archive_after_days": 5}` and displays a success indication

### Requirement: Archived Tasks navigation link

The header user dropdown SHALL include an "Archived Tasks" link that navigates to `/archived`. The link SHALL be visible to all authenticated users (viewer, editor, admin), positioned above the Settings link in the dropdown.

#### Scenario: Viewer sees Archived Tasks link
- **WHEN** a viewer opens the user dropdown in the header
- **THEN** the dropdown includes an "Archived Tasks" link but not a "Settings" link

#### Scenario: Admin sees both links
- **WHEN** an admin opens the user dropdown in the header
- **THEN** the dropdown includes both "Archived Tasks" and "Settings" links

#### Scenario: Archived Tasks link navigates to page
- **WHEN** a user clicks the "Archived Tasks" link in the dropdown
- **THEN** the browser navigates to `/archived`

The "LLM Models" section SHALL display a third dropdown labelled "Transcription Model" for selecting the speech-to-text model. The dropdown SHALL be populated by calling `GET /api/llm/transcription-models` (NOT the generic `/api/llm/models` endpoint) which returns only models with audio transcription capability. The current selection SHALL be loaded from `GET /api/settings` (key `transcription_model`). If no `transcription_model` setting exists, the dropdown SHALL show a placeholder "Select a model to enable voice input" with no model selected. Selecting a model SHALL immediately save the choice via `PUT /api/settings` with `{"transcription_model": "<selected>"}`.

The dropdown SHALL also include a "Disabled" option that, when selected, removes the `transcription_model` setting (sends `PUT /api/settings` with `{"transcription_model": null}`), disabling voice input for all users.

#### Scenario: No transcription model selected (default)
- **WHEN** the Settings page loads and no `transcription_model` setting exists
- **THEN** the "Transcription Model" dropdown shows placeholder "Select a model to enable voice input" with no model selected

#### Scenario: Transcription model selected
- **WHEN** the Settings page loads and the `transcription_model` setting is `groq/whisper-large-v3`
- **THEN** the "Transcription Model" dropdown shows `groq/whisper-large-v3` as selected

#### Scenario: Select transcription model
- **WHEN** the admin selects `whisper-1` from the "Transcription Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with `{"transcription_model": "whisper-1"}` and shows a success indication

#### Scenario: Disable transcription
- **WHEN** the admin selects "Disabled" from the "Transcription Model" dropdown
- **THEN** the frontend sends `PUT /api/settings` with `{"transcription_model": null}` to remove the setting, disabling voice input

#### Scenario: Only transcription-capable models shown
- **WHEN** the Settings page loads the transcription model dropdown
- **THEN** only models with `mode: audio_transcription` from the LiteLLM proxy are shown (not general chat or embedding models)

#### Scenario: No transcription models available
- **WHEN** `GET /api/llm/transcription-models` returns an empty array
- **THEN** the dropdown is disabled and shows "No transcription models available"

#### Scenario: Transcription models endpoint unavailable
- **WHEN** `GET /api/llm/transcription-models` fails
- **THEN** the dropdown is disabled and an error message is displayed
