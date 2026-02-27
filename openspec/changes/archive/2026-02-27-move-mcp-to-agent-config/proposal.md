## Why

The "MCP Servers (via LiteLLM)" settings section currently lives on the Integrations sub-page, but it configures which MCP servers the agent uses — making it an agent configuration concern, not a platform integration. With the new Task Profiles feature (which also selects LiteLLM MCP servers per-profile), having the global LiteLLM MCP settings on the Agent Configuration page creates a more coherent grouping: system prompt, skills, MCP servers (static config), and MCP servers (via LiteLLM) all in one place.

## What Changes

- Move `LitellmMcpSettings.vue` from the Integrations page to the Agent Configuration page (after the existing MCP Server Configuration section)
- Remove the LiteLLM MCP section from `IntegrationsPage.vue`, leaving only Platform Settings
- Update the `admin-settings-ui` spec to reflect the new section placement
- Update the `litellm-mcp-settings-ui` spec to reference Agent Configuration instead of Integrations

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `admin-settings-ui`: Agent Configuration page gains the LiteLLM MCP Servers section; Integrations page loses it
- `litellm-mcp-settings-ui`: Section location changes from Integrations to Agent Configuration page

## Impact

- **Frontend pages**: `AgentConfigurationPage.vue` (add import), `IntegrationsPage.vue` (remove import)
- **Router/navigation**: No changes — both pages already exist at the same routes
- **Backend**: No changes — the API endpoints and settings keys are unchanged
- **Tests**: Any tests asserting LiteLLM MCP section is on Integrations page need updating
