## MODIFIED Requirements

### Requirement: Standalone Playwright K8s Deployment

The Helm chart SHALL deploy Playwright MCP as a separate Deployment and Service (not a sidecar). The Deployment SHALL use the existing `playwright.image` values. The Service SHALL expose the Playwright port for internal cluster access. The container entrypoint SHALL be overridden with a shell command that starts Xvfb then execs the MCP server with `--isolated`, `--port`, `--host 0.0.0.0`, and `--allowed-hosts *` (without `--headless`).

The Deployment SHALL include an `emptyDir` volume with `medium: Memory` and `sizeLimit: 2Gi` mounted at `/dev/shm` for Chrome shared memory. The memory resource limit SHALL be set to `768Mi`.

#### Scenario: Playwright accessible via service DNS

- **WHEN** a task-runner Job is created by the TaskManager
- **THEN** the task-runner connects to Playwright via the K8s Service DNS (e.g. `http://errand-playwright:8931/mcp`)

#### Scenario: Playwright pod restarts independently

- **WHEN** the Playwright pod crashes
- **THEN** K8s restarts it without affecting the server pods

### Requirement: Standalone Playwright in Docker Compose

The docker-compose configuration SHALL include a standalone Playwright service on the `errand-net` named network. The container entrypoint SHALL be overridden with a shell command that starts Xvfb then execs the MCP server with `--isolated` flag. The service SHALL specify `shm_size: '2gb'` for Chrome shared memory. The errand service SHALL reference the Playwright service by Docker Compose DNS name. Task-runner containers, attached to the same named network via `TASK_RUNNER_NETWORK`, SHALL resolve the Playwright service by name.

#### Scenario: Playwright available in local dev

- **WHEN** a developer runs `docker compose up`
- **THEN** Playwright starts as a standalone service with Xvfb and task-runners connect to it via Compose DNS
