## Why

The worker runs as a separate Deployment from the server, with ~80% overlapping env vars, its own ServiceAccount/RBAC, and a Playwright sidecar. This doubles the Helm configuration surface and creates operational overhead (two deployments to monitor, configure, and debug). The worker also processes tasks sequentially — one at a time per replica — which creates a deadlock risk when a task-runner spawns sub-tasks via the MCP `new_task` tool and waits for them to complete. As agents start using Errand to its full potential (MCP-driven sub-task orchestration), concurrent task processing becomes essential.

Additionally, the Playwright MCP server currently runs as a per-worker sidecar without the `--isolated` flag, causing the second concurrent connection to fail due to browser profile locking. A standalone Playwright deployment with `--isolated` mode would support multiple concurrent task-runners safely while reducing resource duplication.

## What Changes

- Merge worker task processing into the server as an async `TaskManager` background task
- Use Postgres advisory lock for leader election — only one server replica runs the TaskManager at a time, with automatic failover if the leader pod dies
- Add `max_concurrent_tasks` setting (UI-configurable) controlling an asyncio semaphore for task admission
- Deploy Playwright MCP as a standalone K8s Deployment + Service (not a sidecar), with `--isolated` flag for concurrent session support
- **BREAKING**: Remove the separate worker Deployment, ServiceAccount, and RBAC from the Helm chart
- **BREAKING**: Remove the worker service from docker-compose; server runs task processing directly
- Move K8s RBAC (Jobs, ConfigMaps, Pods) to the server's ServiceAccount

## Capabilities

### New Capabilities

- `task-manager`: Async TaskManager class running as a FastAPI lifespan background task, with leader election via Postgres advisory lock, configurable concurrency via asyncio semaphore, and per-task heartbeat/log-streaming coroutines
- `playwright-standalone`: Standalone Playwright MCP deployment with `--isolated` mode, K8s Deployment + Service, and stable DNS-based connectivity for task-runners

### Modified Capabilities

- `task-worker`: Worker logic moves into the TaskManager — dequeue, settings resolution, container runtime orchestration, result handling, and retry logic all become async methods on the TaskManager class rather than a standalone `worker.py` entrypoint
- `container-runtime`: ContainerRuntime interface gains async variants for K8s runtime (async `prepare`, `run`, `result`, `cleanup`) to support concurrent task execution without thread pools
- `helm-deployment`: Remove worker Deployment, ServiceAccount, RBAC templates; add RBAC to server ServiceAccount; add Playwright Deployment + Service; add `max_concurrent_tasks` to server env vars
- `local-dev-environment`: Remove worker, DinD, and task-runner-build services from docker-compose; mount host Docker socket on errand service; use explicit named network (`errand-net`) so task-runner containers resolve compose service DNS; deploy Playwright as a separate service with `--isolated`
- `container-runtime` (additional): `DockerRuntime` supports `TASK_RUNNER_NETWORK` env var to attach task-runners to a named Docker network instead of `network_mode="host"`

## Impact

- **errand/worker.py** — refactored into `errand/task_manager.py` as an async class; standalone entrypoint removed
- **errand/main.py** — FastAPI lifespan starts/stops the TaskManager background task
- **errand/container_runtime.py** — `KubernetesRuntime` gains async methods; `DockerRuntime` stays sync (wrapped in `run_in_executor`)
- **helm/errand/templates/** — delete `worker-deployment.yaml`, worker SA/RBAC; add Playwright deployment + service; update `server-deployment.yaml` with RBAC and new env vars
- **testing/docker-compose.yml** — remove worker, DinD, and task-runner-build services; mount host Docker socket on errand service; add explicit `errand-net` named network; add standalone Playwright service
- **Settings** — new `max_concurrent_tasks` setting (default: 3) in settings registry and Task Management settings UI
- **RBAC** — server pod's ServiceAccount needs: jobs, configmaps, pods, pods/log, pods/exec
