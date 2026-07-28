## Purpose

Frontend settings section for viewing and toggling LiteLLM-provided MCP servers on the Agent Configuration page.

## Requirements

### Requirement: LiteLLM MCP Servers section on Agent Configuration page
The Agent Configuration settings page SHALL display a "MCP Servers (via LiteLLM)" section when the LiteLLM proxy is detected. The section SHALL NOT appear when the LiteLLM proxy is not detected. The section SHALL appear below the existing MCP Server Configuration section.

#### Scenario: LiteLLM detected
- **WHEN** an admin opens Settings > Agent Configuration and the discovery endpoint returns `available: true`
- **THEN** a "MCP Servers (via LiteLLM)" section is displayed below MCP Server Configuration

#### Scenario: LiteLLM not detected
- **WHEN** an admin opens Settings > Agent Configuration and the discovery endpoint returns `available: false`
- **THEN** no LiteLLM MCP section is displayed

### Requirement: Fetch on page load
The component SHALL call `GET /api/litellm/mcp-servers` when the Agent Configuration page mounts. A loading state SHALL be displayed while the request is in flight. The loading state SHALL NOT block the rendering of the other Agent Configuration sections.

#### Scenario: Loading state
- **WHEN** the Agent Configuration page mounts and the discovery request is in flight
- **THEN** a loading indicator is shown in the LiteLLM MCP section area

#### Scenario: Error during fetch
- **WHEN** the discovery request fails with a network error
- **THEN** the LiteLLM MCP section is hidden (same as unavailable)

### Requirement: LiteLLM MCP server selection is editable and persisted

The "MCP Servers (via LiteLLM)" section SHALL render a toggle per discovered server, reflecting whether that server's alias is present in the `litellm_mcp_servers` setting. The section SHALL track dirty state against the loaded selection and SHALL persist the current selection by sending `litellm_mcp_servers` as an array of alias strings to the settings API. The request SHALL NOT include keys for settings the section does not own.

An empty selection SHALL persist as an empty array, never as `null` and never by omitting the key — otherwise disabling the last enabled server would leave the previous selection in place.

#### Scenario: Enabling a server persists the alias

- **WHEN** an admin toggles "perplexity" on with "argocd" already enabled, and saves
- **THEN** the setting `litellm_mcp_servers` is persisted as `["argocd", "perplexity"]`

#### Scenario: Disabling the last server persists an empty array

- **WHEN** an admin toggles off the only enabled server and saves
- **THEN** the setting `litellm_mcp_servers` is persisted as `[]` and not as `null` or an absent key

#### Scenario: Save sends only the owned key

- **WHEN** an admin changes the selection and saves
- **THEN** the settings request body contains `litellm_mcp_servers` and no other setting key

#### Scenario: Section is clean until the selection changes

- **WHEN** an admin opens Agent Configuration and does not change any toggle
- **THEN** the section reports no unsaved changes

#### Scenario: Changing a toggle marks the section dirty

- **WHEN** an admin toggles a server on or off without saving
- **THEN** the section reports unsaved changes

#### Scenario: Successful save clears dirty state

- **WHEN** an admin saves a changed selection and the request succeeds
- **THEN** the section reports no unsaved changes and the saved selection becomes the new baseline

#### Scenario: Failed save keeps the change pending

- **WHEN** an admin saves a changed selection and the request fails
- **THEN** the section still reports unsaved changes so the edit is not silently discarded

#### Scenario: Discard restores the loaded selection

- **WHEN** an admin toggles two servers and then discards
- **THEN** every toggle returns to its loaded state and the section reports no unsaved changes
