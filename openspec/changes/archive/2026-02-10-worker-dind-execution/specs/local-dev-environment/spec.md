## ADDED Requirements

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
