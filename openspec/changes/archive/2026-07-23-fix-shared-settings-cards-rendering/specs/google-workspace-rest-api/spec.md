## ADDED Requirements

### Requirement: Google Workspace status endpoint
The errand-server SHALL expose `GET /api/google-workspace/status` requiring an authenticated user (consistent with the existing `/api/integrations` cloud-storage surface these adapters wrap; the settings UI is admin-gated in the frontend), returning JSON matching the library's `GoogleWorkspaceStatus` shape (connection state plus any granted-services/scope detail the card renders). Values SHALL derive from errand's existing Google Workspace machinery. The endpoint SHALL always return `application/json`.

#### Scenario: Not connected
- **WHEN** an admin calls `GET /api/google-workspace/status` and Google Workspace is not connected
- **THEN** the response is HTTP 200 `application/json` indicating a not-connected state

#### Scenario: Connected
- **WHEN** an admin calls `GET /api/google-workspace/status` and Google Workspace is connected
- **THEN** the response is HTTP 200 indicating connected, including the granted-services / scope detail the card displays

#### Scenario: Response is always JSON
- **WHEN** the endpoint is reached under any state
- **THEN** the `Content-Type` is `application/json` and the body parses as JSON (never `index.html`)

### Requirement: Google Workspace authorize endpoint
The errand-server SHALL expose `POST /api/google-workspace/authorize` requiring an authenticated user (consistent with the existing `/api/integrations` cloud-storage surface these adapters wrap; the settings UI is admin-gated in the frontend), returning JSON with a redirect URL matching the library's `GoogleWorkspaceAuthorizeResponse` shape. The card performs a top-level redirect to this URL.

#### Scenario: Authorize returns a redirect URL
- **WHEN** an admin calls `POST /api/google-workspace/authorize`
- **THEN** the response is HTTP 200 with a non-empty redirect URL for the Google OAuth flow

### Requirement: Google Workspace disconnect endpoint
The errand-server SHALL expose `DELETE /api/google-workspace` requiring an authenticated user (consistent with the existing `/api/integrations` cloud-storage surface these adapters wrap; the settings UI is admin-gated in the frontend). It SHALL remove the stored Google Workspace connection and return HTTP 204. It SHALL be idempotent.

#### Scenario: Disconnect existing connection
- **WHEN** an admin calls `DELETE /api/google-workspace` and a connection exists
- **THEN** the connection is removed and the endpoint returns HTTP 204

#### Scenario: Disconnect when not connected
- **WHEN** an admin calls `DELETE /api/google-workspace` and no connection exists
- **THEN** the endpoint returns HTTP 204 (idempotent)

### Requirement: Google Workspace capability implies a working status endpoint
The Google Workspace status endpoint SHALL be registered unconditionally, so that whenever the `google_workspace` capability is advertised by `GET /api/capabilities`, `GET /api/google-workspace/status` resolves to a real JSON endpoint (never the SPA catch-all). The `google_workspace` capability SHALL be advertised based on the deployment being configured for Google OAuth.

#### Scenario: Capability present implies working endpoint
- **WHEN** `GET /api/capabilities` includes `google_workspace`
- **THEN** `GET /api/google-workspace/status` returns HTTP 200 JSON (not an SPA fallback)
