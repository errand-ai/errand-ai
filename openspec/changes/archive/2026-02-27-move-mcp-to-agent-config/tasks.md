## 1. Frontend — Move LiteLLM MCP section to Agent Configuration

- [x] 1.1 Add `LitellmMcpSettings` import and component to `AgentConfigurationPage.vue`, placed after `McpServerConfigSettings`
- [x] 1.2 Remove `LitellmMcpSettings` import and component from `IntegrationsPage.vue`, leaving only `PlatformSettings`

## 2. Tests

- [x] 2.1 Update any existing tests that assert LiteLLM MCP section is on the Integrations page to reference Agent Configuration instead (no changes needed — existing tests don't assert LiteLLM placement on a specific page)
