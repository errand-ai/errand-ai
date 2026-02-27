## Purpose

Docker Compose configuration for running the full application stack locally with PostgreSQL, DinD, and all services.

## Requirements

### Requirement: Docker Compose runs the full application stack
A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, errand (main application), worker, and Hindsight. Running `docker compose up` SHALL start the entire application locally. The errand service SHALL serve both API routes and frontend static files on port 8000. There SHALL NOT be a separate frontend service. The errand service SHALL include OIDC environment variables (`OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`). The errand and worker services SHALL receive `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables. The `docker-compose.yml` SHALL continue to include the `dind` service, `task-runner-build` service, and the worker's `DOCKER_HOST=tcp://dind:2375` environment variable. The worker service SHALL NOT set `CONTAINER_RUNTIME` (defaulting to `docker`). The worker service SHALL set `ERRAND_MCP_URL` to `http://errand:8000/mcp`.

#### Scenario: Full stack starts successfully
- **WHEN** a developer runs `docker compose up` with OIDC and OpenAI variables configured
- **THEN** all services start: PostgreSQL becomes ready, migrations run, the errand service serves on `localhost:8000` with OIDC enabled and frontend static files available, worker begins polling, and Hindsight is accessible on `localhost:8888`

#### Scenario: Services start in correct order
- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and errand/worker start after migrations complete

#### Scenario: Local dev uses Docker runtime
- **WHEN** a developer runs `docker compose up`
- **THEN** the worker uses DockerRuntime (default), connects to DinD, and runs task-runners as Docker containers — identical to current behaviour
