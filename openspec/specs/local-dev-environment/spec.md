## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack
A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, backend, worker, and Hindsight. Running `docker compose up` SHALL start the entire application locally. The backend SHALL serve both API routes and frontend static files on port 8000. There SHALL NOT be a separate frontend service. The backend service SHALL include OIDC environment variables (`OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`). The backend and worker services SHALL receive `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables.

#### Scenario: Full stack starts successfully
- **WHEN** a developer runs `docker compose up` with OIDC and OpenAI variables configured
- **THEN** all services start: PostgreSQL becomes ready, migrations run, backend serves on `localhost:8000` with OIDC enabled and frontend static files available, worker begins polling, and Hindsight is accessible on `localhost:8888`

#### Scenario: Services start in correct order
- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and backend/worker start after migrations complete

## REMOVED Requirements

### Requirement: Frontend proxies API requests to backend
**Reason**: There is no longer a separate frontend service. The backend serves both API routes and static files directly.
**Migration**: Remove the `frontend` service from docker-compose.yml. Access the application at `localhost:8000` instead of `localhost:3000`.

### Requirement: Frontend proxies auth requests to backend
**Reason**: There is no longer a separate frontend service with nginx. The backend handles auth routes directly.
**Migration**: No action needed — auth routes are already on the backend.
