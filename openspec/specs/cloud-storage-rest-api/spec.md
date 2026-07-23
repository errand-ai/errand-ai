# cloud-storage-rest-api Specification

## Purpose
TBD - created by archiving change fix-shared-settings-cards-rendering. Update Purpose after archive.
## Requirements
### Requirement: Cloud storage status endpoint
The errand-server SHALL expose `GET /api/cloud-storage/status` requiring an authenticated user (consistent with the existing `/api/integrations` cloud-storage surface these adapters wrap; the settings UI is admin-gated in the frontend), returning JSON matching the library's `CloudStorageStatus` shape: `{ "connected": boolean, "provider": string|null, "account": string|null, "authorize_url": string|null }`. The endpoint SHALL derive its values from errand's existing cloud-storage (OneDrive) machinery. It SHALL always return `application/json` (never fall through to the SPA catch-all).

#### Scenario: Not connected
- **WHEN** an admin calls `GET /api/cloud-storage/status` and no cloud-storage provider is connected
- **THEN** the response is HTTP 200 `application/json` with `connected: false`
- **AND** `authorize_url` is `null` (the status endpoint does not build an authorize URL; the SPA obtains it from `POST /api/cloud-storage/authorize`)

#### Scenario: Connected
- **WHEN** an admin calls `GET /api/cloud-storage/status` and a provider is connected
- **THEN** the response is HTTP 200 with `connected: true`, `provider` set (e.g. `"onedrive"`), and `account` set to the connected account identifier when known

#### Scenario: Response is always JSON
- **WHEN** the endpoint is reached under any state
- **THEN** the `Content-Type` is `application/json` and the body parses as JSON (the request never resolves to `index.html`)

### Requirement: Cloud storage authorize endpoint
The errand-server SHALL expose `POST /api/cloud-storage/authorize` requiring an authenticated user (consistent with the existing `/api/integrations` cloud-storage surface these adapters wrap; the settings UI is admin-gated in the frontend), returning JSON matching the library's `CloudStorageAuthorizeResponse` shape: `{ "authorize_url": string }`. The URL SHALL initiate the cloud-storage connection flow appropriate to the deployment.

#### Scenario: Authorize returns a URL
- **WHEN** an admin calls `POST /api/cloud-storage/authorize`
- **THEN** the response is HTTP 200 with a non-empty `authorize_url` the SPA can redirect the browser to

### Requirement: Cloud storage disconnect endpoint
The errand-server SHALL expose `DELETE /api/cloud-storage` requiring an authenticated user (consistent with the existing `/api/integrations` cloud-storage surface these adapters wrap; the settings UI is admin-gated in the frontend). It SHALL remove the stored cloud-storage connection and return HTTP 204. It SHALL be idempotent.

#### Scenario: Disconnect existing connection
- **WHEN** an admin calls `DELETE /api/cloud-storage` and a connection exists
- **THEN** the connection is removed and the endpoint returns HTTP 204

#### Scenario: Disconnect when not connected
- **WHEN** an admin calls `DELETE /api/cloud-storage` and no connection exists
- **THEN** the endpoint returns HTTP 204 (idempotent)

### Requirement: Cloud storage capability implies a working status endpoint
The cloud-storage status endpoint SHALL be registered unconditionally, so that whenever the `cloud_storage` capability is advertised by `GET /api/capabilities`, `GET /api/cloud-storage/status` resolves to a real JSON endpoint (never the SPA catch-all). The `cloud_storage` capability SHALL be advertised based on the deployment being configured for OneDrive.

#### Scenario: Capability present implies working endpoint
- **WHEN** `GET /api/capabilities` includes `cloud_storage`
- **THEN** `GET /api/cloud-storage/status` returns HTTP 200 JSON (not an SPA fallback)

#### Scenario: OneDrive not configured
- **WHEN** the deployment is not configured for OneDrive (no OneDrive MCP URL)
- **THEN** `cloud_storage` is absent from `GET /api/capabilities` and the `CloudStorageCard` does not render

