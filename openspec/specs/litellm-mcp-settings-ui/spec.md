## Requirements

### Requirement: LiteLLM MCP Servers section on Integrations page
The Integrations settings page SHALL display a "MCP Servers (via LiteLLM)" section when the LiteLLM proxy is detected. The section SHALL NOT appear when the LiteLLM proxy is not detected. The section SHALL appear below the existing platform integrations.

#### Scenario: LiteLLM detected
- **WHEN** an admin opens Settings > Integrations and the discovery endpoint returns `available: true`
- **THEN** a "MCP Servers (via LiteLLM)" section is displayed

#### Scenario: LiteLLM not detected
- **WHEN** an admin opens Settings > Integrations and the discovery endpoint returns `available: false`
- **THEN** no LiteLLM MCP section is displayed

### Requirement: Server list with toggle checkboxes
The LiteLLM MCP section SHALL display each discovered server as a row with: a checkbox toggle, the server alias (bold), the server description, and the tool count. Checking/unchecking a server SHALL mark it as enabled/disabled.

#### Scenario: Display server with tools
- **WHEN** the discovery endpoint returns server `argocd` with description "DevOps Consultants ArgoCD" and 14 tools
- **THEN** a row is displayed showing a checkbox, "argocd", "DevOps Consultants ArgoCD", and "14 tools"

#### Scenario: Toggle server on
- **WHEN** an admin checks the checkbox for `argocd`
- **THEN** `argocd` is added to the local enabled list and the Save button becomes active

#### Scenario: Toggle server off
- **WHEN** an admin unchecks the checkbox for `argocd`
- **THEN** `argocd` is removed from the local enabled list and the Save button becomes active

### Requirement: Tool name display
Each server row SHALL be expandable to show the list of tool names available on that server.

#### Scenario: Expand server to see tools
- **WHEN** an admin clicks on a server row
- **THEN** the row expands to show the list of tool names (e.g. "list_applications, get_application, sync_application, ...")

### Requirement: Save enabled servers
The LiteLLM MCP section SHALL have a Save button that sends the enabled server aliases to `PUT /api/settings` as the `litellm_mcp_servers` key. The Save button SHALL be disabled when there are no unsaved changes.

#### Scenario: Save enabled selections
- **WHEN** an admin toggles servers and clicks Save
- **THEN** `PUT /api/settings` is called with `{"litellm_mcp_servers": ["argocd", "perplexity"]}` (the enabled aliases)

### Requirement: Fetch on page load
The component SHALL call `GET /api/litellm/mcp-servers` when the Integrations page mounts. A loading state SHALL be displayed while the request is in flight. The loading state SHALL NOT block the rendering of the existing platform integrations section.

#### Scenario: Loading state
- **WHEN** the Integrations page mounts and the discovery request is in flight
- **THEN** a loading indicator is shown in the LiteLLM MCP section area

#### Scenario: Error during fetch
- **WHEN** the discovery request fails with a network error
- **THEN** the LiteLLM MCP section is hidden (same as unavailable)

### Requirement: Manual refresh button
The LiteLLM MCP section SHALL include a Refresh button that re-fetches the server and tool list from LiteLLM. The button SHALL show a loading state while the request is in flight.

#### Scenario: Refresh updates server list
- **WHEN** an admin clicks Refresh after a new MCP server was added in LiteLLM
- **THEN** the server list is re-fetched and the new server appears
