## Purpose

See proposal: add-plugin-marketplaces.

## Requirements

### Requirement: Background poller resyncs marketplaces on interval
The task manager SHALL start a background asyncio task on server startup that, every `plugin_poll_interval_seconds` seconds (default `21600`), iterates over all `enabled=true` marketplaces and invokes the marketplace sync operation. Sync failures SHALL be logged but SHALL NOT abort the loop.

#### Scenario: Poller invokes sync per enabled marketplace
- **WHEN** the poller wakes up with 2 enabled and 1 disabled marketplace
- **THEN** the sync operation is called twice (once per enabled marketplace) and the disabled one is skipped

#### Scenario: Sync failure does not stop the loop
- **WHEN** the first marketplace sync raises an exception
- **THEN** the error is logged, the second marketplace's sync still runs, and the loop sleeps until the next interval

#### Scenario: Disabled poller via zero interval
- **WHEN** `plugin_poll_interval_seconds` is `0`
- **THEN** the poller does not run after startup and only manual resync requests trigger sync

### Requirement: Poller updates latest_available_version on installed plugins
After each marketplace sync, the poller SHALL walk every plugin row whose `marketplace_id` matches the synced marketplace, read the latest version from the marketplace's `cached_manifest`, and set `latest_available_version` and `last_checked_at` on the plugin row. The poller SHALL NOT modify `installed_version`.

#### Scenario: Newer version detected
- **WHEN** the synced manifest lists `slack-toolkit@1.3.0` and the installed plugin row has `installed_version="1.2.0"`
- **THEN** the plugin row's `latest_available_version` becomes `1.3.0` and `last_checked_at` is updated

#### Scenario: Plugin no longer in manifest
- **WHEN** the synced manifest no longer lists a previously installed plugin
- **THEN** the plugin row is left unchanged (its cache remains valid for the pinned version) and the absence is logged at info level

#### Scenario: Manually installed plugins
- **WHEN** a plugin row has `marketplace_id=null` (manual install)
- **THEN** the marketplace poller does not touch it (manual plugins are refreshed by their own per-plugin check or by admin action)

### Requirement: Manual resync triggers immediate update
When an admin invokes `POST /api/marketplaces/<id>/resync`, the backend SHALL run the sync operation immediately (out of band of the poller schedule) and update plugin `latest_available_version` rows for that marketplace synchronously before returning.

#### Scenario: Manual resync updates plugin row latest version
- **WHEN** an admin invokes resync for a marketplace whose manifest now lists newer plugin versions
- **THEN** the affected plugin rows have updated `latest_available_version` values before the API response returns

### Requirement: Update-available signal surfaced in API
The `GET /api/plugins` response SHALL include an `update_available` boolean on each plugin row, computed as `latest_available_version != installed_version AND latest_available_version IS NOT NULL`.

#### Scenario: Update available
- **WHEN** a plugin row has `installed_version="1.2.0"`, `latest_available_version="1.3.0"`
- **THEN** the API row includes `update_available: true`

#### Scenario: No update available
- **WHEN** a plugin row has `installed_version="1.2.0"`, `latest_available_version="1.2.0"`
- **THEN** the API row includes `update_available: false`

#### Scenario: Latest unknown
- **WHEN** a plugin row has `latest_available_version=null`
- **THEN** the API row includes `update_available: false`
