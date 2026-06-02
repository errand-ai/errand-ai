## Purpose

See proposal: add-plugin-marketplaces.

## Requirements

### Requirement: Plugin data model
The backend SHALL persist installed plugins in a `plugins` table with the following columns: `id` (UUID, primary key), `marketplace_id` (UUID, nullable, FK to marketplaces with `ON DELETE SET NULL`), `plugin_name` (Text, not null), `source_type` (Text, nullable — required when `marketplace_id` is null), `source_url` (Text, nullable — required when `marketplace_id` is null), `ref` (Text, nullable), `auth_credential_id` (UUID, nullable, FK to credentials), `installed_version` (Text, not null), `latest_available_version` (Text, nullable), `enabled` (Boolean, not null, default false), `manifest` (JSONB, nullable — cached parsed plugin.json), `ignored_artifacts` (JSONB, nullable — list of `{type, count}` objects), `installed_at` (TIMESTAMPTZ, server-default), `last_checked_at` (TIMESTAMPTZ, nullable). The combination (`marketplace_id`, `plugin_name`) SHALL be unique. For manual installs (`marketplace_id` IS NULL), `plugin_name` alone SHALL be unique.

#### Scenario: Install a marketplace plugin
- **WHEN** a row is inserted with `marketplace_id=<id>`, `plugin_name="slack-toolkit"`, `installed_version="1.2.0"`
- **THEN** the row is persisted with `enabled=false`, `latest_available_version` initially equal to `installed_version`

#### Scenario: Install a manual plugin
- **WHEN** a row is inserted with `marketplace_id=null`, `source_type="github"`, `source_url="acme/research-pack"`, `plugin_name="research-pack"`, `installed_version="0.5.0"`
- **THEN** the row is persisted and identifies the plugin by `source_url` for refresh

#### Scenario: Unique constraint on marketplace+name
- **WHEN** a row is inserted with the same `marketplace_id` and `plugin_name` as an existing row
- **THEN** the insert raises a unique constraint violation

### Requirement: Plugin install operation
The backend SHALL provide an install operation that, given a marketplace ID and plugin name (and optional version), or a direct source descriptor, fetches the plugin contents at the requested version, parses the optional `.claude-plugin/plugin.json`, identifies skills under `skills/<name>/SKILL.md` and MCP server definitions in `.mcp.json` or inline `mcpServers`, counts ignored artifact types (commands, agents, hooks, lspServers, themes, output-styles, monitors, bin), persists the plugin row, and writes the plugin tree to disk. Installation SHALL NOT enable the plugin automatically.

#### Scenario: Install from marketplace
- **WHEN** the install operation is invoked with marketplace ID and `plugin_name="slack-toolkit"`, `version="1.2.0"` and the marketplace's cached manifest lists that plugin
- **THEN** the plugin contents are fetched from the source listed in the manifest, the row is created with `installed_version="1.2.0"` and `enabled=false`, the manifest is cached, and the contents are written under the plugin cache directory

#### Scenario: Manual install via GitHub shorthand
- **WHEN** the install operation is invoked with `source_type="github"`, `source_url="acme/research-pack"`, `ref=null`
- **THEN** the plugin is fetched, its name is read from the cloned `plugin.json` (or directory name if absent), and the row is created with `marketplace_id=null`

#### Scenario: Manual install via full git URL
- **WHEN** the install operation is invoked with `source_type="git"`, `source_url="https://gitlab.com/x/research.git"`, `ref="v0.5.0"`
- **THEN** the plugin is fetched at that ref and the row records the same source for future refresh

#### Scenario: Ignored artifacts recorded
- **WHEN** the install operation processes a plugin containing 3 hooks and 2 commands
- **THEN** the row's `ignored_artifacts` is `[{"type": "hooks", "count": 3}, {"type": "commands", "count": 2}]` and an info-level log message names the ignored artifact types

#### Scenario: Install with unsupported source rejected
- **WHEN** the install operation is invoked for a plugin whose marketplace entry uses an unsupported source (e.g. npm)
- **THEN** the operation fails with a typed error and no plugin row is created

