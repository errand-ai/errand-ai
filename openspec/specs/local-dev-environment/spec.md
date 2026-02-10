## ADDED Requirements

### Requirement: Docker Compose runs the full application stack
A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, backend, worker, and frontend. Running `docker compose up` SHALL start the entire application locally. The backend service SHALL include OIDC environment variables (`OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`).

#### Scenario: Full stack starts successfully
- **WHEN** a developer runs `docker compose up` with OIDC variables configured
- **THEN** all services start: PostgreSQL becomes ready, migrations run, backend serves on `localhost:8000` with OIDC enabled, worker begins polling, and frontend is accessible on `localhost:3000`

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

### Requirement: Local testing before committing
All code changes MUST be verified by running `docker compose up` and confirming the affected functionality works before committing and pushing to GitHub.

#### Scenario: Developer workflow
- **WHEN** a developer makes changes to the backend or frontend
- **THEN** they run `docker compose up`, verify the changes work as expected, and only then commit and push

### Requirement: DinD service in Docker Compose
The Docker Compose configuration SHALL include a `dind` service using the `docker:27-dind` image. The DinD service SHALL run with `privileged: true`. The DinD service SHALL have `DOCKER_TLS_CERTDIR` set to an empty string to disable TLS. The DinD service SHALL expose port 2375 on the internal Docker network.

#### Scenario: DinD service starts
- **WHEN** `docker compose up` is run
- **THEN** the `dind` service starts and the Docker daemon becomes available on port 2375

#### Scenario: DinD service health
- **WHEN** the DinD service is running
- **THEN** the Docker daemon responds to API requests on port 2375

### Requirement: Worker connects to DinD service
The Docker Compose worker service SHALL have `DOCKER_HOST` set to `tcp://dind:2375`. The worker service SHALL depend on the `dind` service being healthy. The worker service SHALL have `TASK_RUNNER_IMAGE` set to the task runner image reference for local development.

#### Scenario: Worker uses DinD
- **WHEN** the worker service starts
- **THEN** the worker connects to the Docker daemon at `tcp://dind:2375`

#### Scenario: Worker depends on DinD
- **WHEN** `docker compose up` is run
- **THEN** the worker service waits for the `dind` service to be healthy before starting
