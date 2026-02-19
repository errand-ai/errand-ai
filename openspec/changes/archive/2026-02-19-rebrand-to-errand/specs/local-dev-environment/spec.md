## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack
The docker-compose.yml SHALL use `errand` as the project/service naming convention. The task runner image reference SHALL be `errand-task-runner:latest`. The `OIDC_ROLES_CLAIM` SHALL default to `resource_access.errand.roles`. The `TASK_RUNNER_IMAGE` env var SHALL be `errand-task-runner:latest`.

#### Scenario: Task runner image reference
- **WHEN** `docker compose up` starts the worker service
- **THEN** the `TASK_RUNNER_IMAGE` environment variable is set to `errand-task-runner:latest`
