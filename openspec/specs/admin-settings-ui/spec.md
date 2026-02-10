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
The Settings page SHALL display a heading "Settings" and two sections: "System Prompt" and "MCP Server Configuration". Each section SHALL have a card-style container with a title and form content.

#### Scenario: Settings page renders sections
- **WHEN** an admin views the Settings page
- **THEN** the page displays a "Settings" heading and two sections: "System Prompt" and "MCP Server Configuration"

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
The Settings page SHALL display a placeholder section for MCP server configuration. The placeholder SHALL include descriptive text indicating that MCP server configuration will be available in a future update. The section SHALL display any existing `mcp_servers` setting value as read-only formatted JSON.

#### Scenario: MCP section with no existing config
- **WHEN** the Settings page loads and no `mcp_servers` setting exists
- **THEN** the MCP section displays placeholder text about future availability

#### Scenario: MCP section with existing config
- **WHEN** the Settings page loads and an `mcp_servers` setting exists
- **THEN** the MCP section displays the configuration as formatted read-only JSON

### Requirement: Settings page error handling
The Settings page SHALL display an error message if the `GET /api/settings` request fails or if a `PUT /api/settings` request fails. A 403 response SHALL display "Access denied -- admin role required."

#### Scenario: API returns 403
- **WHEN** the settings API returns HTTP 403
- **THEN** the page displays "Access denied -- admin role required."

#### Scenario: API returns network error
- **WHEN** the settings API request fails due to a network error
- **THEN** the page displays a generic error message

### Requirement: LLM model selector on settings page
The Settings page SHALL display a "LLM Model" section with a dropdown to select the active LLM model. The dropdown SHALL be populated by calling `GET /api/llm/models`. The current selection SHALL be loaded from `GET /api/settings` (key `llm_model`). If no `llm_model` setting exists, the dropdown SHALL default to `claude-haiku-4-5-20251001`. Changing the selection SHALL immediately save the choice via `PUT /api/settings` with `{"llm_model": "<selected>"}`.

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