### Requirement: Plugin enable / disable
The backend SHALL allow toggling `plugins.enabled` via `PATCH /api/plugins/<id>` with `{"enabled": true|false}`. Disabling a plugin SHALL NOT remove its cache, but tasks SHALL stop including its contents in new tarballs.

#### Scenario: Enable a plugin
- **WHEN** an admin calls `PATCH /api/plugins/<id>` with `{"enabled": true}`
- **THEN** the row's `enabled` is set to true and the response is HTTP 200

#### Scenario: Disable a plugin
- **WHEN** an admin calls `PATCH /api/plugins/<id>` with `{"enabled": false}`
- **THEN** the row's `enabled` is set to false and the plugin tree remains on disk

### Requirement: Plugin uninstall
The backend SHALL allow uninstalling a plugin via `DELETE /api/plugins/<id>`. Uninstall SHALL remove the row and the corresponding cache subtree from disk.

#### Scenario: Uninstall plugin
- **WHEN** an admin calls `DELETE /api/plugins/<id>` for an installed plugin
- **THEN** the row is deleted, the on-disk cache subtree is removed, and the response is HTTP 204

#### Scenario: Uninstall referenced by profile
- **WHEN** a plugin is uninstalled while listed in some profile's `enabled_plugins`
- **THEN** the row is deleted and the next task using that profile silently skips the missing plugin reference (logged at info level)

### Requirement: Plugin update operation
The backend SHALL provide `POST /api/plugins/<id>/update` that, given a plugin row with `latest_available_version > installed_version`, re-fetches the plugin at the new version, replaces the on-disk tree atomically, updates `manifest` and `ignored_artifacts`, and sets `installed_version` to the new version. The plugin's `enabled` state SHALL be preserved across updates.

#### Scenario: Update to newer version
- **WHEN** a plugin row has `installed_version="1.2.0"`, `latest_available_version="1.3.0"`, and an admin calls `POST /api/plugins/<id>/update`
- **THEN** the plugin is re-fetched at `1.3.0`, the on-disk tree is replaced, the row's `installed_version` becomes `1.3.0`, and `enabled` is unchanged

#### Scenario: Update when already current
- **WHEN** `installed_version == latest_available_version` and update is invoked
- **THEN** the response is HTTP 200 with a no-op message; no fetch is performed

#### Scenario: Update fails mid-fetch
- **WHEN** the fetch for the new version fails
- **THEN** the on-disk tree at the previous version is preserved and the row is unchanged

### Requirement: Plugin-vs-plugin skill name collision handling
When two enabled plugins contribute skills with the same name, the worker SHALL select the skill from the plugin whose `plugin_name` sorts earliest alphabetically. The losing plugin's skill SHALL be omitted and a warning SHALL be logged. The API SHALL surface the collision on both plugins' UI metadata so the admin can see the conflict.

#### Scenario: Two plugins define `post-message`
- **WHEN** plugins `slack-toolkit` and `team-chat` both define a skill named `post-message` and both are enabled
- **THEN** the `slack-toolkit` version is included and the `team-chat` version is omitted; a warning is logged naming both plugins

#### Scenario: Conflict surfaced in plugin metadata
- **WHEN** the worker resolves a collision
- **THEN** the next `GET /api/plugins` response includes a `skill_conflicts` field on each affected plugin row listing the conflicting skill name and the other plugin's name

### Requirement: Plugin list API
The backend SHALL expose `GET /api/plugins` returning all installed plugins with their `id`, `plugin_name`, `marketplace_id` (or `null`), `installed_version`, `latest_available_version`, `enabled`, skill name list (from manifest), MCP server name list with both raw and namespaced names, `ignored_artifacts` summary, and any `skill_conflicts` from the last worker resolution.

#### Scenario: List installed plugins
- **WHEN** an admin calls `GET /api/plugins` with two installed plugins
- **THEN** the response is a JSON array of 2 plugin objects with the fields above

#### Scenario: Plugin contributing nothing
- **WHEN** a plugin defines no skills and no MCP servers
- **THEN** the response includes the plugin with empty `skills` and `mcp_servers` arrays
