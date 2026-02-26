## ADDED Requirements

### Requirement: LiteLLM MCP server discovery endpoint
The backend SHALL expose `GET /api/litellm/mcp-servers` (admin-only) that returns a list of MCP servers available on the LiteLLM proxy, along with their tools and the user's enabled selections. The endpoint SHALL use the resolved `openai_base_url` and `openai_api_key` settings to authenticate with LiteLLM.

#### Scenario: LiteLLM detected with MCP servers
- **WHEN** an admin calls `GET /api/litellm/mcp-servers` and `openai_base_url` points to a LiteLLM instance with configured MCP servers
- **THEN** the response is `{"available": true, "servers": {"argocd": {"description": "...", "tools": ["list_applications", ...]}, ...}, "enabled": ["argocd"]}`

#### Scenario: LiteLLM detected with no MCP servers
- **WHEN** an admin calls `GET /api/litellm/mcp-servers` and `openai_base_url` points to a LiteLLM instance with no MCP servers configured
- **THEN** the response is `{"available": true, "servers": {}, "enabled": []}`

#### Scenario: Not a LiteLLM instance
- **WHEN** an admin calls `GET /api/litellm/mcp-servers` and `openai_base_url` points to a non-LiteLLM provider (e.g. api.openai.com)
- **THEN** the response is `{"available": false, "servers": {}, "enabled": []}`

#### Scenario: No openai_base_url configured
- **WHEN** an admin calls `GET /api/litellm/mcp-servers` and `openai_base_url` is empty
- **THEN** the response is `{"available": false, "servers": {}, "enabled": []}`

#### Scenario: LiteLLM unreachable
- **WHEN** an admin calls `GET /api/litellm/mcp-servers` and the LiteLLM instance is down or times out
- **THEN** the response is `{"available": false, "servers": {}, "enabled": []}`

### Requirement: LiteLLM detection via server list probe
The backend SHALL detect LiteLLM by sending `GET {openai_base_url}/v1/mcp/server` with `Authorization: Bearer {openai_api_key}`. A successful response (HTTP 200 with a JSON array) SHALL indicate LiteLLM is present. Any other response (404, 401, timeout, non-JSON) SHALL be treated as "not LiteLLM". The probe SHALL use a 5-second timeout.

#### Scenario: Successful probe
- **WHEN** the backend sends `GET {base_url}/v1/mcp/server` and receives HTTP 200 with a JSON array
- **THEN** LiteLLM is detected as available

#### Scenario: 404 response
- **WHEN** the backend sends `GET {base_url}/v1/mcp/server` and receives HTTP 404
- **THEN** LiteLLM is detected as unavailable

#### Scenario: Timeout
- **WHEN** the backend sends `GET {base_url}/v1/mcp/server` and the request times out after 5 seconds
- **THEN** LiteLLM is detected as unavailable

### Requirement: Two-endpoint server and tool discovery
The backend SHALL call `GET {openai_base_url}/v1/mcp/server` and `GET {openai_base_url}/v1/mcp/tools` in parallel. Server metadata (alias, description) SHALL come from the server endpoint. Tool names SHALL come from the tools endpoint. Tools SHALL be matched to servers by comparing the tool name prefix (before the first `-`) against known server aliases.

#### Scenario: Tools matched to servers
- **WHEN** the server endpoint returns a server with alias `argocd` and the tools endpoint returns tools `argocd-list_applications` and `argocd-get_application`
- **THEN** the `argocd` server entry includes `tools: ["list_applications", "get_application"]`

#### Scenario: Tool with no matching server
- **WHEN** the tools endpoint returns a tool `unknown-some_tool` but no server has alias `unknown`
- **THEN** the tool is omitted from the response

### Requirement: Sensitive data stripping
The backend SHALL strip sensitive fields from the LiteLLM server list response before returning to the frontend. Stripped fields: `env`, `credentials`, `command`, `args`, `static_headers`, `authorization_url`, `token_url`, `registration_url`, `extra_headers`. Only `alias`, `server_name`, `description`, and `tools` (from tool matching) SHALL be included in the response.

#### Scenario: Server with env secrets
- **WHEN** the LiteLLM API returns a server with `env: {"API_KEY": "secret123"}`
- **THEN** the Errand API response for that server does not contain the `env` field or its value

### Requirement: Save enabled LiteLLM MCP servers
The backend SHALL accept `PUT /api/settings` with a `litellm_mcp_servers` key containing a JSON array of server alias strings. The value SHALL be stored in the existing settings table.

#### Scenario: Enable two servers
- **WHEN** an admin sends `PUT /api/settings` with `{"litellm_mcp_servers": ["argocd", "perplexity"]}`
- **THEN** the `litellm_mcp_servers` setting is stored as `["argocd", "perplexity"]`

#### Scenario: Disable all servers
- **WHEN** an admin sends `PUT /api/settings` with `{"litellm_mcp_servers": []}`
- **THEN** the `litellm_mcp_servers` setting is stored as `[]`
