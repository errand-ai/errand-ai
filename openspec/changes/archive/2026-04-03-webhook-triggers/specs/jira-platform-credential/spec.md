## Purpose

Jira Cloud credential storage, management, and verification using the PlatformCredential model, with a dedicated API for connecting and disconnecting Jira.

## ADDED Requirements

### Requirement: Jira credential data structure
The system SHALL store Jira credentials in a `PlatformCredential` record with `platform_id="jira"`. The encrypted data SHALL contain: `cloud_id` (string, the Atlassian Cloud instance ID), `api_token` (string, a scoped Bearer token for the Jira REST API), `site_url` (string, e.g. "https://company.atlassian.net"), and `service_account_email` (string, the email address of the service account used for API calls).

#### Scenario: Credential fields stored
- **WHEN** Jira credentials are saved with cloud_id "abc-123", api_token "tok_xxx", site_url "https://acme.atlassian.net", and service_account_email "bot@acme.com"
- **THEN** all four fields are encrypted and stored in the PlatformCredential record with platform_id "jira"

### Requirement: Save Jira credentials API
The system SHALL expose `PUT /api/credentials/jira` requiring the `admin` role. The endpoint SHALL accept a JSON body with fields: `cloud_id`, `api_token`, `site_url`, and `service_account_email`. The endpoint SHALL verify the token by calling `GET /rest/api/3/myself` against `https://api.atlassian.com/ex/jira/{cloud_id}/` with `Authorization: Bearer {api_token}`. If verification succeeds, the endpoint SHALL encrypt the credentials, upsert the PlatformCredential record, set status to "connected" and `last_verified_at` to now, and return the connection status with the display name from the verification response. If verification fails, the endpoint SHALL return HTTP 400 with the error reason.

#### Scenario: Save valid Jira credentials
- **WHEN** an admin sends `PUT /api/credentials/jira` with valid credentials
- **THEN** the system verifies the token against Jira, stores the encrypted credentials, and responds with `{"platform_id": "jira", "status": "connected", "display_name": "Bot Account", "site_url": "https://acme.atlassian.net"}`

#### Scenario: Save invalid Jira credentials
- **WHEN** an admin sends `PUT /api/credentials/jira` with an invalid api_token
- **THEN** the verification call to `/rest/api/3/myself` fails and the endpoint returns HTTP 400 with `{"detail": "Credential verification failed: ..."}`

#### Scenario: Non-admin user
- **WHEN** a non-admin user sends `PUT /api/credentials/jira`
- **THEN** the response is HTTP 403

### Requirement: Get Jira credential status API
The system SHALL expose `GET /api/credentials/jira` requiring the `admin` role. The endpoint SHALL return the connection status and `site_url` from the stored credential. The endpoint SHALL NOT return the `api_token` value. If no credentials are stored, the endpoint SHALL return status "disconnected".

#### Scenario: Credentials configured
- **WHEN** an admin requests `GET /api/credentials/jira` and Jira credentials exist
- **THEN** the response includes `{"platform_id": "jira", "status": "connected", "site_url": "https://acme.atlassian.net", "last_verified_at": "..."}` without the api_token

#### Scenario: No credentials configured
- **WHEN** an admin requests `GET /api/credentials/jira` and no Jira credentials exist
- **THEN** the response is `{"platform_id": "jira", "status": "disconnected", "site_url": null, "last_verified_at": null}`

### Requirement: Delete Jira credentials API
The system SHALL expose `DELETE /api/credentials/jira` requiring the `admin` role. The endpoint SHALL remove the PlatformCredential record for platform_id "jira" and return HTTP 204. If no credentials exist, the endpoint SHALL return HTTP 204 (idempotent).

#### Scenario: Delete existing credentials
- **WHEN** an admin sends `DELETE /api/credentials/jira` and credentials exist
- **THEN** the PlatformCredential record is removed and HTTP 204 is returned

#### Scenario: Delete non-existent credentials
- **WHEN** an admin sends `DELETE /api/credentials/jira` and no credentials exist
- **THEN** HTTP 204 is returned

### Requirement: Token shared between REST API and MCP server
The same `api_token` stored in the Jira PlatformCredential SHALL be used for both server-side REST API calls (completion actions) and the Atlassian MCP server in task profiles. A TaskProfile's `mcp_servers` configuration MAY reference the Jira token as `{"url": "https://mcp.atlassian.com/v1/mcp", "headers": {"Authorization": "Bearer {jira_api_token}"}}`. The system SHALL inject the actual token value from the PlatformCredential at task execution time, replacing the `{jira_api_token}` placeholder.

#### Scenario: Token injected into MCP server config at execution time
- **WHEN** a task executes with a profile containing an MCP server config referencing `{jira_api_token}`
- **THEN** the system loads the api_token from PlatformCredential(platform_id="jira") and replaces the placeholder with the actual token value before passing the config to the task runner

#### Scenario: Token placeholder with no credentials
- **WHEN** a task executes with a profile referencing `{jira_api_token}` but no Jira credentials are stored
- **THEN** the system logs a warning and the MCP server config is omitted from the task runner configuration

### Requirement: Credential verification on save
The system SHALL verify Jira credentials on save by calling `GET /rest/api/3/myself` against the Atlassian Cloud gateway. The verification call MUST use the provided `cloud_id` and `api_token` to construct the full URL `https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/myself`. On success, the system SHALL extract and store the `displayName` from the response for display purposes. On failure (non-2xx response), the system SHALL reject the save and return the HTTP status and error message.

#### Scenario: Verification succeeds
- **WHEN** the `/rest/api/3/myself` call returns HTTP 200 with `{"displayName": "Errand Bot", "accountId": "xyz"}`
- **THEN** the credentials are saved and the display name "Errand Bot" is included in the response

#### Scenario: Verification fails with 401
- **WHEN** the `/rest/api/3/myself` call returns HTTP 401
- **THEN** the credentials are not saved and the endpoint returns HTTP 400 indicating the token is invalid

#### Scenario: Verification fails with network error
- **WHEN** the `/rest/api/3/myself` call fails due to a network error
- **THEN** the credentials are not saved and the endpoint returns HTTP 400 with the connection error details
