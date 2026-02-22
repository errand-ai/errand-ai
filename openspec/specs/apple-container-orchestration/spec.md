## ADDED Requirements

### Requirement: Container lifecycle management via Containerization framework
The app SHALL use Apple's Containerization Swift package to pull OCI images, create containers, start/stop containers, bind volumes, and monitor container health. The app SHALL NOT shell out to the `container` CLI.

#### Scenario: Pull image from registry
- **WHEN** the app needs to start PostgreSQL and the `postgres:16-alpine` image is not cached locally
- **THEN** the app pulls the image from the OCI registry using the Containerization framework

#### Scenario: Create container with volume
- **WHEN** the app starts the PostgreSQL service
- **THEN** it creates a container from the `postgres:16-alpine` image with `~/Library/Application Support/ContentManager/data/postgres/` mounted as the data directory

#### Scenario: Stop and remove container
- **WHEN** the user clicks "Stop All"
- **THEN** each container is gracefully stopped (SIGTERM, then SIGKILL after timeout) and removed

### Requirement: Service dependency ordering
The app SHALL start services in dependency order: PostgreSQL → Valkey → Backend → Worker. The app SHALL wait for each service's health check to pass before starting dependent services. The app SHALL stop services in reverse order.

#### Scenario: Backend waits for PostgreSQL
- **WHEN** "Start All" is triggered
- **THEN** the backend container is not started until PostgreSQL's health check passes

#### Scenario: Worker waits for backend
- **WHEN** "Start All" is triggered
- **THEN** the worker container is not started until the backend's health check passes

### Requirement: Health checking
The app SHALL health-check each service: PostgreSQL via TCP connection to port 5432, Valkey via TCP connection to port 6379, Backend via HTTP GET to `/health`, Worker via process liveness. Health checks SHALL run every 10 seconds while services are running. A service that fails 3 consecutive health checks SHALL be marked as unhealthy.

#### Scenario: PostgreSQL health check
- **WHEN** PostgreSQL is running
- **THEN** the app checks TCP connectivity to port 5432 every 10 seconds

#### Scenario: Backend health check
- **WHEN** the backend is running
- **THEN** the app checks HTTP GET `/health` on port 8000 every 10 seconds

### Requirement: Inter-container networking via environment variables
The app SHALL discover each container's IP address after creation and pass connection URLs as environment variables to dependent containers. PostgreSQL and Valkey URLs SHALL be passed to the backend and worker. The backend URL SHALL be passed to the worker.

#### Scenario: Backend receives database URL
- **WHEN** the backend container starts
- **THEN** it receives `DATABASE_URL=postgresql://postgres:postgres@<postgres-ip>:5432/content_manager`

#### Scenario: Worker receives backend URL
- **WHEN** the worker container starts
- **THEN** it receives `ERRAND_MCP_URL=http://<backend-ip>:8000/mcp`

### Requirement: Persistent storage via volume mounts
Container data SHALL be persisted via bind mounts from `~/Library/Application Support/ContentManager/data/`. PostgreSQL data SHALL be mounted at the container's data directory. Valkey data SHALL be mounted for RDB/AOF persistence. Data SHALL survive container restarts and app updates.

#### Scenario: PostgreSQL data persists
- **WHEN** the user stops and restarts all services
- **THEN** PostgreSQL retains all previously created tasks, tags, and settings

#### Scenario: Factory reset
- **WHEN** the user triggers "Reset Data" from settings
- **THEN** the data directories are deleted and recreated empty
