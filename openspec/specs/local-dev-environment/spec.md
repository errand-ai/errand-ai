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

### Requirement: Optional workspace gateway in docker-compose

The compose stack SHALL support an optional workspace gateway service (same rclone image and configuration shape as the Kubernetes gateway, including the token-refresher behavior) attached to the errand network. Task containers with workspace-enabled profiles SHALL reach it via an NFS volume (`driver_opts: type=nfs`) or a bind-mount fallback for local testing. The service SHALL be disabled by default (compose profile or commented block) so `docker compose up` behavior is unchanged for existing users.

#### Scenario: Default compose unchanged

- **WHEN** the stack is started without the workspace profile
- **THEN** no gateway container runs and existing services behave as before

#### Scenario: Gateway service started

- **WHEN** the stack is started with the workspace profile enabled and provider credentials configured
- **THEN** the gateway serves the configured cloud folder and a workspace-enabled task container can read and write files through its mount

### Requirement: Hindsight stores its tables in a schema of the errand database

The compose environments SHALL point Hindsight at the same PostgreSQL database errand uses, isolated by schema rather than by database. Hindsight SHALL receive `HINDSIGHT_API_DATABASE_SCHEMA=hindsight`, and the database initialisation script SHALL NOT create a separate `hindsight` database. Alembic SHALL continue to own the `public` schema and SHALL NOT create, read or migrate anything in the `hindsight` schema.

#### Scenario: Single database in compose

- **WHEN** the compose environment is brought up
- **THEN** Hindsight's connection string names the same database as errand's `DATABASE_URL`
- **AND** `HINDSIGHT_API_DATABASE_SCHEMA` is `hindsight`

#### Scenario: Init script no longer creates a hindsight database

- **WHEN** `deploy/init-databases.sh` runs
- **THEN** it creates the `litellm` database only
- **AND** it does not issue `CREATE DATABASE hindsight`

#### Scenario: pgvector available in the shared database

- **WHEN** the compose PostgreSQL image starts
- **THEN** the `vector` extension is available and installed in the errand database before Hindsight first connects

### Requirement: Hindsight Control Plane is opt-in and off by default

The Control Plane SHALL be defined as a separate compose service behind a profile, and SHALL NOT start or publish a port during a default `docker compose up`. Starting it SHALL require explicitly selecting that profile.

#### Scenario: Default bring-up omits the Control Plane

- **WHEN** the compose environment is started without profile selection
- **THEN** no Control Plane container is created
- **AND** no host port is published for it

#### Scenario: Control Plane started on request

- **WHEN** the compose environment is started with the memory-UI profile selected
- **THEN** the Control Plane container starts and is reachable
- **AND** it is configured with the API service URL and, when the API requires one, the matching bearer

### Requirement: Hindsight volume ownership is prepared before first start

Every compose file that mounts a host-managed volume into the Hindsight container SHALL ensure the mounted paths are owned by the container's non-root user before the service starts. This applies to the model/cache directory as well as any embedded-database directory.

#### Scenario: Cache volume chowned in the deployment compose file

- **WHEN** `deploy/docker-compose.yml` is brought up for the first time with empty volumes
- **THEN** an initialisation step makes the mounted cache directory writable by the container user
- **AND** Hindsight starts without `PermissionError` on its Hugging Face cache directory

#### Scenario: Both mounted directories are covered

- **WHEN** a compose file mounts both a data directory and a cache directory into Hindsight
- **THEN** the initialisation step covers both paths, not only the data directory
