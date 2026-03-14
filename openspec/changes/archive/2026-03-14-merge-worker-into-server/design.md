## Context

The server (FastAPI + uvicorn) and worker (`python worker.py`) share the same Docker image but run as separate K8s Deployments. The worker polls the DB for pending tasks, dequeues one at a time via `SELECT ... FOR UPDATE SKIP LOCKED`, processes it in a container (Docker or K8s Job), and updates results. The server already runs background asyncio tasks (zombie cleanup, task scheduler) using Valkey distributed locks for replica coordination.

The worker's `process_task_in_container` function is synchronous and uses a global `active_handle` — explicitly a single-task-at-a-time design. The K8s container runtime makes synchronous HTTP calls to the K8s API, which is wasteful of event loop capacity.

Playwright MCP runs as a worker pod sidecar without `--isolated`, meaning the default persistent profile mode locks out concurrent connections via Chromium's `SingletonLock` file.

## Goals / Non-Goals

**Goals:**

- Eliminate the worker Deployment and its configuration duplication
- Enable concurrent task processing with a user-configurable limit
- Prevent deadlocks when task-runners spawn sub-tasks via MCP
- Deploy Playwright as a standalone service supporting concurrent sessions
- Maintain leader-elected single-processor semantics across server replicas

**Non-Goals:**

- Making DockerRuntime fully async (sync + `run_in_executor` is fine for local dev)
- Horizontal scaling of task processing across replicas (leader election means one active processor)
- Distributed task queue (Redis/Celery) — the DB-based approach with `SKIP LOCKED` is sufficient
- Auto-scaling based on queue depth (KEDA can be re-evaluated later)

## Decisions

### Decision 1: Postgres advisory lock for leader election

**Choice:** Use `pg_try_advisory_lock(constant_id)` in the TaskManager's poll loop. The lock is session-scoped — it releases automatically when the DB connection drops (pod crash). Only the lock holder polls and dequeues tasks. Non-leaders sleep and retry the lock periodically.

**Alternative considered:** K8s Lease-based leader election. This requires the K8s client library and RBAC for Lease objects, adding dependencies for something Postgres handles natively.

**Alternative considered:** Valkey-based distributed lock (as used by zombie cleanup). Advisory locks are simpler — no TTL management, no renewal, automatic release on disconnect.

**Rationale:** The server already has a Postgres connection. Advisory locks are zero-config, session-scoped (no TTL to manage), and automatically released on pod crash — exactly the semantics needed.

### Decision 2: TaskManager as a FastAPI lifespan background task

**Choice:** The TaskManager runs as an `asyncio.create_task()` in FastAPI's lifespan handler. It owns the poll loop, dequeues tasks, and spawns per-task coroutines controlled by an `asyncio.Semaphore(max_concurrent_tasks)`.

**Alternative considered:** A separate thread running the existing synchronous worker loop. This would avoid refactoring but can't share the async event loop, making Valkey pub/sub and DB access awkward (separate sync connections needed).

**Rationale:** FastAPI is already async. Running the TaskManager in the same event loop gives it direct access to async DB sessions, Valkey pub/sub, and event publishing — no sync/async bridging needed.

### Decision 3: Async KubernetesRuntime, sync DockerRuntime

**Choice:** Add async methods (`async_prepare`, `async_run`, `async_result`, `async_cleanup`) to `KubernetesRuntime` using the async K8s client or `httpx`. `DockerRuntime` stays synchronous, wrapped in `asyncio.get_event_loop().run_in_executor()`.

**Alternative considered:** Making both runtimes async. The Docker SDK has no async support, so this would require replacing it with `aiodocker` — an unnecessary dependency change for local dev only.

**Rationale:** K8s is the production runtime where concurrency matters. Docker is for local dev where single-task processing is fine. The `run_in_executor` wrapper is already in use today.

### Decision 4: Standalone Playwright with `--isolated` mode

**Choice:** Deploy Playwright MCP as a separate K8s Deployment + Service with `--isolated` flag. Task-runners connect via stable service DNS (e.g. `http://errand-playwright:3000`). In docker-compose, Playwright runs as a standalone service.

**Alternative considered:** Keep Playwright as a sidecar on the server pod. This wastes memory on non-leader replicas and couples Playwright lifecycle to the server.

