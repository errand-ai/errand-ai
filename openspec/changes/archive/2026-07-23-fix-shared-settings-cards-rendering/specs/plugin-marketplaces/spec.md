## MODIFIED Requirements

### Requirement: Marketplace sync operation
The backend SHALL provide a sync operation that, given a marketplace ID, invokes the fetcher, parses the manifest, persists `cached_manifest`, sets `last_synced_at` to the current UTC time, and sets `last_sync_status` to `ok` on success or `error` (with `last_sync_error` populated) on failure. Sync SHALL never modify already-installed plugins.

Sync (including `POST /api/marketplaces/<id>/resync`) SHALL capture fetch-layer failures — notably a `git clone` failure — into `last_sync_status="error"` with a descriptive, actionable `last_sync_error` (a clean category such as "git clone failed", not the generic "unexpected error"; sensitive detail such as the source URL stays in logs), rather than raising an uncaught exception. Such a failure MUST NOT return HTTP 500 to the caller and MUST NOT corrupt the plugins listing or leave a partially-synced marketplace in a state that breaks `GET /api/plugins`.

#### Scenario: Successful sync
- **WHEN** the sync operation is invoked for a marketplace with a reachable, valid manifest
- **THEN** `cached_manifest` is updated, `last_synced_at` is set, `last_sync_status="ok"`, `last_sync_error` is null

#### Scenario: Network failure during sync
- **WHEN** the sync operation is invoked and the fetcher times out or returns HTTP 5xx
- **THEN** `cached_manifest` is left unchanged, `last_sync_status="error"`, `last_sync_error` contains a descriptive message

#### Scenario: Authentication failure
- **WHEN** the sync operation is invoked for an HTTP marketplace and the linked credential returns HTTP 401
- **THEN** `last_sync_status="error"`, `last_sync_error` includes "401"

#### Scenario: git clone failure captured and categorized, not raised
- **WHEN** a resync is invoked and the underlying `git clone` fails
- **THEN** the operation returns without raising; `last_sync_status="error"` and `last_sync_error` is a clean category (e.g. "git clone failed (see server logs)"), not "unexpected error (see server logs)"
- **AND** the caller receives a non-500 response

#### Scenario: A broken plugin does not break the plugins listing
- **WHEN** a marketplace is in an error / partially-synced state and one installed plugin's on-disk tree is missing
- **THEN** `GET /api/plugins` continues to return HTTP 200 with the readable plugins (the broken plugin is returned degraded, with a `load_error`)
