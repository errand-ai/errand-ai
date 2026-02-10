## Context

The worker (`backend/worker.py`) currently polls for pending tasks, sets them to `running`, calls a placeholder `process_task` (2-second sleep), then sets them to `completed`. It has direct database access via SQLAlchemy async sessions and publishes events via Valkey pub/sub.

The worker shares the backend Docker image and codebase. In Docker Compose, it runs as a separate service (`python worker.py`). In Kubernetes, it runs as a separate Deployment using the backend image.

Settings are stored in a `settings` table (key/value with JSONB values) accessed via `GET/PUT /api/settings` (admin-only). The MCP server configuration section on the Settings page is currently a read-only placeholder.

## Goals / Non-Goals

**Goals:**
- Establish the container execution pipeline: create → copy files (prompt, config) → start → wait → capture output → remove
- Run tasks in isolated Docker containers via a DinD sidecar
- Store task output for later viewing
- Make MCP server configuration editable on the Settings page
- Support credential injection into task containers via environment variables
- Build and publish the task runner image in CI

**Non-Goals:**
- LLM integration or intelligent task processing (future change)
- Defining specific credential variables (future change — initially empty list)
- UI for viewing task output (future change — output is stored but not displayed)
- TLS for DinD communication (can be added later if needed)
- KEDA autoscaling changes (existing ScaledObject scales workers, DinD is a sidecar)

## Decisions

### 1. Container lifecycle: create → put_archive → start

**Decision:** Use the Docker SDK's `containers.create()` → `put_archive()` → `start()` → `wait()` → `logs()` → `remove()` sequence.

**Alternatives considered:**
- `docker run` (detached) → `docker cp` → `docker exec`: Requires an idle process (`sleep infinity`) to keep the container alive while copying files. Distroless/minimal images have no shell, so `sleep` isn't available. Also adds complexity (must manage idle process, stop container separately).
- `docker run` with volume mounts: Proposal explicitly excludes volume mounts for security reasons.

**Rationale:** The create-copy-start pattern guarantees files exist before the entrypoint runs, works with any base image (no shell required for idle process), and produces a clean lifecycle — one command, one exit, one set of logs. The `put_archive` step copies all input files (`/workspace/prompt.txt`, `/workspace/mcp.json`) in a single tar archive.

### 2. Task prompt passed as file, not command argument

**Decision:** The worker writes the task description (and in future, the full LLM prompt including system prompt) to `/workspace/prompt.txt` inside the container via `put_archive()`. The container command reads this file (stub: `cat /workspace/prompt.txt`). Credentials remain as environment variables.

**Alternatives considered:**
- Pass prompt as command argument (`echo "long prompt text..."`): Linux `execve` enforces `MAX_ARG_STRLEN` of 128KB per argument and `ARG_MAX` of ~2-6MB for all args + env combined. LLM prompts with system prompt + task description + tool definitions could approach or exceed these limits as the system grows. Also requires careful shell escaping of special characters.
- Pass prompt as environment variable: Subject to the same `ARG_MAX` pool as command arguments. Additionally, env vars are visible via `/proc/<pid>/environ` to other processes, leaking prompt content.

**Rationale:** File-based prompt delivery has no size limit (writes directly to container filesystem layer via `put_archive`), requires no escaping, and avoids `/proc` leaks. The `put_archive` mechanism is already used for `mcp.json`, so this adds no new infrastructure — just another file in the tar archive. Short credentials (API keys, tokens) remain as env vars since they're small and follow standard container conventions.

### 3. Task runner base image: distroless

**Decision:** Use `gcr.io/distroless/static-debian12:nonroot` as the base image for the task runner container. A multi-stage build copies a statically-linked `cat` binary from `busybox:1.37-musl` into the image. The container runs as the built-in `nonroot` user (UID 65532). There is no shell, no package manager, and no other executables.

```dockerfile
FROM busybox:1.37-musl AS tools
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=tools /bin/busybox /usr/local/bin/cat
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/cat", "/workspace/prompt.txt"]
```

**Migration path to Python:** When the task runner needs Python execution (future change), the base switches to `gcr.io/distroless/python3-debian12:nonroot`. Dependencies are installed in a `python:3.12` build stage and copied to the distroless runtime. The security model (no shell, no package manager, non-root) is preserved across the migration.

**Alternatives considered:**
- `alpine:3.19` with hardening (remove `apk`, add non-root user): More attack surface — Alpine includes a shell (`/bin/sh`), which enables arbitrary command execution if an attacker gains code injection. Removing `apk` helps but the shell remains. ~5MB vs ~3MB for distroless+busybox.
- `scratch`: No user database (`/etc/passwd`), no CA certs, no tzdata. Would need to copy all of these manually.
- `ubuntu-minimal`: Much larger (~30MB), includes shell and many unnecessary utilities.

**Rationale:** Distroless provides the strongest security posture out of the box: no shell means an attacker with code execution cannot run arbitrary commands; no package manager means no ability to install tools. The built-in `nonroot` user eliminates the need for manual user creation. The only executable is `cat` (busybox), strictly limiting what the container can do. The ~3MB image size is smaller than Alpine.

### 4. Worker reads settings/credentials from DB directly

**Decision:** The worker reads MCP configuration and credentials from the `settings` table using the existing SQLAlchemy `Setting` model, not via the backend HTTP API.

**Alternatives considered:**
- Worker calls `GET /api/settings` via HTTP: Would require the worker to authenticate (it has no JWT tokens) or adding an unauthenticated internal endpoint. Adds HTTP client dependency and network hop for something the worker can read directly.

