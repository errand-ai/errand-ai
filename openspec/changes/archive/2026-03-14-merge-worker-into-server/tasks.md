## 1. Container Runtime Async Interface

- [x] 1.1 Add async method stubs to `ContainerRuntime` base class (`async_prepare`, `async_run`, `async_result`, `async_cleanup`) with default implementations that wrap sync methods via `run_in_executor`
- [x] 1.2 Implement native async methods on `KubernetesRuntime` using `kubernetes_asyncio` or async HTTP calls for Job/ConfigMap/Pod operations
- [x] 1.3 Implement `async_run` on `KubernetesRuntime` as an async generator yielding pod log lines
- [x] 1.4 Add tests for async runtime methods (mock K8s API, verify non-blocking behaviour)

## 2. TaskManager Core

- [x] 2.1 Create `errand/task_manager.py` with `TaskManager` class containing: advisory lock acquisition, poll loop, semaphore-based concurrency, and shutdown handling
- [x] 2.2 Implement `_acquire_leader_lock()` using `pg_try_advisory_lock` with a constant lock ID
- [x] 2.3 Implement `_poll_and_dispatch()` — dequeue task via `SELECT ... FOR UPDATE SKIP LOCKED`, create asyncio task for processing
- [x] 2.4 Implement `_run_task()` coroutine — settings resolution, container preparation, async runtime lifecycle, result handling, retry logic
- [x] 2.5 Read `max_concurrent_tasks` from settings DB on each poll cycle and update the semaphore

## 3. Migrate Worker Logic

- [x] 3.1 Move `read_settings()`, `resolve_profile()`, `dequeue_task()` from `worker.py` into `task_manager.py` as async methods
- [x] 3.2 Move `process_task_in_container()` logic into `TaskManager._run_task()`, replacing sync runtime calls with async variants
- [x] 3.3 Move per-task log streaming into an async coroutine using `async for line in runtime.async_run(handle)`
- [x] 3.4 Move per-task heartbeat into a periodic async task (`asyncio.create_task`) that updates `heartbeat_at` every 60 seconds, cancelled on task completion
- [x] 3.5 Move Valkey log publishing into the async log streaming coroutine (use async Redis client)
- [x] 3.6 Move MCP injection logic (errand, hindsight, litellm, cloud storage, playwright) — replace `POD_IP`-based Playwright URL with `PLAYWRIGHT_MCP_URL` env var
- [x] 3.7 Move git skills clone/refresh, SSH key injection, GitHub credential loading
- [x] 3.8 Move retry logic (`_schedule_retry`, `GitSkillsError` handling) and repeating task rescheduling
- [x] 3.9 Move result callback (`post_result_callback` equivalent via async httpx)

## 4. FastAPI Integration

- [x] 4.1 Add `TASK_MANAGER_ENABLED` env var check (default: `true`)
- [x] 4.2 Start `TaskManager.run()` as background asyncio task in FastAPI lifespan startup
- [x] 4.3 Stop TaskManager on lifespan shutdown — signal stop, await in-flight tasks with timeout
- [x] 4.4 Add `max_concurrent_tasks` to settings registry (default: 3, env var: `MAX_CONCURRENT_TASKS`)
- [x] 4.5 Add `max_concurrent_tasks` input to Task Management settings tab in frontend

## 5. Playwright Standalone

- [x] 5.1 Add `PLAYWRIGHT_MCP_URL` env var to the server; use it in MCP config injection instead of `POD_IP`-based URL construction
- [x] 5.2 Remove Playwright sidecar management code from task processing (start/stop/health-check of per-worker containers)
- [x] 5.3 Add `--isolated` flag to Playwright args in remaining Docker mode container startup (for backward compat during transition)

## 6. Helm Chart Updates

- [x] 6.1 Add ServiceAccount and RBAC (jobs, configmaps, pods, pods/log, pods/exec) to server Deployment
- [x] 6.2 Add task processing env vars to server Deployment (`CONTAINER_RUNTIME`, `TASK_RUNNER_IMAGE`, `ERRAND_MCP_URL`, `PLAYWRIGHT_MCP_URL`)
- [x] 6.3 Create `playwright-deployment.yaml` and `playwright-service.yaml` templates with `--isolated` flag
- [x] 6.4 Add `playwright.enabled` conditional to Playwright templates and `PLAYWRIGHT_MCP_URL` env var
- [x] 6.5 Delete `worker-deployment.yaml`, worker ServiceAccount, and worker RBAC templates
- [x] 6.6 Add `server.maxConcurrentTasks` to values.yaml and pass as `MAX_CONCURRENT_TASKS` env var
- [x] 6.7 Move worker-specific Helm values (`worker.replicaCount`, `worker.healthPort`) under `server` or remove

## 7. Docker Compose Updates

- [x] 7.1 Remove `worker`, `dind`, and `task-runner-build` services from `testing/docker-compose.yml` and `deploy/docker-compose.yml`
- [x] 7.2 Add explicit named network (`errand-net` with `name: errand-net`) to docker-compose; assign all services to it
- [x] 7.3 Mount `/var/run/docker.sock:/var/run/docker.sock` on `errand` service
- [x] 7.4 Add `CONTAINER_RUNTIME`, `TASK_RUNNER_IMAGE`, `TASK_RUNNER_NETWORK=errand-net` env vars to `errand` service (no `DOCKER_HOST` — uses local socket)
- [x] 7.5 Add standalone `playwright` service with `--isolated` flag
- [x] 7.6 Add `PLAYWRIGHT_MCP_URL` env var to `errand` service pointing to Playwright service
- [x] 7.7 Update `DockerRuntime.prepare()` to use `network=TASK_RUNNER_NETWORK` when set, falling back to `network_mode="host"` when unset (errand-desktop compatibility)

## 8. Cleanup

- [x] 8.1 Delete `errand/worker.py` standalone entrypoint (logic now in `task_manager.py`)
- [x] 8.2 Remove worker health server code (health endpoint now served by FastAPI's `/api/health`)
- [x] 8.3 Remove global `active_handle` and `_cleanup_active_container` (replaced by per-task handle tracking)
- [x] 8.4 Remove Playwright sidecar start/stop/health-check functions (`start_playwright_container`, `cleanup_playwright_container`, `health_check_playwright` for Docker mode)
- [x] 8.5 Update CLAUDE.md — remove worker references, update architecture diagram, update docker-compose instructions

## 9. Tests

- [x] 9.1 Test leader election — advisory lock acquisition, standby behaviour, failover on disconnect
- [x] 9.2 Test concurrency — semaphore limits concurrent tasks, setting changes update semaphore
- [x] 9.3 Test per-task lifecycle — settings resolution, container runtime calls, result handling, cleanup
- [x] 9.4 Test graceful shutdown — in-flight tasks complete, lock released
- [x] 9.5 Test deadlock prevention — parent task + sub-task can run concurrently when max >= 2
- [x] 9.6 Test Playwright URL injection — uses `PLAYWRIGHT_MCP_URL` env var, not `POD_IP`
- [x] 9.7 Verify existing worker tests still pass against TaskManager methods
