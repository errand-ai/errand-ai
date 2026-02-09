## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack
A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, backend, worker, and frontend. Running `docker compose up` SHALL start the entire application locally. The backend service SHALL include OIDC environment variables (`OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`).

#### Scenario: Full stack starts successfully
- **WHEN** a developer runs `docker compose up` with OIDC variables configured
- **THEN** all services start: PostgreSQL becomes ready, migrations run, backend serves on `localhost:8000` with OIDC enabled, worker begins polling, and frontend is accessible on `localhost:3000`

#### Scenario: Services start in correct order
- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and backend/worker/frontend start after migrations complete

## ADDED Requirements

### Requirement: OIDC environment variables in Docker Compose
The Docker Compose backend service SHALL include `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET` environment variables. Values SHALL be configurable via a `.env` file or shell environment.

#### Scenario: Variables from .env file
- **WHEN** a `.env` file exists with `OIDC_CLIENT_ID=my-client`
- **THEN** the backend service receives `OIDC_CLIENT_ID=my-client`

#### Scenario: Missing OIDC variables
- **WHEN** a developer runs `docker compose up` without setting OIDC variables
- **THEN** the backend service fails to start with an error indicating the missing variables

### Requirement: Frontend proxies auth requests to backend
The frontend nginx configuration in Docker Compose SHALL proxy `/auth/*` requests to the backend service, in addition to the existing `/api/*` proxy.

#### Scenario: Auth requests reach backend
- **WHEN** a browser at `localhost:3000` is redirected to `/auth/login`
- **THEN** nginx proxies the request to the backend service