**Rationale:** The worker already has a database session for task dequeue and status updates. Reading settings from the same session is simpler, faster, and requires no additional auth or networking. Credentials are stored as a JSONB value under the `credentials` key in the settings table (list of `{key, value}` objects). MCP config is stored under the `mcp_servers` key.

### 5. Credentials stored in existing settings table

**Decision:** Store container credentials as a settings entry with key `credentials`, value `[]` (initially empty list of `{"key": "...", "value": "..."}` objects). Manage via the existing `PUT /api/settings` admin endpoint — no dedicated credentials endpoint needed.

**Alternatives considered:**
- Dedicated `GET/PUT /api/settings/credentials` endpoint: Adds API surface for something the existing settings API already handles. The JSONB value column supports any structure.
- Kubernetes Secrets mounted into worker: Would work in K8s but not in Docker Compose. Adds K8s-specific configuration complexity.

**Rationale:** The settings table already stores arbitrary JSONB values. Credentials fit naturally as another settings entry. The admin can manage them via the same settings UI. In future, if credential management needs more sophistication (rotation, encryption at rest), a dedicated system can replace this.

### 6. Output stored via direct DB write

**Decision:** Worker writes task output to an `output` text column on the tasks table, using the same DB session pattern it uses for status updates. The PATCH API also accepts `output` for completeness.

**Alternatives considered:**
- Worker calls `PATCH /api/tasks/{id}` via HTTP: Same auth problem as settings — worker has no JWT. Unnecessary network hop.
- Separate `task_outputs` table: Over-engineering for a single text field. Can be refactored later if output grows in complexity (structured sections, streaming, etc.).

**Rationale:** Simple text column, same write pattern as existing status updates. The `output` field is included in `TaskResponse` for future UI consumption.

### 7. DinD without TLS for initial implementation

**Decision:** Run DinD with `DOCKER_TLS_CERTDIR=""` (TLS disabled). Worker connects via `tcp://localhost:2375` (K8s sidecar) or `tcp://dind:2375` (Docker Compose).

**Alternatives considered:**
- DinD with TLS (`DOCKER_TLS_CERTDIR=/certs`): Requires shared certificate volume, cert generation, and configuring the Docker client with TLS certs. Adds significant complexity.

**Rationale:** In K8s, the DinD sidecar runs in the same pod — communication is localhost, not traversing a network. In Docker Compose, communication is on the internal Docker network. TLS can be added if DinD is moved to a separate service/pod in future.

### 8. DinD sidecar pattern in Kubernetes

**Decision:** Add `docker:dind` as a sidecar container in the worker Deployment pod spec. The worker container and DinD container share the pod's network namespace (localhost communication).

**Alternatives considered:**
- Separate DinD Deployment + Service: Workers would need to share a single DinD instance, introducing contention and requiring unique container names. Sidecar gives each worker its own isolated DinD.
- Host Docker socket mount: Breaks container isolation — the worker could control any container on the node. Unacceptable security risk.

**Rationale:** Sidecar pattern gives each worker pod its own DinD instance. No shared state, no contention, clean lifecycle (DinD starts and stops with the worker). DinD needs `privileged: true` in the pod spec.

### 9. Task runner image in CI

**Decision:** Add a `build-task-runner` job to the CI pipeline, parallel to `build-frontend` and `build-backend`. Same tagging scheme (version from `VERSION` file). Image pushed to `ghcr.io/<repo>-task-runner`.

**Rationale:** Follows the existing CI pattern exactly. The `helm` job depends on all three build jobs. The task runner image tag is configured in Helm values and defaults to `appVersion`.

### 10. Task completes to `review` status (not `completed`)

**Decision:** After successful container execution, worker sets task status to `review`. On failure, status is set to `failed` (existing behavior).

**Rationale:** The `review` column is for tasks that have been processed and need human review before being marked complete. This matches the kanban workflow described in the proposal.

## Risks / Trade-offs

**[DinD requires privileged mode]** → The DinD sidecar needs `privileged: true` in the K8s pod spec. This grants elevated permissions to the DinD container. Mitigation: only the DinD container is privileged, not the worker. Task containers run inside DinD's isolated Docker daemon.

**[Task runner image must be pre-pulled in DinD]** → Each new worker pod's DinD starts fresh — no cached images. The first task execution will pull the task runner image. Mitigation: the distroless-based image is small (~3MB). For production, consider pre-pulling via an init container or using a local registry.

**[Output size unbounded]** → The `output` text column has no size limit. A runaway container could produce enormous output. Mitigation: worker truncates captured output to a configurable maximum (e.g. 1MB) before storing.

**[DinD startup time]** → DinD takes a few seconds to initialise its Docker daemon. Worker must wait for DinD to be ready before creating containers. Mitigation: worker retries Docker connection with exponential backoff at startup.

**[Container cleanup on worker crash]** → If the worker crashes mid-execution, the task container is orphaned inside DinD. Since DinD is a sidecar, it will be terminated when the pod restarts, cleaning up orphaned containers. In Docker Compose, manual cleanup may be needed.

## Migration Plan

1. Add `output` column to tasks table via Alembic migration (nullable text, no default)
2. Deploy backend with updated model/API first — backwards compatible (output is optional)
3. Deploy worker with DinD sidecar — requires Helm chart update for sidecar + privileged mode
4. Deploy task runner image — must be available in registry before workers can use it
5. Rollback: revert worker to previous image (no DinD), revert Helm chart (remove sidecar). Output column can remain (nullable, unused).

## Open Questions

- **Output truncation limit**: What maximum output size should the worker enforce? Proposed: 1MB.
- **DinD image tag**: Pin to specific version (e.g. `docker:27-dind`) or use `docker:dind` (latest)?
- **Task runner image pull policy**: Use `IfNotPresent` (faster, cached) or `Always` (ensures latest)?
