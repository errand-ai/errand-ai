## Purpose

GitHub platform module with PAT and GitHub App authentication modes, credential verification, and platform registry integration.

## Requirements

### Requirement: GitHub platform module

The system SHALL provide a `GitHubPlatform` class in `errand/platforms/github.py` that extends the `Platform` base class. The platform SHALL register with id `github`, label `GitHub`, and capabilities `{}` (no platform-specific capabilities like POST). The credential schema SHALL include an `auth_mode` selector field with values `pat` and `app`, plus fields for both modes:

- **PAT mode fields**: `personal_access_token` (type `password`, required)
- **App mode fields**: `app_id` (type `text`, required), `private_key` (type `textarea`, required), `installation_id` (type `text`, required)

The stored credential dict SHALL always include `auth_mode` to distinguish which fields are active.

#### Scenario: Platform registered in registry

- **WHEN** the application starts
- **THEN** the `GitHubPlatform` is registered in the platform registry with id `github`

#### Scenario: Platform info returns correct schema

- **WHEN** `platform.info()` is called
- **THEN** the returned `PlatformInfo` has id `github`, label `GitHub`, and a credential schema with `auth_mode`, PAT, and App fields

### Requirement: GitHub PAT credential verification

When `verify_credentials()` is called with `auth_mode: "pat"`, the platform SHALL send a `GET` request to `https://api.github.com/user` with `Authorization: Bearer <personal_access_token>` and `Accept: application/vnd.github+json` headers. If the response is HTTP 200, verification SHALL succeed. If the response is HTTP 401 or any other error, verification SHALL fail.

#### Scenario: Valid PAT verifies successfully

- **WHEN** `verify_credentials({"auth_mode": "pat", "personal_access_token": "ghp_valid"})` is called and GitHub returns HTTP 200
- **THEN** the method returns `True`

#### Scenario: Invalid PAT fails verification

- **WHEN** `verify_credentials({"auth_mode": "pat", "personal_access_token": "ghp_expired"})` is called and GitHub returns HTTP 401
- **THEN** the method returns `False`

#### Scenario: Network error during PAT verification

- **WHEN** `verify_credentials()` is called in PAT mode and the request to GitHub fails with a network error
- **THEN** the method returns `False` and logs the error

### Requirement: GitHub App credential verification

When `verify_credentials()` is called with `auth_mode: "app"`, the platform SHALL attempt to mint a test installation access token using the provided `app_id`, `private_key`, and `installation_id`. The verification process SHALL:

1. Create a JWT with `iss` set to `app_id`, `iat` set to current time minus 60 seconds, and `exp` set to current time plus 600 seconds, signed with the `private_key` using RS256
2. Send a `POST` request to `https://api.github.com/app/installations/{installation_id}/access_tokens` with `Authorization: Bearer <jwt>` and `Accept: application/vnd.github+json` headers
3. If the response is HTTP 201 and contains a `token` field, verification SHALL succeed
4. If the response is any other status or the JWT signing fails, verification SHALL fail

#### Scenario: Valid App credentials verify successfully

- **WHEN** `verify_credentials({"auth_mode": "app", "app_id": "123", "private_key": "<valid PEM>", "installation_id": "456"})` is called and GitHub returns HTTP 201 with a token
- **THEN** the method returns `True`

#### Scenario: Invalid App credentials fail verification

- **WHEN** `verify_credentials()` is called in App mode with an invalid private key
- **THEN** the method returns `False` and logs the error

#### Scenario: Wrong installation ID fails verification

- **WHEN** `verify_credentials()` is called in App mode with a valid app/key but wrong installation ID
- **THEN** GitHub returns HTTP 404 and the method returns `False`

### Requirement: GitHub App token minting utility

The `github.py` module SHALL provide a standalone function `mint_installation_token(app_id: str, private_key: str, installation_id: str) -> str` that creates an ephemeral GitHub installation access token. The function SHALL:

1. Create a JWT signed with RS256 using the provided private key, with `iss` set to `app_id`, `iat` to current time minus 60 seconds, and `exp` to current time plus 600 seconds
2. POST to `https://api.github.com/app/installations/{installation_id}/access_tokens` with the JWT as Bearer token
3. Return the `token` value from the response
4. Raise an exception if the API returns a non-201 status or the request fails

This function is called by the worker at task preparation time to mint fresh tokens per-task.

#### Scenario: Token minted successfully

- **WHEN** `mint_installation_token("123", "<valid PEM>", "456")` is called
- **THEN** a valid GitHub installation access token string is returned

#### Scenario: Token minting fails with invalid key

- **WHEN** `mint_installation_token()` is called with an invalid private key
- **THEN** an exception is raised with a descriptive error message

#### Scenario: Token minting fails with API error

- **WHEN** the GitHub API returns HTTP 401 (bad JWT) or HTTP 404 (bad installation ID)
- **THEN** an exception is raised with the HTTP status and error detail

### Requirement: GitHub integration UI on Integrations sub-page

The Integrations settings sub-page SHALL display a GitHub integration card alongside existing platform integrations (e.g., Twitter). The card SHALL:

1. Show connection status (connected/disconnected) matching the platform credential status
2. Provide an auth mode selector (PAT / GitHub App) that controls which credential fields are displayed
3. In PAT mode, show a single password field for the personal access token
4. In App mode, show fields for App ID, Private Key (textarea for PEM), and Installation ID
5. Provide Save/Connect and Disconnect buttons following the same pattern as other platform integrations
6. On Save, call the existing `PUT /api/platforms/github/credentials` endpoint with the credential fields plus `auth_mode`

#### Scenario: GitHub card displayed on Integrations page

- **WHEN** an admin navigates to the Integrations settings sub-page
- **THEN** a GitHub integration card is visible alongside other platform cards

#### Scenario: Auth mode selector switches fields

- **WHEN** the admin selects "GitHub App" auth mode
- **THEN** the PAT field is hidden and App ID, Private Key, and Installation ID fields are shown

#### Scenario: PAT credentials saved successfully

- **WHEN** the admin enters a valid PAT and clicks Save
- **THEN** the credentials are sent to `PUT /api/platforms/github/credentials`, verified, and the status updates to "connected"

#### Scenario: App credentials saved successfully

- **WHEN** the admin enters valid App ID, Private Key, and Installation ID and clicks Save
- **THEN** the credentials are sent to `PUT /api/platforms/github/credentials`, verified, and the status updates to "connected"

#### Scenario: Disconnect removes credentials

- **WHEN** the admin clicks Disconnect on the GitHub integration
- **THEN** `DELETE /api/platforms/github/credentials` is called and the status updates to "disconnected"
