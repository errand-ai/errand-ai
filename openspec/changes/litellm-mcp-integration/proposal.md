## Why

LiteLLM already proxies our LLM calls, but it also proxies MCP servers — handling authentication, transport, and access control for each upstream server. Today, adding an MCP server to the task runner requires manual JSON editing in Settings > Agent Configuration. If the user's `openai_base_url` points to a LiteLLM instance, we can auto-discover available MCP servers and let the user toggle them on/off from the Integrations page, with LiteLLM handling all upstream auth.

## What Changes

- New backend endpoint `GET /api/litellm/mcp-servers` that probes the LiteLLM API (`/v1/mcp/server` for server metadata, `/v1/mcp/tools` for tool lists) using the existing `openai_base_url` and `openai_api_key` settings. Returns a merged list of servers with their tools, plus which servers the user has enabled. Returns `available: false` if the base URL is not a LiteLLM instance (404/timeout/error).
- New `litellm_mcp_servers` setting (list of server aliases the user has enabled).
- New `LitellmMcpSettings.vue` component on the Integrations page showing discovered MCP servers with toggle checkboxes, tool counts, and descriptions. Section only appears when LiteLLM is detected. Fetches on page load with a manual Refresh button.
- Worker injects a single `litellm` entry into the task runner's `mcp.json` pointing at `{openai_base_url}/mcp` with `x-mcp-servers` header scoped to the user's enabled servers.

## Capabilities

### New Capabilities
- `litellm-mcp-discovery`: Backend discovery of MCP servers from LiteLLM proxy API, including auto-detection of whether the configured LLM provider is a LiteLLM instance.
- `litellm-mcp-settings-ui`: Frontend UI component for browsing and toggling LiteLLM MCP servers on the Integrations settings page.
- `litellm-mcp-worker-injection`: Worker logic to inject a LiteLLM MCP gateway entry into task runner container configuration based on user's enabled servers.

### Modified Capabilities
- `admin-settings-ui`: Integrations sub-page gains a new LiteLLM MCP Servers section alongside existing platform integrations.
- `settings-registry`: New `litellm_mcp_servers` key added to the settings registry.

## Impact

- **Backend**: New API endpoint in `main.py`, new setting in `settings_registry.py`, new injection logic in `worker.py`.
- **Frontend**: New `LitellmMcpSettings.vue` component, updated `IntegrationsPage.vue`.
- **Dependencies**: `httpx` (already in requirements) for LiteLLM API calls.
- **No database migration**: Setting model is key-value, no schema changes needed.
- **No breaking changes**: Existing MCP server configuration (raw JSON) is unaffected. LiteLLM servers are additive.
