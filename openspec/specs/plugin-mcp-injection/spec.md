## Purpose

See proposal: add-plugin-marketplaces.

## Requirements

### Requirement: Worker discovers plugin-sourced MCP servers from cache
For each plugin row with `enabled=true` (filtered by per-profile `enabled_plugins`), the worker SHALL read MCP server definitions from one of two sources, in order of precedence: (1) an inline `mcpServers` object in `.claude-plugin/plugin.json`, (2) a `.mcp.json` file at the plugin root. If both are present, the inline `mcpServers` SHALL win. The discovered structure SHALL preserve the original server names.

#### Scenario: Plugin with .mcp.json
- **WHEN** a plugin's cache directory contains `.mcp.json` with `{"slack": {"command": "...", ...}}`
- **THEN** the worker discovers one MCP server named `slack`

#### Scenario: Plugin with inline mcpServers
- **WHEN** a plugin's `plugin.json` contains `"mcpServers": {"slack": {...}}` and no `.mcp.json`
- **THEN** the worker discovers one MCP server named `slack`

#### Scenario: Both inline and .mcp.json present
- **WHEN** a plugin has both `plugin.json` with inline `mcpServers` and a separate `.mcp.json`
- **THEN** the inline definition wins and the `.mcp.json` is ignored

#### Scenario: Plugin with no MCP servers
- **WHEN** a plugin has neither inline `mcpServers` nor `.mcp.json`
- **THEN** the worker contributes zero MCP servers for that plugin

### Requirement: Plugin MCP server names auto-namespaced
When writing `/workspace/mcp.json`, the worker SHALL prefix every plugin-sourced MCP server name with `<plugin_name>__`, where `plugin_name` is the value from the `plugins.plugin_name` column. Server values (command, args, env, etc.) SHALL be copied verbatim.

#### Scenario: Single plugin namespacing
- **WHEN** plugin `slack-toolkit` defines server `slack`
- **THEN** `/workspace/mcp.json` contains a key `slack-toolkit__slack` with the original server config

#### Scenario: Multiple plugins, same internal server name
- **WHEN** plugins `slack-toolkit` and `team-chat` each define a server named `slack`
- **THEN** `/workspace/mcp.json` contains two distinct keys, `slack-toolkit__slack` and `team-chat__slack`

#### Scenario: Namespacing applies to all server keys
- **WHEN** a plugin defines servers `slack` and `webhooks`
- **THEN** both keys are namespaced in the output

### Requirement: Admin-managed and injected MCP servers not renamed
The worker SHALL NOT apply namespacing to MCP servers sourced from `settings.mcp_servers`, profile `mcp_servers`, or errand-injected servers (`errand`, `hindsight`, `playwright`, `onedrive`). Those servers SHALL be written with their bare names.

#### Scenario: Admin-managed slack not renamed
- **WHEN** `settings.mcp_servers` includes a `slack` entry
- **THEN** `/workspace/mcp.json` contains a key `slack` (no prefix)

#### Scenario: Plugin and admin both define slack
- **WHEN** `settings.mcp_servers` has `slack` and plugin `slack-toolkit` also has `slack`
- **THEN** `/workspace/mcp.json` contains both `slack` (admin) and `slack-toolkit__slack` (plugin) with no collision

#### Scenario: Errand-injected MCP not renamed
- **WHEN** the worker injects the `errand` MCP server
- **THEN** `/workspace/mcp.json` contains a key `errand` with no prefix, even if a plugin coincidentally named `errand` exists

### Requirement: Plugin skill markdown NOT rewritten
The worker SHALL NOT modify the textual content of any plugin-sourced `SKILL.md` (or sibling skill files) when namespacing MCP server names. The skill content is delivered to the workspace byte-identical to what was fetched from the plugin source.

#### Scenario: Skill references MCP server by name
- **WHEN** a plugin's SKILL.md contains the string "use the slack MCP server" and the plugin namespaces `slack` to `slack-toolkit__slack`
- **THEN** the SKILL.md content in `/workspace/skills/<name>/SKILL.md` still contains the literal string "use the slack MCP server"

### Requirement: Plugin MCP servers disabled when plugin disabled
When a plugin row has `enabled=false`, none of its MCP servers SHALL appear in `/workspace/mcp.json` for any task.

#### Scenario: Disabled plugin contributes no MCP servers
- **WHEN** a plugin row has `enabled=false` and defines an MCP server
- **THEN** the namespaced server is absent from `/workspace/mcp.json`
