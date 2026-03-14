## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack

A `docker-compose.yml` at `testing/docker-compose.yml` SHALL define services for PostgreSQL, database migration, errand (main application with integrated task processing), Playwright, and Hindsight. Running `docker compose up` SHALL start the entire application locally. The errand service SHALL serve both API routes and frontend static files on port 8000, and SHALL run the TaskManager for task processing. There SHALL NOT be a separate worker service.

All services SHALL be attached to an explicit named network (`errand-net` with `name: errand-net`). The errand service SHALL mount the host Docker socket (`/var/run/docker.sock:/var/run/docker.sock`) and set `TASK_RUNNER_NETWORK=errand-net` so that `DockerRuntime` attaches task-runner containers to the same network. The errand service SHALL set `CONTAINER_RUNTIME=docker`, `TASK_RUNNER_IMAGE`, and `PLAYWRIGHT_MCP_URL` pointing to the standalone Playwright service. There SHALL NOT be a `dind` service, a `task-runner-build` service, or a `DOCKER_HOST` environment variable.

The Playwright service SHALL run with `--isolated` flag for concurrent session support. The errand service SHALL NOT manage Playwright container lifecycle — it SHALL connect to the standalone Playwright service.

#### Scenario: Full stack starts successfully

- **WHEN** a developer runs `docker compose up` with required variables configured
- **THEN** all services start: PostgreSQL becomes ready, migrations run, the errand service serves on `localhost:8000` with TaskManager active, Playwright starts as a standalone service with `--isolated`, and task-runners connect to Playwright via Compose DNS

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

## REMOVED Requirements

### Requirement: Separate worker service in Docker Compose

**Reason**: Worker functionality merged into the errand service's TaskManager.
**Migration**: Remove the `worker` service from `docker-compose.yml`. The `errand` service now handles task processing directly.

### Requirement: DinD (Docker-in-Docker) for local dev

**Reason**: Replaced by host Docker socket mount + named network. DinD added unnecessary complexity (privileged container, nested Docker daemon, separate image cache, task-runner-build sidecar). The host socket approach is simpler and consistent with how errand-desktop already creates containers directly on the host Docker daemon. Named network gives task-runners DNS resolution for compose services without `network_mode="host"`.
**Migration**: Remove `dind` and `task-runner-build` services. Mount `/var/run/docker.sock` on the errand service. Add `TASK_RUNNER_NETWORK=errand-net` env var. Define explicit `errand-net` network in docker-compose.
