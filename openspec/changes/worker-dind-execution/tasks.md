## 1. Database and Model

- [x] 1.1 Create Alembic migration adding nullable `output` text column to `tasks` table
- [x] 1.2 Add `output` field to `Task` SQLAlchemy model (`Mapped[Optional[str]]`, `Text`, nullable)
- [x] 1.3 Add `output` field to `TaskUpdate` Pydantic model (optional str)
- [x] 1.4 Add `output` field to `TaskResponse` Pydantic model and `from_task` method

## 2. Backend API

- [x] 2.1 Update `update_task` endpoint to accept and persist `output` field
- [x] 2.2 Update `list_tasks` and `get_task` responses to include `output` field (via updated TaskResponse)
- [x] 2.3 Add `output` to `_task_to_dict` helper so WebSocket events include output

## 3. Task Runner Image

- [x] 3.1 Create `task-runner/` directory with `Dockerfile`: multi-stage build from `busybox:1.37-musl` (copy `/bin/busybox` as `/usr/local/bin/cat`) and `gcr.io/distroless/static-debian12:nonroot` base, `WORKDIR /workspace`, `ENTRYPOINT ["/usr/local/bin/cat", "/workspace/prompt.txt"]`
- [x] 3.2 Verify image builds and runs: create test prompt file, run container, confirm output matches

## 4. Worker DinD Connection

- [x] 4.1 Add `docker` Python SDK to `requirements.txt`
- [x] 4.2 Add `DOCKER_HOST` and `TASK_RUNNER_IMAGE` environment variable reads to worker startup
- [x] 4.3 Implement Docker client initialisation with exponential backoff retry (1s to 30s) waiting for DinD readiness
- [x] 4.4 Add graceful shutdown: ensure running containers are stopped/removed when worker receives SIGTERM

## 5. Worker Task Execution

- [x] 5.1 Implement settings reader: read `mcp_servers` and `credentials` from `settings` table using `Setting` model (default to empty JSON object and empty list respectively)
- [x] 5.2 Implement `put_archive` helper: create tar archive from dict of `{filename: content}` for copying files into container
- [x] 5.3 Replace `process_task` placeholder with DinD execution: `containers.create()` with task runner image and credentials as env vars, `put_archive()` to copy `prompt.txt` (task description) and `mcp.json` into `/workspace/`, `start()`, `wait()`, `logs()` capture, `remove()`
- [x] 5.4 Implement output truncation: truncate captured logs to configurable max (default 1MB), append truncation marker if exceeded
- [x] 5.5 Update task completion flow: on success (exit code 0) set status to `review` with new position at bottom of Review column; on failure set status to `failed`; store captured output in `output` field; publish `task_updated` event
- [x] 5.6 Handle container errors: catch Docker API errors (image not found, daemon errors), set task to `failed`, log error, continue polling

## 6. Docker Compose

- [x] 6.1 Add `dind` service to `docker-compose.yml`: `docker:27-dind`, `privileged: true`, `DOCKER_TLS_CERTDIR=""`, healthcheck on Docker daemon port 2375
- [x] 6.2 Update `worker` service: add `DOCKER_HOST=tcp://dind:2375`, add `TASK_RUNNER_IMAGE` env var, add dependency on `dind` service healthy
- [x] 6.3 Verify local stack: `docker compose up --build`, create a task, move to pending, confirm worker picks it up, runs in DinD, output captured, task moves to review

## 7. Helm Chart

- [x] 7.1 Add `taskRunner` and `dind` sections to `values.yaml`: `taskRunner.image.repository` (default `ghcr.io/<repo>-task-runner`), `taskRunner.image.tag` (default empty = appVersion), `dind.image` (default `docker:27-dind`)
- [x] 7.2 Update `worker-deployment.yaml`: add `dind` sidecar container (`privileged: true`, `DOCKER_TLS_CERTDIR=""`), add `DOCKER_HOST=tcp://localhost:2375` and `TASK_RUNNER_IMAGE` env vars to worker container

## 8. Frontend Settings

- [x] 8.1 Update Settings page MCP section: replace read-only placeholder with expandable/collapsible text box (collapsed by default)
- [x] 8.2 Add JSON validation on the MCP text box: parse on save, show error if invalid JSON
- [x] 8.3 Add Save button for MCP configuration: send `PUT /api/settings` with `{"mcp_servers": <parsed JSON>}`, show success/error indication

## 9. CI Pipeline

- [x] 9.1 Add `build-task-runner` job to `.github/workflows/build.yml`: same structure as `build-backend`, context `./task-runner`, push to `ghcr.io/<repo>-task-runner`, depends on `version` and `test`
- [x] 9.2 Update `helm` job to depend on `build-task-runner` in addition to `build-frontend` and `build-backend`

## 10. Tests

- [x] 10.1 Add backend tests: task output field in create/update/list responses, output included in task_updated events
- [x] 10.2 Add frontend tests: MCP settings section expand/collapse, JSON validation, save functionality
- [x] 10.3 Add worker tests: settings reader (mcp_servers, credentials with defaults), output truncation logic, task status transitions (review on success, failed on error)
