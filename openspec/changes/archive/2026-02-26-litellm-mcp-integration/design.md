## Context

The task runner already receives MCP server configuration via `/workspace/mcp.json`, injected by the worker. Users can manually configure MCP servers as raw JSON in Settings > Agent Configuration. LiteLLM is deployed at `litellm.coward.cloud` and already proxies both LLM models and MCP servers (currently ArgoCD and Perplexity). LiteLLM handles upstream authentication, transport (stdio/SSE/HTTP), and access control for each MCP server.

The `openai_base_url` and `openai_api_key` settings already point to the LiteLLM proxy for LLM calls. LiteLLM exposes:
- `GET /v1/mcp/server` — lists configured MCP servers with metadata (alias, description, server_name)
- `GET /v1/mcp/tools` — lists all available tools, namespaced as `{server_alias}-{tool_name}`
- `/{server_alias}/mcp` or `/mcp` with `x-mcp-servers` header — MCP Streamable HTTP gateway

## Goals / Non-Goals

**Goals:**
- Auto-detect whether the configured LLM provider is a LiteLLM instance
- Let users discover and toggle MCP servers from LiteLLM on the Integrations page
- Route task runner MCP traffic through LiteLLM's gateway (single connection, LiteLLM handles upstream auth)
- Zero configuration beyond what already exists (`openai_base_url` + `openai_api_key`)

**Non-Goals:**
- Managing LiteLLM's MCP server configuration from Errand (add/remove/edit servers on LiteLLM side)
- Per-tool granularity in the UI (toggle is per-server, not per-tool)
- Replacing the existing raw JSON MCP config (that stays for non-LiteLLM servers)
- LiteLLM as a managed container service (that's a separate existing spec)

## Decisions

### 1. Detection via `/v1/mcp/server` probe

**Decision**: The backend probes `GET {openai_base_url}/v1/mcp/server` with the existing API key. A successful JSON array response means LiteLLM is present. Any error (404, timeout, non-JSON) means it's not LiteLLM.

**Alternatives considered**:
- Probing `/health` — too generic, other services have health endpoints
- Requiring a separate `litellm_url` setting — unnecessary duplication since `openai_base_url` already points there
- User toggle — worse UX than auto-detection

### 2. Two-endpoint discovery (servers + tools)

**Decision**: Call both `GET /v1/mcp/server` and `GET /v1/mcp/tools` in parallel. The server endpoint gives metadata (alias, description). The tools endpoint gives tool names. Merge by matching tool name prefix `{alias}-` to server alias.

**Rationale**: `/v1/mcp/server` alone doesn't list tools. `/v1/mcp/tools` alone doesn't provide server descriptions. Both are fast GET calls.

### 3. Single LiteLLM MCP gateway entry in mcp.json

**Decision**: The worker injects one `litellm` MCP server entry pointing at `{openai_base_url}/mcp` with the `x-mcp-servers` header set to the comma-separated list of enabled server aliases. LiteLLM routes to the appropriate upstream servers.

**Alternatives considered**:
- One mcp.json entry per enabled server using `/{alias}/mcp` URL paths — more connections, more complexity
- Direct connection to upstream servers — defeats the purpose of LiteLLM proxying auth

### 4. Strip sensitive data from server list response

**Decision**: The backend strips the `env`, `credentials`, `command`, `args`, `static_headers`, `authorization_url`, `token_url`, and `registration_url` fields from the `/v1/mcp/server` response before returning to the frontend. Only alias, server_name, description, and status are forwarded.

**Rationale**: The LiteLLM API returns secrets (API keys, tokens) in the `env` field. These must never reach the browser.

### 5. Refresh on page load + manual button

**Decision**: The frontend calls the discovery endpoint when the Integrations page mounts. A Refresh button triggers a re-fetch. No polling or background refresh.

**Rationale**: MCP server configuration changes infrequently. On-demand is sufficient.

## Risks / Trade-offs

- **[LiteLLM API instability]** The `/v1/mcp/server` and `/v1/mcp/tools` endpoints are not heavily documented → Mitigation: graceful fallback to `available: false`. The feature degrades cleanly — users still have the manual JSON config.
- **[Tool name parsing assumption]** We assume tool names are `{alias}-{tool_name}` with hyphen delimiter → Mitigation: match against known aliases from the server list rather than blind splitting. Unmatched tools logged as warnings.
- **[Latency on page load]** Two HTTP calls to LiteLLM add load time → Mitigation: calls are parallel, short timeout (5s), UI shows loading state. The section is non-blocking — platform integrations render immediately.
- **[x-mcp-servers header support]** If LiteLLM changes how it scopes servers → Mitigation: per-server URL paths (`/{alias}/mcp`) work as a fallback approach.
