## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack
A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, backend, worker, and frontend. Running `docker compose up` SHALL start the entire application locally. The backend service SHALL include OIDC environment variables (`OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`). The backend and worker services SHALL receive `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables (replacing the previous `LITELLM_BASE_URL` and `LITELLM_API_KEY` names).

#### Scenario: Full stack starts successfully
- **WHEN** a developer runs `docker compose up` with OIDC and OpenAI variables configured
- **THEN** all services start: PostgreSQL becomes ready, migrations run, backend serves on `localhost:8000` with OIDC enabled, worker begins polling, and frontend is accessible on `localhost:3000`

#### Scenario: Services start in correct order
- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and backend/worker/frontend start after migrations complete

### Requirement: Worker connects to DinD service
The Docker Compose worker service SHALL have `DOCKER_HOST` set to `tcp://dind:2375`. The worker service SHALL depend on the `dind` service being healthy. The worker service SHALL have `TASK_RUNNER_IMAGE` set to the task runner image reference for local development. The worker service SHALL have `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables passed through from the host environment.

#### Scenario: Worker uses DinD
- **WHEN** the worker service starts
- **THEN** the worker connects to the Docker daemon at `tcp://dind:2375`

#### Scenario: Worker depends on DinD
- **WHEN** `docker compose up` is run
- **THEN** the worker service waits for the `dind` service to be healthy before starting

#### Scenario: Worker has OpenAI credentials
- **WHEN** the worker service starts
- **THEN** the worker has `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables available
