## ADDED Requirements

### Requirement: MCP config translated for Claude Code
Before invoking the CLI, the task-runner SHALL read the MCP configuration at `MCP_CONFIGURATION_PATH` (`/workspace/mcp.json`), add `"type": "http"` to every server entry that does not already declare a `type`, write the result to a separate file, and pass that file to `--mcp-config` together with `--strict-mcp-config`. The canonical `/workspace/mcp.json` SHALL NOT be modified, and the server SHALL continue to generate exactly one MCP configuration for all image variants.

Errand's configuration is already `{"mcpServers": {<name>: {"url": ..., "headers": {...}}}}`, which is the shape Claude Code accepts apart from the missing transport discriminator.

#### Scenario: Type discriminator injected
- **WHEN** `/workspace/mcp.json` contains `{"mcpServers": {"errand": {"url": "http://errand:8000/mcp", "headers": {"Authorization": "Bearer k"}}}}`
- **THEN** the translated config passed to `--mcp-config` contains `{"type": "http", "url": "http://errand:8000/mcp", "headers": {"Authorization": "Bearer k"}}` for `errand`

#### Scenario: Existing type preserved
- **WHEN** a server entry already declares `"type": "sse"`
- **THEN** the translated entry retains `"type": "sse"`

#### Scenario: Headers preserved
- **WHEN** a server entry carries an `Authorization` header
- **THEN** the header is present unchanged in the translated entry

#### Scenario: Canonical config untouched
- **WHEN** translation completes
- **THEN** `/workspace/mcp.json` is byte-identical to what the server injected

#### Scenario: Empty configuration
- **WHEN** `/workspace/mcp.json` declares no servers
- **THEN** the translated config declares no servers and claude is invoked without error

#### Scenario: Strict mode requested
- **WHEN** the task-runner invokes claude with a translated config
- **THEN** the argument list includes `--strict-mcp-config` so no other MCP configuration source is consulted

### Requirement: MCP server registration is verified
After the `system` / `init` event arrives, the task-runner SHALL compare the `mcp_servers` it reports against the servers in the translated configuration and SHALL emit an `error` event naming any configured server that is absent or reports a non-connected status.

Verification is mandatory because Claude Code silently discards server entries it cannot interpret: a config missing the `type` discriminator yields an empty `mcp_servers` list and no diagnostic, which would otherwise present as a task that inexplicably ignored its tools.

#### Scenario: Missing server reported
- **WHEN** the translated config declares `errand` and `playwright` but the init event reports only `errand`
- **THEN** an `error` event is emitted naming `playwright` as not registered

#### Scenario: Failed server reported
- **WHEN** the init event reports `{"name": "errand", "status": "failed"}`
- **THEN** an `error` event is emitted naming `errand` and its status

#### Scenario: All servers registered
- **WHEN** every configured server appears in the init event with a connected status
- **THEN** no MCP verification error event is emitted

### Requirement: Translation applies only to delegated runs
The translated configuration SHALL be produced only when the task-runner is delegating to the CLI. A run that uses the standard Python agent loop SHALL consume `/workspace/mcp.json` unchanged.

#### Scenario: Standard loop unaffected
- **WHEN** the task-runner executes a task through the standard agent loop
- **THEN** no translated MCP config file is produced and the agent connects using `/workspace/mcp.json`
