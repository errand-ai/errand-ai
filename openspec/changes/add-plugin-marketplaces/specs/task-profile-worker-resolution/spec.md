## ADDED Requirements

### Requirement: Worker resolves enabled_plugins for plugin content gating
When the worker resolves a task profile, it SHALL read the profile's `enabled_plugins` column. Plugin-sourced skills and plugin-sourced MCP servers SHALL be included in the task's tarball and `/workspace/mcp.json` ONLY for plugins whose IDs appear in `enabled_plugins`. A null or empty `enabled_plugins` SHALL cause the worker to omit all plugin-sourced content for that task.

#### Scenario: Profile with two enabled plugins
- **WHEN** a profile has `enabled_plugins = ["abc-123", "def-456"]` and both plugin rows have `enabled=true`
- **THEN** the worker includes skills and MCP servers from those two plugins in the task tarball and `/workspace/mcp.json`

#### Scenario: Plugin in enabled_plugins but globally disabled
- **WHEN** a profile has `enabled_plugins = ["abc-123"]` and the plugin row has `enabled=false`
- **THEN** the worker omits that plugin's contents and logs an info-level message

#### Scenario: Empty enabled_plugins
- **WHEN** a profile has `enabled_plugins = []` (or null) and one or more plugins are globally enabled
- **THEN** the worker omits all plugin-sourced skills and MCP servers from the task tarball and `mcp.json`

#### Scenario: enabled_plugins references missing plugin
- **WHEN** a profile has `enabled_plugins = ["deleted-id"]` and no plugin row matches that ID
- **THEN** the worker silently skips that ID, logs an info-level message, and proceeds with the remaining valid plugins

#### Scenario: Default profile (no profile attached)
- **WHEN** a task has `profile_id=null`
- **THEN** the worker omits all plugin-sourced content (default profile has no `enabled_plugins`)

### Requirement: Plugin contents always apply at bundle granularity
The worker SHALL NOT filter plugin-sourced skills or MCP servers by individual name. Inclusion is determined entirely by membership in `profile.enabled_plugins` AND the plugin row's global `enabled` flag.

#### Scenario: Plugin skill not in profile skill_ids
- **WHEN** a plugin contributes skills `post-message` and `react-to-thread`, and the profile's `skill_ids` is `["unrelated-db-skill-uuid"]`
- **THEN** both plugin skills are still included because plugin gating uses `enabled_plugins` not `skill_ids`

#### Scenario: Plugin MCP not in profile mcp_servers
- **WHEN** a plugin contributes a namespaced MCP server `slack-toolkit__slack`, and the profile's `mcp_servers` is `["gmail"]`
- **THEN** the plugin's namespaced MCP server is included alongside `gmail` because plugin gating is bundle-level
