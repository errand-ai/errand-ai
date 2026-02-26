## 1. Settings Registry

- [x] 1.1 Add `litellm_mcp_servers` to `SETTINGS_REGISTRY` in `errand/settings_registry.py` with `env_var: None`, `sensitive: False`, `default: []`

## 2. Backend Discovery Endpoint

- [x] 2.1 Add `GET /api/litellm/mcp-servers` endpoint to `errand/main.py` (admin-only) that resolves `openai_base_url` and `openai_api_key` from settings, calls LiteLLM API, and returns the merged response
- [x] 2.2 Implement LiteLLM detection: `GET {base_url}/v1/mcp/server` with Bearer auth and 5-second timeout. Return `available: false` on any error (404, timeout, non-JSON)
- [x] 2.3 Implement parallel fetch of `/v1/mcp/server` (server metadata) and `/v1/mcp/tools` (tool list) using httpx async
- [x] 2.4 Implement tool-to-server matching: parse tool name prefix before first `-`, match against known server aliases from server list
- [x] 2.5 Strip sensitive fields from server response (`env`, `credentials`, `command`, `args`, `static_headers`, `authorization_url`, `token_url`, `registration_url`, `extra_headers`)
- [x] 2.6 Include `enabled` field in response by reading `litellm_mcp_servers` setting from database
- [x] 2.7 Add backend tests for discovery endpoint: LiteLLM detected, not detected, timeout, empty server list, tool matching, sensitive data stripping

## 3. Worker Injection

- [x] 3.1 Add `litellm_mcp_servers` to the settings keys read in `worker.py` `read_settings()`
- [x] 3.2 Add LiteLLM MCP injection logic in worker: if `litellm_mcp_servers` is non-empty and `openai_base_url` is set, inject `litellm` entry into `mcp_servers` with `url: {base_url}/mcp`, `Authorization` header, and `x-mcp-servers` header
- [x] 3.3 Skip injection if user has manually configured a `litellm` key in their MCP server JSON
- [x] 3.4 Add worker tests for LiteLLM MCP injection: enabled servers, no servers, no base URL, manual override exists

## 4. Frontend Component

- [x] 4.1 Create `LitellmMcpSettings.vue` component with: loading state, server list with checkboxes, tool count display, expandable tool names, save button, refresh button
- [x] 4.2 Add `fetchLitellmMcpServers` API function in `useApi.ts` composable
- [x] 4.3 Integrate `LitellmMcpSettings.vue` into `IntegrationsPage.vue` below `PlatformSettings`
- [x] 4.4 Implement save: collect enabled aliases, call `PUT /api/settings` with `litellm_mcp_servers` key
- [x] 4.5 Add frontend tests for LitellmMcpSettings: renders when available, hidden when unavailable, toggle behavior, save, refresh
