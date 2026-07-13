## Requirements

### Requirement: Server capability advertisement

`errand/capabilities.py::get_capabilities()` is the single capability source, re-evaluated on each cloud connection (including reconnections). Its result SHALL be advertised to BOTH consumers so they gate cards identically:
- errand-cloud, via the WebSocket `register` message (`cloud_client._send_register`);
- the locally-served SPA, via a public `GET /api/capabilities` route backed by the same function.

`get_capabilities()` SHALL advertise the following Wave 1 keys in **snake_case** (the shared `@errand-ai/ui-components` settings cards gate on these exact spellings; the legacy kebab-case keys `mcp-servers`/`litellm-mcp` are renamed, not duplicated):

- `system_prompt` — always advertised
- `mcp_servers` — always advertised
- `skills_git_repo` — always advertised
- `task_management` — always advertised
- `telemetry` — always advertised
- `cloud_storage` — advertised when the OneDrive MCP URL is configured in the server build
- `jira` — advertised when the Jira platform integration is registered
- `litellm_mcp` — advertised when a LiteLLM proxy is detected at runtime (a `litellm` provider row exists, or `OPENAI_BASE_URL` is set)

Pre-Wave-1 keys (`tasks`, `settings`, `task-profiles`, `platforms`, and conditional `voice-input`) SHALL remain advertised for other errand-cloud features.

#### Scenario: Always-on capability advertised (both channels)
- **WHEN** `get_capabilities()` is evaluated (for cloud registration or `GET /api/capabilities`)
- **THEN** the `capabilities` array SHALL include `"system_prompt"`, `"mcp_servers"`, `"skills_git_repo"`, `"task_management"`, `"telemetry"`
- **AND** SHALL NOT include the legacy kebab spelling `"mcp-servers"`

#### Scenario: Conditional capability advertised when feature enabled
- **WHEN** a LiteLLM proxy is detected
- **THEN** the `capabilities` array SHALL include `"litellm_mcp"`

#### Scenario: Conditional capability omitted when feature disabled
- **WHEN** no LiteLLM proxy is detected
- **THEN** the `capabilities` array SHALL NOT include `"litellm_mcp"`

### Requirement: Server version from VERSION file

The server version reported in the `register` message SHALL be read from the `VERSION` file at the project root. If the file does not exist or is unreadable, the version SHALL be reported as `"unknown"`.

#### Scenario: Version file exists

- **WHEN** the `VERSION` file contains `0.14.0`
- **THEN** the register message includes `"server_version": "0.14.0"`

#### Scenario: Version file missing

- **WHEN** the `VERSION` file does not exist
- **THEN** the register message includes `"server_version": "unknown"`
