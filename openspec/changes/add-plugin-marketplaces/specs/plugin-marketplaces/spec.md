## ADDED Requirements

### Requirement: Marketplace data model
The backend SHALL persist marketplaces in a `marketplaces` table with the following columns: `id` (UUID, primary key), `name` (Text, unique, not null), `source_type` (Text, not null — one of `github`, `git`, `http`, `local`), `source_url` (Text, not null), `ref` (Text, nullable — git ref for git-based sources), `auth_credential_id` (UUID, nullable, FK to credentials), `enabled` (Boolean, not null, default true), `predefined` (Boolean, not null, default false), `cached_manifest` (JSONB, nullable — last successfully fetched marketplace.json), `last_synced_at` (TIMESTAMPTZ, nullable), `last_sync_status` (Text, nullable — `ok` or `error`), `last_sync_error` (Text, nullable), `created_at`/`updated_at` (TIMESTAMPTZ, server-defaults).

#### Scenario: Insert a marketplace
- **WHEN** a row is inserted with `name="internal-litellm"`, `source_type="http"`, `source_url="https://litellm.example/claude-code/marketplace.json"`
- **THEN** the row is persisted with a generated UUID, `enabled=true`, `predefined=false`, and null sync fields

#### Scenario: Unique name constraint
- **WHEN** two rows are inserted with the same `name`
- **THEN** the second insert raises a unique constraint violation

#### Scenario: Source type constraint
- **WHEN** a row is inserted with `source_type="ftp"`
- **THEN** the insert raises a check constraint or validation error

### Requirement: Seed predefined Anthropic marketplace
An Alembic migration SHALL insert a single row into `marketplaces` with `name="anthropics/claude-plugins-official"`, `source_type="github"`, `source_url="anthropics/claude-plugins-official"`, `enabled=false`, `predefined=true`, and the migration SHALL be reversible.

#### Scenario: Migration seeds Anthropic row
- **WHEN** the migration runs on an empty database
- **THEN** the `marketplaces` table contains exactly one row with `name="anthropics/claude-plugins-official"`, `enabled=false`, `predefined=true`

#### Scenario: Predefined rows cannot be deleted via API
- **WHEN** an admin calls `DELETE /api/marketplaces/<id>` for the predefined Anthropic row
- **THEN** the response is HTTP 409 Conflict with an explanation

#### Scenario: Predefined rows can be enabled and disabled
- **WHEN** an admin calls `PATCH /api/marketplaces/<id>` with `{"enabled": true}` for the predefined Anthropic row
- **THEN** the row is updated and the response is HTTP 200

### Requirement: Source-type-aware fetcher
The backend SHALL provide a fetcher that, given a marketplace row, retrieves the `marketplace.json` file from the appropriate source. For `github`, the fetcher SHALL shallow-clone `https://github.com/<source_url>.git` at the optional `ref`. For `git`, the fetcher SHALL shallow-clone `<source_url>` at the optional `ref`. For `http`, the fetcher SHALL issue an HTTPS GET to `<source_url>` (including a bearer token from the linked credential when present). For `local`, the fetcher SHALL read the file system path. Git operations SHALL use the existing `ssh_private_key` setting for SSH URLs.

#### Scenario: GitHub shorthand fetch
- **WHEN** the fetcher is invoked for a row with `source_type="github"`, `source_url="acme/plugins"`, `ref=null`
- **THEN** the fetcher runs `git clone --depth 1 https://github.com/acme/plugins.git <cache_dir>` and reads `<cache_dir>/.claude-plugin/marketplace.json`

#### Scenario: Git URL with ref
- **WHEN** the fetcher is invoked for a row with `source_type="git"`, `source_url="https://gitlab.com/x/y.git"`, `ref="release-1.2"`
- **THEN** the fetcher runs `git clone --depth 1 --branch release-1.2 https://gitlab.com/x/y.git <cache_dir>`

#### Scenario: HTTP source with bearer credential
- **WHEN** the fetcher is invoked for a row with `source_type="http"`, `source_url="https://litellm.example/marketplace.json"`, and `auth_credential_id` resolves to a bearer token `tok_xyz`
- **THEN** the fetcher issues `GET https://litellm.example/marketplace.json` with header `Authorization: Bearer tok_xyz` and parses the response body as JSON

#### Scenario: Local source
- **WHEN** the fetcher is invoked for a row with `source_type="local"`, `source_url="/srv/plugins/marketplace.json"`
- **THEN** the fetcher reads the file at that path and parses it as JSON

