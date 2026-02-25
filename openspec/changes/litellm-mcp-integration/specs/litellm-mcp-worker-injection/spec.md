## ADDED Requirements

### Requirement: Inject LiteLLM MCP gateway into task runner
The worker SHALL inject a `litellm` entry into the task runner's MCP server configuration when the `litellm_mcp_servers` setting contains one or more server aliases and `openai_base_url` is configured. The entry SHALL point to `{openai_base_url}/mcp` with `Authorization: Bearer {openai_api_key}` and `x-mcp-servers: {comma-separated aliases}` headers.

#### Scenario: Two servers enabled
- **WHEN** `litellm_mcp_servers` is `["argocd", "perplexity"]` and `openai_base_url` is `https://litellm.coward.cloud`
- **THEN** the task runner's mcp.json includes `{"mcpServers": {"litellm": {"url": "https://litellm.coward.cloud/mcp", "headers": {"Authorization": "Bearer <key>", "x-mcp-servers": "argocd,perplexity"}}}}`

#### Scenario: No servers enabled
- **WHEN** `litellm_mcp_servers` is `[]`
- **THEN** no `litellm` entry is added to mcp.json

#### Scenario: No openai_base_url configured
- **WHEN** `litellm_mcp_servers` is `["argocd"]` but `openai_base_url` is empty
- **THEN** no `litellm` entry is added to mcp.json

### Requirement: LiteLLM MCP server does not conflict with existing entries
The worker SHALL NOT overwrite an existing `litellm` key in the user's manual MCP server configuration. If the user has manually configured a `litellm` entry, the worker SHALL skip automatic injection.

#### Scenario: Manual litellm entry exists
- **WHEN** the user has manually configured `{"mcpServers": {"litellm": {"url": "http://custom:4000/mcp"}}}` and `litellm_mcp_servers` is `["argocd"]`
- **THEN** the manual entry is preserved and no automatic injection occurs

### Requirement: Worker reads litellm_mcp_servers setting
The worker SHALL read the `litellm_mcp_servers` setting from the database alongside other settings during task processing. The setting SHALL default to an empty list if not present.

#### Scenario: Setting present in database
- **WHEN** the worker reads settings and `litellm_mcp_servers` is stored as `["argocd"]`
- **THEN** the worker uses `["argocd"]` for LiteLLM MCP injection

#### Scenario: Setting absent from database
- **WHEN** the worker reads settings and `litellm_mcp_servers` has no database entry
- **THEN** the worker uses `[]` (empty list) and skips LiteLLM MCP injection
