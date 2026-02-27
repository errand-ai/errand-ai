## Purpose

Local authentication with bcrypt password hashing, JWT issuance, and a local_users database table.

## Requirements

### Requirement: Local user database table
The backend SHALL have a `local_users` table with columns: `id` (integer, primary key, auto-increment), `username` (text, unique, not null), `password_hash` (text, not null), `role` (text, not null, default `"admin"`), and `created_at` (timestamptz, not null, auto-set). An Alembic migration SHALL create this table.

#### Scenario: Migration creates local_users table
- **WHEN** the Alembic migration runs
- **THEN** a `local_users` table is created with the specified columns

### Requirement: Local login endpoint
The backend SHALL expose `POST /auth/local/login` which accepts a JSON body `{"username": "<username>", "password": "<password>"}`. The endpoint SHALL validate the password against the bcrypt hash stored in `local_users`. On success, the endpoint SHALL return a JWT with claims `sub`, `email` (set to `<username>@local`), and `_roles: ["admin"]`. On failure, the endpoint SHALL return HTTP 401.

#### Scenario: Successful local login
- **WHEN** a POST to `/auth/local/login` includes valid credentials
- **THEN** the backend returns HTTP 200 with `{"access_token": "<jwt>", "token_type": "bearer"}`

#### Scenario: Invalid password
- **WHEN** a POST to `/auth/local/login` includes a valid username but wrong password
- **THEN** the backend returns HTTP 401 with `{"detail": "Invalid credentials"}`

#### Scenario: Unknown username
- **WHEN** a POST to `/auth/local/login` includes a non-existent username
- **THEN** the backend returns HTTP 401 with `{"detail": "Invalid credentials"}`

### Requirement: Local logout endpoint
The backend SHALL expose `GET /auth/local/logout` which returns a redirect to `/` (the frontend root). Unlike SSO logout, no external IdP session needs to be terminated.

#### Scenario: Local logout redirects to root
- **WHEN** a browser requests `GET /auth/local/logout`
- **THEN** the backend responds with HTTP 302 redirecting to `/`

### Requirement: JWT signing secret auto-generation
The backend SHALL auto-generate a `jwt_signing_secret` setting (64-character hex string) on first startup if it does not exist. The secret SHALL be stored in the `settings` table and used to sign and verify local auth JWTs with HMAC-SHA256.

#### Scenario: Secret generated on first startup
- **WHEN** the backend starts and no `jwt_signing_secret` setting exists
- **THEN** a new 64-character hex secret is generated and stored in the settings table

#### Scenario: Existing secret reused
- **WHEN** the backend starts and `jwt_signing_secret` exists in settings
- **THEN** the existing secret is used for JWT signing

### Requirement: Local JWT token expiry
Local auth JWTs SHALL have a 24-hour expiry. The `exp` claim SHALL be set to 24 hours from the time of issuance.

#### Scenario: Token valid within 24 hours
- **WHEN** a local auth JWT is used within 24 hours of issuance
- **THEN** the token is accepted by the backend

#### Scenario: Token expired after 24 hours
- **WHEN** a local auth JWT is used more than 24 hours after issuance
- **THEN** the backend returns HTTP 401 with `{"detail": "Token expired"}`

### Requirement: Auto-provision local admin from env vars
On startup, if `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables are set and no local user with that username exists, the backend SHALL create a local admin user with those credentials. If the user already exists, the backend SHALL skip creation (not update the password).

#### Scenario: Auto-create local admin from env vars
- **WHEN** the backend starts with `ADMIN_USERNAME=admin` and `ADMIN_PASSWORD=changeme` and no user named `admin` exists
- **THEN** a local admin user is created with username `admin` and the bcrypt hash of `changeme`

#### Scenario: Skip creation when user exists
- **WHEN** the backend starts with `ADMIN_USERNAME=admin` and a user named `admin` already exists
- **THEN** no user is created or modified

#### Scenario: Env vars not set
- **WHEN** the backend starts without `ADMIN_USERNAME` or `ADMIN_PASSWORD`
- **THEN** no auto-provisioning occurs

### Requirement: Change password endpoint
The backend SHALL expose `POST /auth/local/change-password` requiring authentication. The endpoint SHALL accept `{"current_password": "...", "new_password": "..."}`, validate the current password, and update the hash. The endpoint SHALL return HTTP 200 on success or HTTP 401 if the current password is wrong.

#### Scenario: Successful password change
- **WHEN** an authenticated local admin sends a valid current password and new password
- **THEN** the backend updates the password hash and returns HTTP 200

#### Scenario: Wrong current password
- **WHEN** an authenticated local admin sends an incorrect current password
- **THEN** the backend returns HTTP 401 with `{"detail": "Current password is incorrect"}`
