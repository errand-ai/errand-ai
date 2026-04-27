## Purpose

Worker-side injection of cloud-storage MCP servers (currently OneDrive only) and the matching system-prompt instructions into the task-runner. Google Drive access is no longer an MCP server — it is provided via the `gws` CLI bundled in the task-runner image with a token injected as `GOOGLE_WORKSPACE_CLI_TOKEN` (see `google-workspace-integration` spec).

## Requirements

### Requirement: Cloud storage MCP server injection

The worker SHALL inject cloud storage MCP servers into the task-runner's `mcp.json` configuration when both conditions are met: (a) the provider's MCP server URL environment variable is set, and (b) valid credentials exist for that provider.

#### Scenario: OneDrive available and connected
- **WHEN** `ONEDRIVE_MCP_URL` env var is set
- **AND** OneDrive credentials exist in `PlatformCredential`
- **THEN** worker adds an `"onedrive"` entry to `mcp.json` with the URL and `Authorization: Bearer <token>` header

#### Scenario: MCP server URL not configured
- **WHEN** `ONEDRIVE_MCP_URL` env var is not set
- **THEN** worker does NOT inject OneDrive MCP server, regardless of credential status

#### Scenario: No credentials configured
- **WHEN** `ONEDRIVE_MCP_URL` is set but no OneDrive credentials exist
- **THEN** worker does NOT inject OneDrive MCP server

### Requirement: Cloud storage system prompt instructions

When at least one cloud storage MCP server is injected, the worker SHALL append instructions to the task-runner system prompt explaining the available cloud storage tools, the ETag-based optimistic concurrency pattern, and error handling.

#### Scenario: OneDrive injected
- **WHEN** worker injects the OneDrive MCP server
- **THEN** system prompt includes instructions about cloud storage tools, path-based file access, and the ETag pattern for concurrent writes

#### Scenario: No cloud storage injected
- **WHEN** no cloud storage MCP servers are injected
- **THEN** system prompt does NOT include cloud storage instructions

### Requirement: Profile-level cloud storage control

Cloud storage MCP servers SHALL participate in the existing `_profile_mcp_servers` filtering mechanism. Profiles can include or exclude `onedrive` like any other MCP server name.

#### Scenario: Profile excludes cloud storage
- **WHEN** a task profile has `_profile_mcp_servers: ["errand"]` (cloud storage not listed)
- **THEN** worker does NOT inject cloud storage MCP servers for tasks using that profile

#### Scenario: Profile with no MCP filter
- **WHEN** a task profile has no `_profile_mcp_servers` setting
- **THEN** cloud storage MCP servers are injected if available and connected (default behavior)