**Rationale:** `--isolated` mode gives each Streamable HTTP session its own `BrowserContext` (isolated cookies, localStorage, navigation). A single Playwright instance can safely serve multiple concurrent task-runners. Standalone deployment means one Chromium process for the whole cluster instead of one per pod.

### Decision 5: `max_concurrent_tasks` as a database setting

**Choice:** Store `max_concurrent_tasks` in the settings registry (default: 3). The TaskManager reads it on each poll cycle and adjusts the semaphore. Changes take effect on the next dequeue cycle without restart.

**Alternative considered:** Environment variable only. This would require a pod restart to change concurrency.

**Rationale:** Consistent with other runtime-adjustable settings (system_prompt, mcp_servers, etc.). The settings UI already has a Task Management tab where this fits naturally.

### Decision 6: Per-task coroutines for heartbeat and log streaming

**Choice:** Each task gets its own asyncio coroutine that handles: settings resolution, container preparation, log streaming (async generator from K8s pod logs or sync Docker logs via executor), heartbeat updates (periodic DB write), Valkey log publishing, result handling, and retry logic.

**Alternative considered:** Thread pool with one thread per task (current pattern). This doesn't scale well and can't share async resources.

**Rationale:** Async coroutines are lightweight, share the event loop's resources, and integrate naturally with async DB sessions and Valkey pub/sub. The semaphore bounds concurrency to prevent resource exhaustion.

### Decision 7: Remove DinD — host Docker socket + named network

**Choice:** Replace the DinD (Docker-in-Docker) container with a host Docker socket mount (`/var/run/docker.sock`). Define an explicit named Docker network (`errand-net`) in docker-compose and attach task-runner containers to it instead of using `network_mode="host"`. A `TASK_RUNNER_NETWORK` env var tells `DockerRuntime` which network to attach spawned containers to; when unset, falls back to `network_mode="host"` (errand-desktop behaviour).

**Alternative considered:** Socket mount + `network_mode="host"` on task-runners + published ports. Task-runners would reach compose services via `localhost:<host-port>`. This avoids the named network but requires port mapping awareness (e.g. gdrive-mcp publishes 8081→8080 on the host, so URLs need rewriting). Fragile and error-prone.

**Alternative considered:** Keep DinD. This works but adds a privileged container, a separate Docker daemon, a task-runner-build sidecar, and nested image caching — all unnecessary overhead since the errand-desktop app already creates containers directly on the host Docker daemon.

**Rationale:** With a named network, task-runner containers resolve compose service DNS names (`errand:8000`, `playwright:3000`, `gdrive-mcp:8080`) without any URL rewriting. Outbound internet access (LLM APIs, GitHub, errand-cloud) works via Docker bridge NAT. The communication pattern is entirely task-runner-initiates-outbound, so no inbound connectivity is needed. This eliminates the DinD container, the privileged flag, and the task-runner-build sidecar, reducing the compose stack complexity. The `TASK_RUNNER_NETWORK` fallback preserves `network_mode="host"` for errand-desktop where no named network exists.

## Risks / Trade-offs

**[Server pod blast radius]** → Task processing failures could theoretically affect API availability. Mitigated by: all heavy computation happens in task-runner containers (not the server process), the TaskManager only orchestrates Jobs and streams logs (I/O bound, not CPU bound), and unhandled exceptions in per-task coroutines are caught and don't propagate to the event loop.

**[Leader failover latency]** → When the leader pod dies, the standby must detect the advisory lock release and acquire it. Postgres releases session-scoped locks when the connection drops (typically <30 seconds). The standby polls for the lock every 10-15 seconds. Worst case: ~45 seconds of no task processing during failover. Acceptable given tasks are typically minutes-long.

**[RBAC on server pod]** → The server's ServiceAccount now needs K8s Job/ConfigMap/Pod permissions. This increases the server's privilege scope. Mitigated by: RBAC is namespace-scoped (not cluster-wide), and the same permissions the worker had.

**[Playwright as single point of failure]** → A standalone Playwright instance means all task-runners depend on one pod. Mitigated by: K8s restarts it on failure, most tasks don't use Playwright, and the task-runner gracefully handles Playwright unavailability (proceeds without browser tools).

**[Migration complexity]** → This is a breaking change to the deployment topology. Existing Helm deployments need to remove the worker and add RBAC to the server. Mitigated by: clear upgrade notes and the Helm chart handling it automatically on `helm upgrade`.
