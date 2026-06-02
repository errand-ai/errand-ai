## Context

Errand currently composes the per-task workspace from three independent skill sources (DB rows, a single configured git repo, and a baked-in `system-skills/` tree) and an MCP server set assembled from `settings.mcp_servers`, profile filters, and a handful of injected servers (errand, hindsight, playwright, onedrive). The task manager packs these into a tarball and a `/workspace/mcp.json` file before each task runs.

Claude Code's plugin marketplaces let an admin subscribe to a named source (GitHub `owner/repo`, full git URL, HTTP JSON endpoint, or local path), browse the listed plugins, and install versioned bundles. Each plugin can contain skills, MCP server definitions, and other artifacts errand has no analogue for (commands, agents, hooks, LSP servers, themes, output-styles, monitors, executables). LiteLLM specifically can serve a `marketplace.json` over HTTP, making it a useful private-marketplace host.

This change introduces marketplaces and plugins as new admin-managed concepts, persists them in the database, and feeds plugin-sourced skills and MCP servers into the existing tarball / `mcp.json` pipelines without disturbing what already works. The change does not implement plugin commands, agents, hooks, LSP servers, or other non-skill / non-MCP artifacts — those are explicitly out of scope.

Stakeholders:
- Errand admins (configure marketplaces, install plugins, gate per-profile)
- Errand task-runner agents (consume skills and MCP servers transparently)
- Plugin authors / marketplace operators (no API contract from errand; they continue to publish for Claude Code)

## Goals / Non-Goals

**Goals:**

- Add a first-class "marketplace" entity (CRUD + sync) supporting four source types: GitHub shorthand, git URL, HTTP JSON, local path.
- Add a first-class "plugin" entity with pinned versions, manual or marketplace-sourced.
- Auto-namespace plugin-sourced MCP servers as `<plugin>__<server>` to eliminate collision risk against admin-managed `settings.mcp_servers` and against other plugins.
- Merge plugin-sourced skills into the existing skill tarball with precedence `DB > plugin > git > system`.
- Gate plugin contents per-task-profile at the bundle level (`enabled_plugins` array on profiles).
- Poll marketplaces on a global interval and surface available-update badges; admin opts in to each update.
- Seed the Anthropic official marketplace (`anthropics/claude-plugins-official`) as a predefined, disabled-by-default row so existing Claude Code users see it immediately.
- Cache marketplace and plugin contents on disk under `/var/cache/errand/plugins/`, eagerly re-fetching on startup to keep first-task latency predictable.

**Non-Goals:**

