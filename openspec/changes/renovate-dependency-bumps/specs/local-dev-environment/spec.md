## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack

A `docker-compose.yml` at `testing/docker-compose.yml` SHALL define services for PostgreSQL 18, database migration, errand (main application with integrated task processing), Playwright, and Hindsight. The cache service SHALL use Valkey 9. Running `docker compose up` SHALL start the entire application locally. The errand service SHALL serve both API routes and frontend static files on port 8000, and SHALL run the TaskManager for task processing. There SHALL NOT be a separate worker service.

All services SHALL be attached to an explicit named network (`errand-net` with `name: errand-net`). The errand service SHALL mount the host Docker socket (`/var/run/docker.sock:/var/run/docker.sock`) and set `TASK_RUNNER_NETWORK=errand-net` so that `DockerRuntime` attaches task-runner containers to the same network. The errand service SHALL set `CONTAINER_RUNTIME=docker`, `TASK_RUNNER_IMAGE`, and `PLAYWRIGHT_MCP_URL` pointing to the standalone Playwright service. There SHALL NOT be a `dind` service, a `task-runner-build` service, or a `DOCKER_HOST` environment variable.

The Playwright service SHALL run with `--isolated` flag for concurrent session support. The errand service SHALL NOT manage Playwright container lifecycle — it SHALL connect to the standalone Playwright service.

#### Scenario: Full stack starts successfully

- **WHEN** a developer runs `docker compose up` with required variables configured
- **THEN** all services start: PostgreSQL 18 becomes ready, migrations run, the errand service serves on `localhost:8000` with TaskManager active, Playwright starts as a standalone service with `--isolated`, and task-runners connect to Playwright via Compose DNS

#### Scenario: PostgreSQL version
- **WHEN** the docker-compose PostgreSQL service image is inspected
- **THEN** it SHALL be `postgres:18-alpine`

#### Scenario: Valkey version
- **WHEN** the docker-compose Valkey service image is inspected
- **THEN** it SHALL be `valkey/valkey:9-alpine`
