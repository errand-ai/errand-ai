## Why

Errand can already load Agent Skills from the database, a single configured git repository, and an in-image system skills tree, and it can load MCP servers from settings and a few injected sources (errand, hindsight, playwright, onedrive). Claude Code's plugin marketplace ecosystem bundles skills and MCP servers together as versioned, distributable plugins — including the option to host private marketplaces via LiteLLM. Today, an admin wanting to make a curated bundle of Claude-compatible skills and MCPs available to errand's task-runner must vend each one separately. This change brings plugin marketplaces in as a first-class source so admins can subscribe to one or more marketplaces (public, private, or manually-pinned plugins) and pull bundled skills + MCP servers into the agent runtime with the same configurability they have today.

## What Changes

- Add a new **marketplace** concept: a named source (GitHub `owner/repo` shorthand, full git URL, HTTP URL serving `marketplace.json`, or local path) with optional auth credentials, persisted in a new `marketplaces` table.
- Add a new **plugin** concept: a versioned bundle installed from a marketplace OR added manually with a direct source. Persisted in a new `plugins` table with pinned `installed_version` and observed `latest_available_version`.
- Seed a predefined, undeletable, **disabled-by-default** marketplace row for `anthropics/claude-plugins-official` so existing Claude users see it immediately.
- Make plugin contents extend two existing pipelines:
  - **Skills**: a plugin's `skills/<name>/SKILL.md` entries flow into the existing skill tarball with precedence `DB > plugin > git > system`. Plugin-vs-plugin name collisions resolve deterministically by alphabetical plugin name with a logged warning.
  - **MCP servers**: a plugin's `.mcp.json` (or inline `mcpServers` in `plugin.json`) entries are auto-namespaced as `<plugin-name>__<server-name>` and merged into `/workspace/mcp.json` alongside `settings.mcp_servers` and injected servers. The admin-managed `settings.mcp_servers` and errand-injected servers are NOT renamed. Skill text inside plugins is NOT rewritten; the LLM discovers namespaced tools through the standard tool list.
- Silently ignore plugin artifacts errand has no analogue for (commands, agents, hooks, LSP servers, themes, output-styles, monitors, bin/). Log an info-level message at install time and surface a summary count in the Plugins UI card.
- Add a **background marketplace poller** that refetches every configured marketplace at a global cadence (new setting `plugin_poll_interval_seconds`, default 6h) and updates `plugins.latest_available_version`. Admins can also trigger a manual **Resync** per marketplace. Version updates are surfaced as a badge in the UI but never auto-applied.
- Add **bundle-level per-profile plugin gating**: task profiles gain an `enabled_plugins` column listing which installed plugins are exposed to tasks using that profile. The profile editor previews which skills and MCP servers each plugin contributes.
- **Disk cache is ephemeral.** Marketplace clones and installed plugin contents live under `/var/cache/errand/plugins/`. On server startup, all enabled plugins are eagerly re-fetched in parallel so the first task does not pay cold-start latency.
- Extend the **Agent Configuration** settings page with two new sections: *Plugin Marketplaces* (list/add/remove/resync) and *Plugins* (install-from-marketplace dropdown, install-manually git source field, per-plugin enable toggle, version-update prompt). Plugin-sourced skills and MCP servers appear in the existing Skills and MCP Servers tabs with a "from plugin: X" badge.

## Capabilities

### New Capabilities

