## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack
The `docker-compose.yml` SHALL continue to include the `dind` service, `task-runner-build` service, and the worker's `DOCKER_HOST=tcp://dind:2375` environment variable. The worker service SHALL NOT set `CONTAINER_RUNTIME` (defaulting to `docker`). The docker-compose local development environment SHALL be unchanged from its current configuration.

#### Scenario: Local dev uses Docker runtime
- **WHEN** a developer runs `docker compose up`
- **THEN** the worker uses DockerRuntime (default), connects to DinD, and runs task-runners as Docker containers — identical to current behaviour
