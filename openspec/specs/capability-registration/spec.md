## ADDED Requirements

### Requirement: Capability detection from runtime configuration

The server SHALL determine its capabilities from runtime configuration state at the time of cloud connection. Capabilities SHALL be re-evaluated on each connection (including reconnections).

Capability derivation rules:
- `tasks` — always present
- `settings` — always present
- `mcp-servers` — always present (MCP server management is a core feature)
- `voice-input` — present when a `transcription_model` setting is configured AND LLM client is available
- `task-profiles` — always present (the feature exists even if no profiles are defined)
- `litellm-mcp` — present when LiteLLM proxy is detected (the `litellm_mcp_servers` setting endpoint returns `available: true`)
- `platforms` — always present (platform credential management is a core feature)

#### Scenario: Full capability set

- **WHEN** the server has a transcription model configured and LiteLLM proxy is available
- **THEN** the capabilities list includes all capabilities: `["tasks", "settings", "mcp-servers", "voice-input", "task-profiles", "litellm-mcp", "platforms"]`

#### Scenario: Minimal capability set

- **WHEN** the server has no transcription model and no LiteLLM proxy
- **THEN** the capabilities list includes: `["tasks", "settings", "mcp-servers", "task-profiles", "platforms"]`

### Requirement: Server version from VERSION file

The server version reported in the `register` message SHALL be read from the `VERSION` file at the project root. If the file does not exist or is unreadable, the version SHALL be reported as `"unknown"`.

#### Scenario: Version file exists

- **WHEN** the `VERSION` file contains `0.14.0`
- **THEN** the register message includes `"server_version": "0.14.0"`

#### Scenario: Version file missing

- **WHEN** the `VERSION` file does not exist
- **THEN** the register message includes `"server_version": "unknown"`
