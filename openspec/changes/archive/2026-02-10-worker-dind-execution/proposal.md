## Why

The worker currently polls for pending tasks and transitions them to running, but performs no actual processing. Tasks need to be executed in isolated, disposable containers to provide security boundaries and reproducible environments. Docker-in-Docker (DinD) sidecars provide container execution capability without granting host Docker socket access. This first implementation establishes the execution pipeline — container creation, config injection, credential passing, output capture, and lifecycle management — with a stub command (`cat` the task prompt file) so that LLM-based processing can be layered on in a later change.

## What Changes

- Worker uses the Docker SDK with a create→copy→start lifecycle: `containers.create()` creates the container without starting it, `put_archive()` copies all input files into the stopped container, then `start()` runs the command. This guarantees all files exist before the entrypoint executes and is compatible with minimal base images.
- New Dockerfile for the task runner container image (distroless base, non-root user, no shell, no package manager)
- No volume mounts into task containers — all input files (task prompt, `mcp.json`) are copied in via `put_archive()` on the created-but-not-started container
- Task prompt (description and any future system prompt) is written as a file (`/workspace/prompt.txt`) into the container via `put_archive()`, not passed as a command argument or environment variable. This avoids Linux `execve` argument length limits (128KB per arg) and shell escaping issues with special characters in prompts.
- Worker reads MCP server configuration from the settings and copies it into the container as `/workspace/mcp.json` before execution
- Worker retrieves a list of credential key/value pairs and passes them as environment variables when creating the container. Credentials are short strings (API keys, tokens) that fit well within env var limits. The specific variables will be defined in a future change; initially an empty list.
- Task runner container runs `cat /workspace/prompt.txt` as the initial stub command (reads the prompt file and outputs it)
- Worker captures container stdout/stderr via `container.logs()` after `container.wait()` and stores the output via the backend API
- Task moves to `review` status on completion; container is removed; worker returns to idle polling
- MCP server configuration on the Settings page becomes an editable expandable text box (replacing read-only placeholder)
- Task model gains an `output` text field for storing execution results
- Backend exposes a credentials endpoint returning key/value pairs for container environment variables (initially empty)
- CI pipeline builds and publishes the task runner image alongside frontend and backend images
- Docker Compose adds a DinD service for local development
- Helm chart adds a DinD sidecar container to the worker deployment

## Capabilities

### New Capabilities
- `task-runner-image`: Dockerfile for the distroless container that runs inside DinD to execute tasks (non-root `nonroot` user, no shell, no package manager). Uses `distroless/static` with busybox `cat` for the stub; migrates to `distroless/python3` when Python execution is added.

### Modified Capabilities
- `task-worker`: Add DinD-based task execution — create container with credentials as env vars, copy config files via put_archive, start container, wait for completion, capture logs, remove container, transition task to review
- `task-api`: Add `output` text field to task model and API responses; PATCH endpoint accepts `output` for storing execution results; add `GET /api/settings/credentials` endpoint returning key/value pairs for container env vars (initially empty list)
- `admin-settings-ui`: MCP server configuration section becomes an editable expandable text box with save functionality (replacing read-only placeholder)
- `ci-pipelines`: Add build job for the task runner image (build, tag, push to GHCR alongside existing images)
- `helm-deployment`: Add DinD sidecar container to worker deployment with shared Docker socket; add `DOCKER_HOST` env var to worker container
- `local-dev-environment`: Add DinD service to Docker Compose; configure worker service with `DOCKER_HOST` pointing to the DinD service

## Impact

- **Backend**: New `output` column on tasks table (Alembic migration), updated task model and API serialization, new credentials endpoint
- **Worker**: Major changes — Docker SDK dependency, DinD connection, container lifecycle management (create→copy→start→wait→logs→remove), config injection, credential passing, output capture
- **Frontend**: Settings page MCP section changes from read-only to editable
- **Infrastructure**: DinD sidecar in Helm worker deployment; DinD service in Docker Compose; new container image in CI
- **Security**: No volume mounts, distroless base image (no shell, no package manager, non-root), DinD isolation (no host Docker socket access), credentials passed as env vars (not written to filesystem), prompts passed as files (not command args — avoids /proc leaks)
- **Dependencies**: `docker` Python SDK added to worker/backend requirements