- `plugin-marketplaces`: Marketplace data model, source-type resolution (GitHub shorthand vs git vs HTTP vs local), manifest fetch/parse, credential binding, predefined marketplace seeding, manual and automatic resync.
- `plugin-management`: Plugin data model, install/uninstall, version pinning, ignored-artifact summary, plugin-vs-plugin collision handling, manual install via direct git/owner-repo source.
- `plugin-update-poller`: Background loop driven by `plugin_poll_interval_seconds` that refreshes marketplace manifests and updates `latest_available_version` on installed plugin rows; emits an `update_available` signal observable by the UI.
- `plugin-skill-injection`: Worker-side merging of plugin-sourced skills into the existing skill tarball with the new precedence chain `DB > plugin > git > system`, including alphabetical tiebreak for plugin-vs-plugin name collisions.
- `plugin-mcp-injection`: Worker-side merging of plugin-sourced MCP servers into `/workspace/mcp.json` with `<plugin>__<server>` namespacing applied to plugin-sourced entries only.
- `plugin-cache-storage`: Disk cache layout under `/var/cache/errand/plugins/` for marketplace clones and installed plugin contents; eager parallel re-fetch on server startup.
- `plugin-settings-ui`: Frontend additions to the Agent Configuration page (Marketplaces section, Plugins section, per-plugin expandable card showing skills/MCPs/ignored artifacts, update-available badge, manual install dialog).

### Modified Capabilities

- `agent-skill-loading`: The skill manifest precedence chain changes from `DB > git > system` to `DB > plugin > git > system`, and the system prompt skill manifest enumerates plugin-sourced skills alongside existing sources.
- `task-profile-model`: Add an `enabled_plugins` column (JSON list of plugin IDs) to the `task_profiles` table; existing rows default to an empty list.
- `task-profile-settings-ui`: Add a plugin multi-select to the profile editor that previews each plugin's contributed skills and MCP servers based on the cached plugin manifest.
- `task-profile-worker-resolution`: When the worker resolves a task profile, only skills and MCP servers from plugins listed in `enabled_plugins` are included in that task's tarball and `/workspace/mcp.json`. An empty `enabled_plugins` list excludes all plugin contents.
- `settings-registry`: Register the new `plugin_poll_interval_seconds` setting (integer, default 21600) with admin-only write access.

## Impact

- **Code**:
  - `errand/models.py`: new `Marketplace` and `Plugin` SQLAlchemy models; new `task_profiles.enabled_plugins` column.
  - `errand/alembic/versions/`: new migration(s) for the two tables, the new task-profile column, and a predefined-marketplace seed row.
  - `errand/task_manager.py`: plugin-source skill discovery, namespaced MCP merging, `enabled_plugins` resolution in the per-task settings dict, eager cache warm on startup.
  - New module e.g. `errand/plugin_marketplace.py`: marketplace fetch/parse logic, plugin install/refresh, background poller, credential resolution.
  - `errand/main.py` or new `errand/plugin_routes.py`: REST endpoints for marketplaces, plugins, manual resync, version updates.
  - `frontend/src/`: new components for Marketplaces and Plugins sections, badges on existing Skills and MCP Servers tabs, plugin multi-select in profile editor.
- **APIs**:
  - New: `GET/POST/DELETE /api/marketplaces`, `POST /api/marketplaces/<id>/resync`, `GET/POST/DELETE /api/plugins`, `POST /api/plugins/<id>/update`, `PATCH /api/plugins/<id>` (enable/disable).
  - Modified: `GET/PUT /api/profiles/<id>` to include `enabled_plugins`.
- **Dependencies**: none new beyond what's already in errand (Python `httpx` for HTTP fetches, system `git` for git sources, already used).
- **Settings**: new key `plugin_poll_interval_seconds` (integer, default 21600). New encrypted-credential rows may be created for private marketplace auth, reusing the existing credentials infrastructure.
- **Disk**: requires writable `/var/cache/errand/plugins/` inside the server container (ephemeral; not a PVC).
- **Helm**: no values changes required by default; the existing server image carries the new code.
- **Compatibility**: non-breaking. Profiles created before this change have `enabled_plugins=[]`, behaving identically to today. The Anthropic marketplace row is seeded but disabled.
- **Out of scope**: handling of plugin commands, agents, hooks, LSP servers, themes, output-styles, monitors, or `bin/` artifacts; per-plugin auth distinct from the parent marketplace; cross-marketplace plugin dependencies declared via `allowCrossMarketplaceDependenciesOn`.
