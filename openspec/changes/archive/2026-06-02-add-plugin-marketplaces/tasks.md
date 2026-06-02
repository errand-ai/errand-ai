## 1. Database schema and migrations

- [x] 1.1 Add `Marketplace` SQLAlchemy model to `errand/models.py` matching the columns defined in `plugin-marketplaces/spec.md`
- [x] 1.2 Add `Plugin` SQLAlchemy model to `errand/models.py` matching the columns defined in `plugin-management/spec.md`
- [x] 1.3 Add `enabled_plugins` JSON column to the existing `TaskProfile` model
- [x] 1.4 Create Alembic migration `0XX_create_marketplaces_plugins.py` that creates both tables, adds the new task-profile column, and seeds the predefined Anthropic marketplace row (`anthropics/claude-plugins-official`, enabled=false, predefined=true). Verify reversibility.
- [x] 1.5 Register `plugin_poll_interval_seconds` (default 21600) in `errand/settings_registry.py`
- [x] 1.6 Run `docker compose -f testing/docker-compose.yml up --build` to confirm migration applies cleanly against a fresh database

## 2. Marketplace logic module

- [x] 2.1 Create `errand/plugin_marketplace.py` with Pydantic models for the marketplace.json schema (name, owner, plugins[], normalized plugin source)
- [x] 2.2 Implement source-type dispatcher accepting (`github` | `git` | `http` | `local`) and producing a path containing the fetched material
- [x] 2.3 Implement git fetch path using shallow clone + optional ref, reusing the existing `ssh_private_key` / `GIT_SSH_COMMAND` pattern from `errand/task_manager.py`
- [x] 2.4 Implement HTTPS fetch path using `httpx.AsyncClient`, threading the optional bearer credential from the linked credentials row
- [x] 2.5 Implement local fetch path that simply copies / symlinks the local source into the cache directory layout
- [x] 2.6 Implement marketplace sync operation: fetch → parse → update `cached_manifest`, `last_synced_at`, `last_sync_status`, `last_sync_error`
- [x] 2.7 Implement plugin install operation: resolve plugin source from marketplace manifest OR direct descriptor, fetch at pinned version, parse `plugin.json`, walk skills + MCP definitions, count ignored artifacts (commands/agents/hooks/lspServers/themes/output-styles/monitors/bin), persist the plugin row, write tree to the cache directory layout
- [x] 2.8 Implement plugin update operation: fetch new version into sibling directory, atomic swap, remove previous directory, update `installed_version`
- [x] 2.9 Implement plugin uninstall: drop row, remove cache subtree
- [x] 2.10 Unit tests under `errand/tests/test_plugin_marketplace.py` covering source-type dispatch, parse errors, sync error states, install with ignored artifacts, update happy path, uninstall

## 3. Cache and startup integration

- [x] 3.1 Define cache base path `/var/cache/errand/plugins/` and layout helpers (marketplace clone path, installed-plugin path for marketplace vs manual scope)
- [x] 3.2 Ensure base directory is created (parents=True, exist_ok=True) on server startup before the marketplace module is used
- [x] 3.3 Add eager startup warmer: on app startup, walk `enabled=true` plugins and refetch missing trees in parallel via `asyncio.Semaphore(4)`. Log per-plugin progress; do not abort on individual failures.
- [x] 3.4 Implement the per-plugin in-flight future map so tasks can `await` an in-progress warm rather than racing it
- [x] 3.5 Add a transcript `plugin_unavailable` event emitter for use when a task's required plugin failed to warm

## 4. Background poller

- [x] 4.1 Add background asyncio task to the task manager startup that loops every `plugin_poll_interval_seconds`, iterates enabled marketplaces, and invokes sync
- [x] 4.2 After each marketplace sync, walk plugin rows with matching `marketplace_id` and update `latest_available_version` and `last_checked_at` based on the new `cached_manifest`
- [x] 4.3 Add `update_available` derived field to the plugins API response (latest != installed and latest is not null)
- [x] 4.4 Handle `plugin_poll_interval_seconds = 0` by skipping the poller entirely after startup
- [x] 4.5 Unit test poller advances `latest_available_version`, leaves `installed_version` untouched, and survives sync exceptions

## 5. REST API endpoints

