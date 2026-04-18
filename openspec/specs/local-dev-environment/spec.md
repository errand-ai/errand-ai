## Purpose

Docker Compose configuration for running the full application stack locally with PostgreSQL and all services.

## Requirements

### Requirement: Docker Compose runs the full application stack

A `docker-compose.yml` at `testing/docker-compose.yml` SHALL define services for PostgreSQL 18, database migration, errand (main application with integrated task processing), Playwright, and Hindsight. The cache service SHALL use Valkey 9. Running `docker compose up` SHALL start the entire application locally. The errand service SHALL serve both API routes and frontend static files on port 8000, and SHALL run the TaskManager for task processing. There SHALL NOT be a separate worker service.

All services SHALL be attached to an explicit named network (`errand-net` with `name: errand-net`). The errand service SHALL mount the host Docker socket (`/var/run/docker.sock:/var/run/docker.sock`) and set `TASK_RUNNER_NETWORK=errand-net` so that `DockerRuntime` attaches task-runner containers to the same network. The errand service SHALL set `CONTAINER_RUNTIME=docker`, `TASK_RUNNER_IMAGE`, and `PLAYWRIGHT_MCP_URL` pointing to the standalone Playwright service. There SHALL NOT be a `dind` service, a `task-runner-build` service, or a `DOCKER_HOST` environment variable.

The Playwright service SHALL run with `--isolated` flag for concurrent session support. The errand service SHALL NOT manage Playwright container lifecycle — it SHALL connect to the standalone Playwright service.

#### Scenario: Full stack starts successfully

- **WHEN** a developer runs `docker compose up` with required variables configured
- **THEN** all services start: PostgreSQL 18 becomes ready, migrations run, the errand service serves on `localhost:8000` with TaskManager active, Playwright starts as a standalone service with `--isolated`, and task-runners connect to Playwright via Compose DNS

#### Scenario: Services start in correct order

- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and errand starts after migrations complete

#### Scenario: Local dev uses Docker runtime with host socket

- **WHEN** a developer runs `docker compose up`
- **THEN** the errand service uses DockerRuntime via the mounted host Docker socket, creates task-runner containers on the host daemon, and attaches them to the `errand-net` network so they can resolve compose service DNS names

#### Scenario: Task-runner reaches compose services

- **WHEN** a task-runner container is created on the host Docker daemon attached to `errand-net`
- **THEN** it can resolve and connect to `errand:8000`, `playwright:3000`, `gdrive-mcp:8080`, `onedrive-mcp:8080`, `hindsight:8888`, and any other services on the same network

#### Scenario: Task-runner reaches external services

- **WHEN** a task-runner container needs to call LLM APIs, clone git repos, or connect to errand-cloud
- **THEN** outbound traffic routes via Docker bridge NAT to the internet

#### Scenario: PostgreSQL version
- **WHEN** the docker-compose PostgreSQL service image is inspected
- **THEN** it SHALL be `postgres:18-alpine`

#### Scenario: Valkey version
- **WHEN** the docker-compose Valkey service image is inspected
- **THEN** it SHALL be `valkey/valkey:9-alpine`

<!-- Removed: Separate worker service in Docker Compose — Worker functionality merged into the errand service's TaskManager. -->
<!-- Removed: DinD (Docker-in-Docker) for local dev — Replaced by host Docker socket mount + named network. -->

### Requirement: Docker Compose service health monitoring
The errand server service in both testing and deploy docker-compose files SHALL have healthcheck directives that verify the service is responsive.

#### Scenario: Errand server healthcheck defined
- **WHEN** docker-compose services are inspected
- **THEN** the errand service SHALL have a healthcheck that queries `http://localhost:8000/api/health`
