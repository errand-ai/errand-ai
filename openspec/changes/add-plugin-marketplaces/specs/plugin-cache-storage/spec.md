## ADDED Requirements

### Requirement: Plugin cache directory layout
The server SHALL store plugin-related files under the base directory `/var/cache/errand/plugins/`, organized as follows:

- `/var/cache/errand/plugins/marketplaces/<marketplace_name>/` — marketplace clones (for git-based sources) and downloaded `marketplace.json` files (for HTTP sources).
- `/var/cache/errand/plugins/installed/<scope>/<plugin_name>/<version>/` — installed plugin trees, where `<scope>` is the marketplace name when `marketplace_id` is non-null and `manual` otherwise.

The base path SHALL be writable by the server process. The contents of this directory SHALL be ephemeral and SHALL NOT be backed by persistent storage.

#### Scenario: Layout for marketplace plugin
- **WHEN** plugin `slack-toolkit@1.2.0` from marketplace `acme-public` is installed
- **THEN** the contents are written under `/var/cache/errand/plugins/installed/acme-public/slack-toolkit/1.2.0/`

#### Scenario: Layout for manual plugin
- **WHEN** a manually installed plugin named `research-pack` at version `0.5.0` is added
- **THEN** the contents are written under `/var/cache/errand/plugins/installed/manual/research-pack/0.5.0/`

#### Scenario: Marketplace clone location
- **WHEN** marketplace `acme-public` is synced
- **THEN** its clone resides under `/var/cache/errand/plugins/marketplaces/acme-public/`

### Requirement: Eager parallel re-fetch on server startup
On server startup, after the database connection is established and before the task manager dequeues its first task, the server SHALL iterate over all plugin rows with `enabled=true`, verify the cached tree exists at the expected path, and re-fetch any missing or stale tree from the original source. Fetches SHALL run in parallel bounded by an asyncio semaphore (default concurrency: 4). Fetch failures SHALL be logged but SHALL NOT abort startup.

#### Scenario: Startup with enabled plugins missing from cache
- **WHEN** the server starts and 5 plugin rows have `enabled=true` and none of them have cached trees
- **THEN** the server fetches all 5 in parallel (up to 4 concurrently) and logs progress

#### Scenario: Startup with all caches present
- **WHEN** all enabled plugins already have valid trees on disk
- **THEN** the server validates their presence and does not re-fetch

#### Scenario: One fetch fails at startup
- **WHEN** one of the enabled plugins fails to fetch (network error)
- **THEN** the error is logged with the plugin name, the other plugins are still fetched, and the server continues startup

#### Scenario: Disabled plugins not fetched
- **WHEN** a plugin row has `enabled=false`
- **THEN** its cache is not warmed at startup even if absent

### Requirement: Task blocks on plugin fetch availability
When a task using a profile that lists an enabled plugin in `enabled_plugins` begins execution and that plugin's cache is being fetched, the task SHALL wait for the fetch to complete before proceeding. If the fetch ultimately fails, the task SHALL run with the plugin's contents omitted and an event SHALL be emitted to the task's transcript noting the omission.

#### Scenario: Task waits for in-progress fetch
- **WHEN** plugin `slow-fetch` is being warmed at startup and a task referencing it begins
- **THEN** the task waits for the warm to complete before assembling its tarball

#### Scenario: Fetch fails before task uses plugin
- **WHEN** plugin `broken` failed startup warm and a task referencing it begins
- **THEN** the task proceeds without that plugin's contents and emits a `plugin_unavailable` event to the transcript

### Requirement: Uninstall removes cache subtree
When a plugin is uninstalled (`DELETE /api/plugins/<id>`), the server SHALL recursively remove `/var/cache/errand/plugins/installed/<scope>/<plugin_name>/<installed_version>/`. If the plugin name's parent directory becomes empty, the server MAY remove that directory.

#### Scenario: Uninstall removes plugin tree
- **WHEN** plugin `slack-toolkit@1.2.0` (scope `acme-public`) is uninstalled
- **THEN** the directory `/var/cache/errand/plugins/installed/acme-public/slack-toolkit/1.2.0/` is removed

#### Scenario: Uninstall preserves other versions
- **WHEN** a plugin has versions `1.2.0` and `1.3.0` on disk and only `1.3.0` is the installed row
- **THEN** uninstalling that plugin removes only `1.3.0/` (the `1.2.0/` orphan is left for a future cleanup pass)

### Requirement: Update operation swaps version atomically
When a plugin update is invoked, the server SHALL fetch the new version into a sibling directory under the same `<plugin_name>/` parent, validate the fetch succeeded, then atomically swap a `current` symlink (or update the `installed_version` row) so concurrent task assembly never sees a half-written tree. The previous version directory SHALL be removed after the swap.

#### Scenario: Update swap leaves no partial state
- **WHEN** plugin `slack-toolkit` is updated from `1.2.0` to `1.3.0` and the new fetch succeeds
- **THEN** at no point during the operation does a task observe a directory that mixes `1.2.0` and `1.3.0` files

#### Scenario: Update aborts on fetch failure
- **WHEN** the fetch of the new version fails
- **THEN** the previous version directory is preserved and `installed_version` is unchanged
