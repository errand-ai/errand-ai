## MODIFIED Requirements

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