- [x] 5.1 Add `errand/plugin_routes.py` (or extend existing routes module) with admin-gated `/api/marketplaces` CRUD + resync + `<id>/plugins` listing
- [x] 5.2 Add admin-gated `/api/plugins` CRUD (install from marketplace, install manual, list, patch enabled, update, delete)
- [x] 5.3 Update profile endpoints in `errand/main.py` to accept/return `enabled_plugins`
- [x] 5.4 Validate `enabled_plugins` as a JSON array of UUID strings; HTTP 422 on invalid shape
- [x] 5.5 Reject DELETE on predefined marketplaces with HTTP 409
- [x] 5.6 Reject `plugin_poll_interval_seconds < 0` in the settings PUT endpoint
- [x] 5.7 Pytest coverage in `errand/tests/test_plugin_routes.py` for happy paths, validation failures, predefined protection, admin gating

## 6. Worker integration (task_manager.py)

- [x] 6.1 Extend `merge_skills` signature to accept `plugin_skills` and implement precedence DB > plugin > git > system with logged warnings on collisions
- [x] 6.2 Implement plugin-vs-plugin alphabetical tiebreak with a logged warning, surfacing `skill_conflicts` to the plugin row metadata so the API can return it
- [x] 6.3 Walk profile `enabled_plugins` (intersected with globally-enabled plugins) before tarball assembly; load each plugin's skills from the cache directory
- [x] 6.4 Extend `/workspace/mcp.json` builder to read each enabled plugin's `.mcp.json` (or inline `plugin.json` mcpServers, with inline winning), prefix every server key with `<plugin_name>__`, and merge into the existing dict
- [x] 6.5 Confirm admin-managed `settings.mcp_servers` and injected servers (errand, hindsight, playwright, onedrive) remain unprefixed
- [x] 6.6 Update the system prompt manifest builder to annotate plugin-sourced skills with their source plugin name
- [x] 6.7 Make the worker await plugin cache availability for any plugin referenced by the task's profile, emitting `plugin_unavailable` if a fetch ultimately fails
- [x] 6.8 Pytest coverage in `errand/tests/test_task_manager.py` for skill precedence (all four sources), plugin MCP namespacing, and bundle gating via `enabled_plugins`

## 7. Frontend — Agent Configuration extensions

- [x] 7.1 Add `Marketplaces` and `Plugins` sections to the Agent Configuration page in `frontend/src/`
- [x] 7.2 Implement Marketplaces section: list, add (with source type radio), edit, resync, remove (disabled for predefined), sync-status display
- [x] 7.3 Implement Plugins section: expandable cards showing skills/MCP/ignored, enable/disable toggle, update-available badge with Update action, conflict warnings, Install-from-Marketplace dialog, Install-Manually dialog, Remove action
- [x] 7.4 Add plugin-source badges to existing Skills and MCP Servers tabs (read-only entries with "from plugin: X")
- [x] 7.5 Add `plugin_poll_interval_seconds` form control (validated non-negative integer; "Polling disabled" when 0)
- [x] 7.6 Add plugin multi-select to Profile editor (Add and Edit forms) with expandable preview of contributed skills and MCP server pairs; load existing `enabled_plugins`; surface stale plugin references
- [x] 7.7 Update Profile summary cards to display "Plugins: N" / "Plugins: None"
- [x] 7.8 Vitest coverage in `frontend/src/` for the new components: marketplace list, plugin card, install dialogs, plugin multi-select

## 8. Smoke and end-to-end verification

- [x] 8.1 Bump `VERSION` per semver (minor — non-breaking feature addition)
- [x] 8.2 Local docker-compose smoke: enable the predefined Anthropic marketplace, sync, list its plugins, install one, enable it on a profile, run a task that uses one of its skills, verify skill text loads and any MCP servers appear under their namespaced names in `/workspace/mcp.json`
- [x] 8.3 Local docker-compose smoke: add a LiteLLM HTTP marketplace using a stored bearer credential, sync, install a plugin, verify HTTPS Authorization header was sent (capture via test stub)
- [x] 8.4 Local docker-compose smoke: manually install a plugin via `acme/plugins` GitHub shorthand, verify it appears with `marketplace_id=null`
- [x] 8.5 Local docker-compose smoke: trigger a plugin-vs-DB skill collision, observe DB wins; trigger a plugin-vs-plugin skill collision, observe alphabetical tiebreak and warning
- [x] 8.6 Local docker-compose smoke: set `plugin_poll_interval_seconds=0`, restart server, verify poller does not run; reset to 60 for fast testing, observe `latest_available_version` update on a stub manifest change
- [x] 8.7 Confirm `openspec validate add-plugin-marketplaces --strict` passes