### Requirement: Marketplace manifest parsing
The backend SHALL parse the fetched `marketplace.json` into a typed structure containing `name` (string), `owner` (object, optional), `plugins` (array of plugin entries with `name`, `source`, optional `version`, optional `description`, optional `displayName`, optional `keywords`, optional `category`). Plugin `source` entries SHALL be normalized into a tagged shape accepting relative paths, GitHub objects, git URLs, HTTP URLs, and local paths. Unsupported source forms (e.g. npm) SHALL be retained but flagged as unsupported.

#### Scenario: Standard manifest parse
- **WHEN** a `marketplace.json` is fetched with `{"name": "acme", "plugins": [{"name": "p1", "source": "./p1"}, {"name": "p2", "source": {"source": "github", "repo": "acme/p2"}}]}`
- **THEN** the parsed structure exposes two plugins with normalized sources

#### Scenario: Unsupported source flagged
- **WHEN** a plugin entry has `source: {"source": "npm", "package": "x"}`
- **THEN** the parsed entry is present in the list with an `unsupported=true` flag and is rejected at install time

#### Scenario: Malformed manifest
- **WHEN** the fetched content cannot be parsed as the expected schema
- **THEN** the parse function raises a typed error and the caller records `last_sync_status="error"` with the error message

### Requirement: Marketplace sync operation
The backend SHALL provide a sync operation that, given a marketplace ID, invokes the fetcher, parses the manifest, persists `cached_manifest`, sets `last_synced_at` to the current UTC time, and sets `last_sync_status` to `ok` on success or `error` (with `last_sync_error` populated) on failure. Sync SHALL never modify already-installed plugins.

#### Scenario: Successful sync
- **WHEN** the sync operation is invoked for a marketplace with a reachable, valid manifest
- **THEN** `cached_manifest` is updated, `last_synced_at` is set, `last_sync_status="ok"`, `last_sync_error` is null

#### Scenario: Network failure during sync
- **WHEN** the sync operation is invoked and the fetcher times out or returns HTTP 5xx
- **THEN** `cached_manifest` is left unchanged, `last_sync_status="error"`, `last_sync_error` contains a descriptive message

#### Scenario: Authentication failure
- **WHEN** the sync operation is invoked for an HTTP marketplace and the linked credential returns HTTP 401
- **THEN** `last_sync_status="error"`, `last_sync_error` includes "401"

### Requirement: Marketplace CRUD API
The backend SHALL expose the following admin-only endpoints:

- `GET /api/marketplaces` — list all marketplaces with sync status and plugin count from `cached_manifest`.
- `POST /api/marketplaces` — create a new marketplace (body: `name`, `source_type`, `source_url`, optional `ref`, optional `auth_credential_id`). After insert, the backend SHALL trigger an initial sync.
- `PATCH /api/marketplaces/<id>` — update a subset of fields. Allowed: `enabled`, `name`, `source_url`, `ref`, `auth_credential_id`. Changes to `source_url`, `ref`, or `auth_credential_id` SHALL trigger an automatic resync.
- `DELETE /api/marketplaces/<id>` — delete a marketplace. SHALL refuse with HTTP 409 if `predefined=true`.
- `POST /api/marketplaces/<id>/resync` — enqueue an immediate resync.
- `GET /api/marketplaces/<id>/plugins` — return the parsed plugin list from `cached_manifest`.

All endpoints SHALL require admin role.

#### Scenario: List marketplaces
- **WHEN** an admin calls `GET /api/marketplaces` with the seeded Anthropic row plus one custom row
- **THEN** the response is a JSON array of 2 marketplace objects including their sync status

#### Scenario: Create marketplace triggers initial sync
- **WHEN** an admin calls `POST /api/marketplaces` with valid fields and the source is reachable
- **THEN** the row is persisted and `last_synced_at` is populated by the initial sync

#### Scenario: Patch source_url triggers resync
- **WHEN** an admin calls `PATCH /api/marketplaces/<id>` with `{"source_url": "new/repo"}`
- **THEN** the row is updated and an automatic resync runs

#### Scenario: Delete refused for predefined
- **WHEN** an admin calls `DELETE /api/marketplaces/<id>` for the predefined Anthropic row
- **THEN** the response is HTTP 409

#### Scenario: Manual resync
- **WHEN** an admin calls `POST /api/marketplaces/<id>/resync`
- **THEN** the sync operation is invoked and the response is HTTP 202

#### Scenario: List plugins for marketplace
- **WHEN** an admin calls `GET /api/marketplaces/<id>/plugins` after a successful sync
- **THEN** the response is a JSON array of plugin entries from `cached_manifest`

#### Scenario: Non-admin rejected
- **WHEN** a non-admin user calls any `/api/marketplaces` endpoint
- **THEN** the response is HTTP 403
