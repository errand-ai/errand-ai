## MODIFIED Requirements

### Requirement: Docker Compose runs the full application stack

A `docker-compose.yml` at the repository root SHALL define services for PostgreSQL, database migration, backend, worker, frontend, and Hindsight. Running `docker compose up` SHALL start the entire application locally. The backend service SHALL include OIDC environment variables (`OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`). The backend and worker services SHALL receive `OPENAI_BASE_URL` and `OPENAI_API_KEY` environment variables (replacing the previous `LITELLM_BASE_URL` and `LITELLM_API_KEY` names).

#### Scenario: Full stack starts successfully

- **WHEN** a developer runs `docker compose up` with OIDC and OpenAI variables configured
- **THEN** all services start: PostgreSQL becomes ready, migrations run, backend serves on `localhost:8000` with OIDC enabled, worker begins polling, frontend is accessible on `localhost:3000`, and Hindsight is accessible on `localhost:8888`

#### Scenario: Services start in correct order

- **WHEN** Docker Compose starts
- **THEN** PostgreSQL starts first, migrations run after PostgreSQL is healthy, and backend/worker/frontend start after migrations complete

## ADDED Requirements

### Requirement: Hindsight service in Docker Compose

The Docker Compose configuration SHALL include a `hindsight` service using the `ghcr.io/vectorize-io/hindsight:latest` image. The service SHALL expose port 8888 (API) and port 9999 (control plane UI) on the host. The service SHALL receive `HINDSIGHT_API_LLM_API_KEY` set to `${OPENAI_API_KEY}`, `HINDSIGHT_API_LLM_BASE_URL` set to `${OPENAI_BASE_URL:-}`, and `HINDSIGHT_API_LLM_MODEL` set explicitly to avoid Hindsight's default model which may not be available on the LLM provider. The service SHALL use embedded pg0 storage (no external PostgreSQL dependency) with persistent Docker volumes for the pg0 data directory and model cache. A `hindsight-init` service SHALL run before hindsight to fix volume ownership (the container runs as uid 1000 but Docker creates volumes as root). The service SHALL include a healthcheck against `/health`.

#### Scenario: Hindsight service starts

- **WHEN** `docker compose up` is run with `OPENAI_API_KEY` configured
- **THEN** the Hindsight service starts, the API is accessible at `http://localhost:8888`, and the control plane UI is accessible at `http://localhost:9999`

#### Scenario: Hindsight uses same LLM provider

- **WHEN** the Hindsight service starts
- **THEN** it uses the `OPENAI_BASE_URL` and `OPENAI_API_KEY` from the host environment for LLM operations

### Requirement: Worker connects to Hindsight in Docker Compose

The Docker Compose worker service SHALL have `HINDSIGHT_URL` set to `http://hindsight:8888`. The worker service SHALL NOT depend on the Hindsight service being healthy (Hindsight is optional — tasks run without memory if Hindsight is unavailable).

#### Scenario: Worker uses local Hindsight

- **WHEN** the worker service starts in Docker Compose
- **THEN** it has `HINDSIGHT_URL=http://hindsight:8888` and can reach the Hindsight API

#### Scenario: Worker operates without Hindsight

- **WHEN** the Hindsight service is not running or unhealthy
- **THEN** the worker logs a warning during recall and continues task execution without memory context
