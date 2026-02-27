## Purpose

Backend endpoint for detecting the current authentication mode (setup, local, or SSO) without requiring authentication.

## Requirements

### Requirement: Auth status endpoint
The backend SHALL expose `GET /api/auth/status` with NO authentication required. The endpoint SHALL return a JSON object with the current auth mode and related metadata.

#### Scenario: Setup mode (no users, no SSO)
- **WHEN** no local admin exists and no OIDC configuration is present (env or DB)
- **THEN** the endpoint returns `{"mode": "setup"}`

#### Scenario: Local auth mode
- **WHEN** a local admin exists and no OIDC configuration is present
- **THEN** the endpoint returns `{"mode": "local"}`

#### Scenario: SSO mode from env vars
- **WHEN** OIDC env vars are set
- **THEN** the endpoint returns `{"mode": "sso", "login_url": "/auth/login"}`

#### Scenario: SSO mode from DB settings
- **WHEN** OIDC settings exist in the database (but not env vars)
- **THEN** the endpoint returns `{"mode": "sso", "login_url": "/auth/login"}`

### Requirement: Auth status reflects live state
The `/api/auth/status` endpoint SHALL query the current state on each request (not cache at startup). This ensures changes to auth config (e.g., admin enabling SSO via settings) are reflected immediately.

#### Scenario: Mode changes after SSO config saved
- **WHEN** the admin saves OIDC settings via the User Management page and then calls `/api/auth/status`
- **THEN** the response reflects `"mode": "sso"` without requiring a restart