- Supporting plugin commands, agents, hooks, LSP servers, themes, output-styles, monitors, or `bin/` executables.
- Rewriting skill markdown to remap MCP server name references after namespacing (we rely on the LLM's tool listing instead).
- Cross-marketplace plugin dependencies (`allowCrossMarketplaceDependenciesOn`).
- Per-plugin authentication separate from the parent marketplace's credential.
- Replacing or deprecating the existing `skills_git_repo` mechanism.
- Auto-applying version upgrades. Admin always confirms via the UI.
- Persistent (PVC-backed) plugin cache. The cache is ephemeral by design.

## Decisions

### Decision 1: Reimplement marketplace resolution in Python rather than shell out to `claude` CLI

Errand's server is a Python FastAPI process and the existing git skills loader already shells out to `git`. Bundling Node and the `claude` CLI into the server image to drive plugin install would inflate the image, couple us to CLI shape changes, and provide no auth benefit (Claude Code relies on git credential helpers, while our private-marketplace requirement specifically needs bearer-token-on-HTTPS support for LiteLLM).

We will:
- Parse `marketplace.json` directly using Pydantic models matching Claude's published schema.
- Clone git sources with `git clone --depth 1` (and `git pull --ff-only` on refresh), reusing the existing `ssh_private_key`/`git_ssh_hosts` mechanism plus a new per-marketplace credential reference for HTTPS bearer auth.
- Resolve plugin sources declared in `marketplace.json` (relative path inside the marketplace repo, GitHub shorthand, separate git URL, HTTP URL, or local path) using the same dispatcher.

**Alternatives considered:**
- *Shell out to `claude` CLI*: rejected — heavyweight, brittle, doesn't solve the LiteLLM auth case.
- *Implement only HTTP marketplaces*: rejected — would break the user expectation that errand handles the same shapes Claude Code does (`anthropics/claude-plugins-official` is a GitHub repo).

### Decision 2: Auto-namespace plugin MCP servers but DO NOT rewrite skill content

Plugin-sourced MCP servers are renamed to `<plugin-name>__<server-name>` when written into `/workspace/mcp.json`. Admin-managed `settings.mcp_servers` entries and errand-injected servers (`errand`, `hindsight`, `playwright`, `onedrive`) are not renamed.

We will NOT rewrite the markdown of plugin-bundled skills to remap MCP server references. Skill text remains byte-identical to what the plugin author published. The LLM discovers tools via the standard `mcp__<server>__<tool>` listing, so a skill that says "use the Slack MCP server" still reaches `mcp__slack-toolkit__slack__post_message` through inference rather than a literal name match.

**Alternatives considered:**
- *No namespacing*: rejected — admin would have to manually resolve any name clash between two plugins or between a plugin and `settings.mcp_servers`.
- *Namespace + rewrite skill text*: rejected — markdown rewriting is brittle (false positives, formatting drift) and breaks the implicit contract that skill content is the plugin author's source of truth.
- *Refuse to enable on conflict*: rejected for MCPs because it would force admins to argue with bundle authors. Acceptable for skills, but covered by the precedence chain (DB > plugin) which subsumes most real-world cases.

### Decision 3: Bundle-level per-profile gating via `enabled_plugins`

Task profiles get a new `enabled_plugins` JSON column listing installed plugin IDs. A task using a given profile sees the union of:
- DB skills permitted by `profile.skill_ids`
- Git skills, if `profile.include_git_skills` is true
- All system skills whose registry conditions match the task context
- Skills and MCP servers from every plugin whose ID appears in `profile.enabled_plugins`

There is no per-profile filter that slices *inside* a plugin. A plugin is an atomic unit at the profile boundary. The Plugins UI card and the profile editor display each plugin's contributed skills and MCP server names so admins can see what's included or excluded.

**Alternatives considered:**
- *Synthesize stable UUIDs for plugin skills and expose them in the existing `skill_ids` filter*: rejected — granular filtering inside a bundle breaks the published-as-a-unit contract and inflates the per-profile UI.
- *Default `enabled_plugins=None` meaning "all enabled plugins"*: rejected — explicit lists make profile behavior predictable and review-able.

### Decision 4: Ephemeral cache, eager re-fetch on startup

Plugin cache lives at `/var/cache/errand/plugins/` inside the server container. The directory is not backed by a PVC. On server startup, the task manager (or a startup hook) walks the `plugins` table for `enabled = true` rows and fetches each in parallel using a bounded `asyncio.Semaphore`.

Tasks block on plugin availability — if a plugin is enabled but not yet fetched at the moment a task starts, the task waits for that plugin's fetch to complete. We rely on eager warming to make this rare.

**Alternatives considered:**
- *PVC-backed cache*: rejected — adds operational burden (PVC provisioning, RWX for multi-replica), inconsistent with how `skills_git_repo` is handled today.
- *Lazy fetch on first task*: rejected — cold-start latency for the first task becomes unpredictable, especially if multiple plugins must be fetched serially.
- *Background fetch on startup without blocking first task*: considered for the implementation phase; can be added later if eager parallel fetch proves too slow.

### Decision 5: Global poll interval; admin opts in to updates

A single `plugin_poll_interval_seconds` setting (default `21600` = 6h) drives a background asyncio task that re-fetches each marketplace's manifest, walks installed plugins, and updates `plugins.latest_available_version`. The poller never modifies `installed_version`.

The UI surfaces an "update available" badge on plugin cards when `latest_available_version > installed_version`. Clicking *Update* triggers a sync POST that re-fetches the plugin at the new version, swaps it on disk, and bumps `installed_version`.

**Alternatives considered:**
- *Per-marketplace polling cadence*: rejected as premature complexity — admins can manually Resync when they need a refresh sooner.
- *Auto-apply updates*: rejected — version churn could silently introduce skill or MCP changes mid-flight.

### Decision 6: Predefined marketplaces seeded by migration, undeletable

The Anthropic marketplace (`anthropics/claude-plugins-official`) is inserted by the same Alembic migration that creates the `marketplaces` table. The row carries `predefined = true`. The API rejects DELETE on predefined rows but allows toggling `enabled` and triggering `resync`. This same mechanism reserves the option to seed a future ErrandAI marketplace.

**Alternatives considered:**
- *Hardcoded constant in app code*: rejected — would not show in the UI alongside user-added marketplaces, would require special-case rendering.
- *Optional ENV var to enable Anthropic*: rejected — less discoverable than a row that's visible-but-disabled.

### Decision 7: Marketplace and plugin source-type resolution

A single source-type enum drives both marketplaces and plugins:

| `source_type` | Fetcher | Format of `source_url`                       |
|---------------|---------|----------------------------------------------|
| `github`      | git     | `owner/repo` (optional `#ref` suffix)        |
| `git`         | git     | full git URL (optional `#ref` suffix)        |
| `http`        | HTTPS   | URL returning JSON (marketplace) or git ref  |
| `local`       | fs copy | absolute filesystem path                     |

Inside a marketplace's plugin list, plugin sources can use the same set, plus the conventional relative-path form (`./plugins/my-plugin`) which resolves against the marketplace repo root. We do not support npm sources; if a marketplace lists one, the plugin is shown but flagged unsupported.

### Decision 8: API surface

REST endpoints under `/api/marketplaces` and `/api/plugins`, admin-only (existing role check):

```
GET    /api/marketplaces                  list with sync status + cached plugin counts
POST   /api/marketplaces                  add (body: name, source_url, source_type, ref?, auth_credential_id?)
PATCH  /api/marketplaces/<id>             toggle enabled, change ref / credential
DELETE /api/marketplaces/<id>             refused for predefined rows
POST   /api/marketplaces/<id>/resync      enqueue immediate refresh
GET    /api/marketplaces/<id>/plugins     list plugins from cached manifest (for UI install flow)

GET    /api/plugins                       list installed plugins with skill/MCP counts + ignored artifacts
POST   /api/plugins                       install — either {marketplace_id, plugin_name, version}
                                                  or {source_type, source_url, ref?, auth_credential_id?}
PATCH  /api/plugins/<id>                  enable/disable
POST   /api/plugins/<id>/update           bump installed_version to latest_available_version
DELETE /api/plugins/<id>                  uninstall and remove from cache
```

Existing profile endpoints gain `enabled_plugins` in their JSON payload.

### Decision 9: Worker integration points

Two small changes inside `errand/task_manager.py`:

1. After git skills are loaded, walk every plugin in `enabled_plugins` for the resolved profile, load its skill set, and pass to `merge_skills(db_skills, plugin_skills, git_skills, system_skills)` with the new precedence order.
2. Build `/workspace/mcp.json` from `settings.mcp_servers` then iterate plugin MCP definitions, prefixing keys with `<plugin-name>__` before adding them. Injected servers go last and are never renamed.

All other task-manager behavior (advisory lock, runtime selection, env var injection) remains unchanged.

## Risks / Trade-offs

- **[Skill text references an MCP server by literal name and fails after namespacing]** → Mitigation: log the original server names and the namespaced equivalents in the install confirmation; document in the user-facing release notes. The LLM's tool list typically lets it figure out the mapping; for stubborn cases the admin can fork the plugin.
- **[Marketplace HTTPS endpoint disappears or rate-limits]** → Mitigation: cached `marketplace.json` survives in the DB row; sync errors are surfaced in the UI but don't break already-installed plugins. The poller backs off on consecutive failures.
- **[Eager startup fetch slow with many enabled plugins]** → Mitigation: parallel `asyncio.Semaphore` (initial value e.g. 4). Tasks block on plugin availability rather than crashing, so a slow startup degrades to "first tasks queue briefly" not failure.
- **[Plugin author publishes a malicious `.mcp.json`]** → Mitigation: admin explicitly enables each plugin and the install flow lists every server name and stdio command shown in the UI before confirm. No silent autoload.
- **[Predefined Anthropic marketplace row drift if upstream renames the repo]** → Mitigation: the seed migration is reversible; a follow-up migration can update the URL.
- **[GitHub `owner/repo` shorthand collides with a name the admin already used]** → Mitigation: marketplace `name` is enforced unique at DB level and surfaced in the UI; the admin overrides on add.
- **[Disk pressure from many cached plugins]** → Mitigation: cache lives under a known path; uninstall always removes its tree. We can add a size watchdog later if needed.
- **[`enabled_plugins` references a plugin that was uninstalled]** → Mitigation: on profile resolution, missing plugin IDs are silently skipped and an info-level message is logged. UI shows stale references with a "removed" badge.

## Migration Plan

1. **Alembic migration `0XX_create_marketplaces_and_plugins.py`**:
   - Create `marketplaces` (id UUID PK, name TEXT UNIQUE NOT NULL, source_type TEXT NOT NULL, source_url TEXT NOT NULL, ref TEXT NULL, auth_credential_id UUID NULL FK, enabled BOOL NOT NULL DEFAULT true, predefined BOOL NOT NULL DEFAULT false, cached_manifest JSONB NULL, last_synced_at TIMESTAMPTZ NULL, last_sync_status TEXT NULL, last_sync_error TEXT NULL, created_at/updated_at TIMESTAMPTZ).
   - Create `plugins` (id UUID PK, marketplace_id UUID NULL FK, plugin_name TEXT NOT NULL, source_type TEXT NULL, source_url TEXT NULL, ref TEXT NULL, auth_credential_id UUID NULL FK, installed_version TEXT NOT NULL, latest_available_version TEXT NULL, enabled BOOL NOT NULL DEFAULT false, manifest JSONB NULL, ignored_artifacts JSONB NULL, installed_at/last_checked_at TIMESTAMPTZ, UNIQUE(marketplace_id, plugin_name, installed_version)).
   - Add `task_profiles.enabled_plugins` JSONB NULL (treated as empty list when null).
   - Seed `marketplaces` with one row: `name='anthropics/claude-plugins-official'`, `source_type='github'`, `source_url='anthropics/claude-plugins-official'`, `enabled=false`, `predefined=true`.
   - Register setting `plugin_poll_interval_seconds` (integer default 21600) in `settings_registry.py`.
2. **Code rollout (single PR or short series)**:
   - Models, migration, REST endpoints (gated behind role checks).
   - `plugin_marketplace.py` module: source-type dispatcher, fetcher, parser, installer, refresher, poller startup hook.
   - Task manager hooks: skill merge, MCP namespacing, eager cache warm.
   - Frontend: Marketplaces and Plugins sections in Agent Configuration; badges in Skills and MCP Servers tabs; plugin multi-select in profile editor.
3. **Smoke test on staging**:
   - Add Anthropic marketplace by toggling `enabled=true`, sync, install one plugin, enable it on a profile, run a task.
   - Add LiteLLM marketplace via HTTP URL with a bearer credential, install a plugin, verify namespacing.
4. **Rollback**: the migration is reversible (drops both tables and the column). No data corruption risk — plugin cache is on-disk and ephemeral, profile changes degrade gracefully (`enabled_plugins` ignored when column missing).

## Open Questions

- **Plugin source `git-subdir`**: Claude marketplaces can declare a plugin as living in a subdirectory of a larger repo. Should we support this in v1, or only top-of-tree plugins? Leaning yes (cheap to implement), but defer if it complicates the fetcher.
- **Credential rotation**: when an admin changes the bearer token on a marketplace, do we re-resync immediately? Suggested behavior: yes, on PATCH that touches `auth_credential_id` or `source_url`.
- **What happens to a task already running when its enabled plugin gets disabled?** The task-runner already has the tarball; we don't tear it down mid-flight. New tasks see the updated state.
