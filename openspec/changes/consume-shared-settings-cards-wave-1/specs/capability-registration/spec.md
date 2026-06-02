## MODIFIED Requirements

### Requirement: Server capability advertisement

The errand server's `/api/capabilities` endpoint SHALL advertise the following Wave 1 capability keys so that the shared library's settings cards display correctly:

- `system_prompt` — always advertised
- `mcp_servers` — always advertised
- `skills_git_repo` — always advertised
- `task_management` — always advertised
- `telemetry` — always advertised
- `cloud_storage` — advertised when at least one cloud-storage provider is configured/available in the server build
- `jira` — advertised when Jira webhook handling is enabled in the server build
- `litellm_mcp` — advertised when a LiteLLM proxy is detected at runtime

#### Scenario: Always-on capability advertised
- **WHEN** any client requests `GET /api/capabilities`
- **THEN** the response `capabilities` array SHALL include `"system_prompt"`, `"mcp_servers"`, `"skills_git_repo"`, `"task_management"`, `"telemetry"`

#### Scenario: Conditional capability advertised when feature enabled
- **WHEN** the LiteLLM proxy is detected at startup
- **THEN** `GET /api/capabilities` SHALL include `"litellm_mcp"` in the `capabilities` array

#### Scenario: Conditional capability omitted when feature disabled
- **WHEN** the LiteLLM proxy is not detected
- **THEN** `GET /api/capabilities` SHALL NOT include `"litellm_mcp"`
