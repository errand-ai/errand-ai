## Purpose

Settings sub-page for authentication mode configuration and local admin account management.

## Requirements

### Requirement: User Management settings sub-page
The Settings page SHALL include a "User Management" sub-page at `/settings/users`. The sub-page SHALL contain two sections: "Authentication Mode" and "Local Admin Account".

#### Scenario: User Management page renders
- **WHEN** an admin navigates to `/settings/users`
- **THEN** the page displays the Authentication Mode and Local Admin Account sections

### Requirement: Authentication mode display
The Authentication Mode section SHALL display the current auth mode (Local or SSO) and allow the admin to configure SSO. When SSO is not configured, the section SHALL show "Local Authentication" as the current mode with an option to configure SSO. When SSO is configured, the section SHALL show the SSO provider details.

#### Scenario: Local auth active, no SSO configured
- **WHEN** the admin views User Management and no OIDC settings exist
- **THEN** the section shows "Local Authentication" as the current mode with OIDC configuration fields

#### Scenario: SSO active from env vars
- **WHEN** OIDC settings come from env vars
- **THEN** the OIDC fields are displayed read-only with the env-sourced values and a lock indicator

### Requirement: OIDC configuration fields
The Authentication Mode section SHALL display four fields: OIDC Discovery URL, Client ID, Client Secret (password field), and Roles Claim. If the corresponding env vars are set, the fields SHALL be read-only with a lock indicator. If not env-sourced, the fields SHALL be editable. A "Test Connection" button SHALL perform OIDC discovery against the entered URL to verify it works. A "Save & Enable SSO" button SHALL save the config and trigger a hot-reload of the OIDC configuration.

#### Scenario: Save and enable SSO
- **WHEN** the admin enters valid OIDC details and clicks "Save & Enable SSO"
- **THEN** the backend saves the OIDC settings, performs discovery, and switches to SSO mode

#### Scenario: Test OIDC connection
- **WHEN** the admin clicks "Test Connection" with a valid discovery URL
- **THEN** a success message confirms the OIDC provider is reachable

#### Scenario: Invalid OIDC discovery URL
- **WHEN** the admin clicks "Test Connection" with an unreachable URL
- **THEN** an error message is displayed

### Requirement: Remove SSO configuration
When SSO is configured via DB settings (not env vars), the Authentication Mode section SHALL display a "Remove SSO" button. Clicking it SHALL delete the OIDC settings from the database and revert to local auth mode.

#### Scenario: Remove SSO reverts to local auth
- **WHEN** the admin clicks "Remove SSO" and confirms
- **THEN** the OIDC settings are deleted from the DB and the auth mode reverts to local

#### Scenario: Cannot remove env-sourced SSO
- **WHEN** OIDC settings come from env vars
- **THEN** no "Remove SSO" button is displayed

### Requirement: Local admin account section
The Local Admin Account section SHALL display the current admin username and a "Change Password" button. Clicking the button SHALL reveal current password, new password, and confirm password fields. Submitting SHALL call `POST /auth/local/change-password`.

#### Scenario: Change password
- **WHEN** the admin enters the current password and a new password and submits
- **THEN** the password is changed and a success toast is shown

#### Scenario: Wrong current password
- **WHEN** the admin enters an incorrect current password
- **THEN** an error message is displayed
