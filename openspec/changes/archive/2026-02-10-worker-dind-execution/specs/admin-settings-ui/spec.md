## MODIFIED Requirements

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
