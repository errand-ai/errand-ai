## ADDED Requirements

### Requirement: Docker Compose runs the full application stack
A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, backend, worker, and frontend. Running `docker compose up` SHALL start the entire application locally.

#### Scenario: Full stack starts successfully
- **WHEN** a developer runs `docker compose up`
- **THEN** all services start: PostgreSQL becomes ready, migrations run, backend serves on `localhost:8000`, worker begins polling, and frontend is accessible on `localhost:3000`

#### Scenario: Services start in correct order
- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and backend/worker/frontend start after migrations complete

### Requirement: PostgreSQL container is included
The Docker Compose configuration SHALL include a PostgreSQL service with a preconfigured database. The `DATABASE_URL` environment variable SHALL be set consistently across the migrate, backend, and worker services.

#### Scenario: Database is accessible
- **WHEN** the postgres service is running
- **THEN** the backend, worker, and migration services can connect using the shared `DATABASE_URL`

### Requirement: Migrations run automatically on startup
The Docker Compose configuration SHALL include a migration service that runs `alembic upgrade head` and exits. Backend and worker services MUST depend on the migration service completing successfully.

#### Scenario: Schema is current before application starts
- **WHEN** `docker compose up` is run
- **THEN** Alembic migrations execute against PostgreSQL before the backend or worker accept any requests

### Requirement: Frontend proxies API requests to backend
The frontend service in Docker Compose SHALL proxy `/api/*` requests to the backend container, matching the production nginx configuration.

#### Scenario: API requests reach backend
- **WHEN** a browser at `localhost:3000` makes a request to `/api/tasks`
- **THEN** the request is proxied to the backend service and returns task data

### Requirement: Local testing before committing
All code changes MUST be verified by running `docker compose up` and confirming the affected functionality works before committing and pushing to GitHub.

#### Scenario: Developer workflow
- **WHEN** a developer makes changes to the backend or frontend
- **THEN** they run `docker compose up`, verify the changes work as expected, and only then commit and push
