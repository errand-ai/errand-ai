## 1. Project Setup

- [x] 1.1 Create new repository `errand-desktop` with Swift Package targeting macOS 26+
- [x] 1.2 Add Containerization Swift package as a dependency
- [x] 1.3 Set up Apple Developer ID certificate and provisioning
- [x] 1.4 Configure CI/CD for building, signing, and notarizing the app

## 2. Menu Bar App Shell

- [x] 2.1 Implement `MenuBarExtra` with status icon (idle/starting/running/degraded states)
- [x] 2.2 Implement service status popover (service list, status indicators, ports)
- [x] 2.3 Add "Start All", "Stop All", "Open in Browser" buttons
- [x] 2.4 Implement settings window (API keys, OIDC config, LiteLLM toggle, ports)
- [x] 2.5 Implement log viewer window with service filter
- [x] 2.6 Implement "Launch at Login" via `SMAppService`
- [x] 2.7 Implement first-run setup assistant (API keys, image pull progress)

## 3. Container Orchestration

- [x] 3.1 Implement OCI image pull via Containerization framework (with progress reporting)
- [x] 3.2 Implement container creation with environment variables and volume mounts
- [x] 3.3 Implement container start/stop/remove lifecycle
- [x] 3.4 Implement health checking (TCP for Postgres/Valkey, HTTP for backend)
- [x] 3.5 Implement dependency-ordered startup (Postgres → Valkey → Backend → Worker)
- [x] 3.6 Implement reverse-order shutdown
- [x] 3.7 Implement inter-container networking (discover IPs, inject connection URLs)

## 4. Persistent Storage

- [x] 4.1 Create `~/Library/Application Support/ContentManager/data/` structure on first run
- [x] 4.2 Implement volume mounts for PostgreSQL data directory
- [x] 4.3 Implement volume mounts for Valkey persistence
- [x] 4.4 Implement config.json read/write for app settings
- [x] 4.5 Implement "Reset Data" functionality

## 5. Container Bridge API

- [x] 5.1 Implement local HTTP server (localhost-bound) in the Swift app
- [x] 5.2 Implement `POST /containers` — create and start task-runner container
- [x] 5.3 Implement `GET /containers/{id}/logs` — SSE log streaming
- [x] 5.4 Implement `GET /containers/{id}/status` — container status and exit code
- [x] 5.5 Implement `GET /containers/{id}/output` — read `/output/result.json`
- [x] 5.6 Implement `DELETE /containers/{id}` — remove container
- [x] 5.7 Implement bearer token authentication (generated at startup, passed to worker)

## 6. AppleContainerRuntime (Python worker side)

- [x] 6.1 Add `AppleContainerRuntime` to `backend/container_runtime.py` implementing the ContainerRuntime interface via HTTP calls to the bridge API
- [x] 6.2 Add `CONTAINER_RUNTIME=apple` selection in runtime factory
- [x] 6.3 Add tests for AppleContainerRuntime (mocking bridge API)

## 7. LiteLLM Integration

- [x] 7.1 Add LiteLLM container management (pull, create, start, stop)
- [x] 7.2 Implement LiteLLM config UI (model providers, API keys)
- [x] 7.3 Persist LiteLLM `config.yaml` to Application Support
- [x] 7.4 Route backend/worker `OPENAI_BASE_URL` through LiteLLM when enabled

## 8. Database Migrations

- [x] 8.1 Run Alembic migrations on startup (exec into backend container or dedicated migration container)
- [x] 8.2 Handle migration failures gracefully (show error in UI, don't start backend)

## 9. Distribution

- [x] 9.1 Set up DMG packaging (app bundle + Applications symlink)
- [x] 9.2 Automate code signing and notarization in CI
- [x] 9.3 Implement auto-update check against GitHub Releases
- [x] 9.4 Create GitHub Actions workflow for building and publishing releases
