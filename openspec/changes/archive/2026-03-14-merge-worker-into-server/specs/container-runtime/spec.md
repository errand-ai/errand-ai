## MODIFIED Requirements

### Requirement: ContainerRuntime abstract interface

The ContainerRuntime SHALL define both synchronous and asynchronous lifecycle methods. The synchronous methods (`prepare`, `run`, `result`, `cleanup`) SHALL remain for backward compatibility with `DockerRuntime`. The asynchronous methods (`async_prepare`, `async_run`, `async_result`, `async_cleanup`) SHALL be added with default implementations that call the synchronous versions via `asyncio.get_event_loop().run_in_executor()`. Runtimes that support native async (e.g. `KubernetesRuntime`) SHALL override the async methods directly.

#### Scenario: Sync interface unchanged

- **WHEN** `DockerRuntime` is used
- **THEN** the synchronous `prepare`, `run`, `result`, `cleanup` methods work as before

#### Scenario: Async interface available

- **WHEN** `KubernetesRuntime` is used by the TaskManager
- **THEN** the TaskManager calls `async_prepare`, `async_run`, `async_result`, `async_cleanup` which execute without blocking the event loop

#### Scenario: Default async wraps sync

- **WHEN** a runtime does not override async methods (e.g. `DockerRuntime`)
- **THEN** the default async methods run the sync versions in a thread executor

### Requirement: KubernetesRuntime async methods

The `KubernetesRuntime` SHALL override `async_prepare`, `async_run`, `async_result`, and `async_cleanup` with native async implementations using the async Kubernetes client (`kubernetes_asyncio`) or `httpx` for K8s API calls. The `async_run` method SHALL yield log lines as an async generator from the pod's log stream. These async methods SHALL support concurrent execution — multiple task containers can be managed simultaneously without thread contention.

#### Scenario: Async K8s Job creation

- **WHEN** `async_prepare` is called
- **THEN** the ConfigMap and Job are created via async K8s API calls without blocking the event loop

#### Scenario: Async log streaming

- **WHEN** `async_run` is called
- **THEN** pod log lines are yielded as an async iterator, allowing other coroutines to run between log lines

#### Scenario: Concurrent K8s tasks

- **WHEN** 3 tasks are being processed concurrently via the K8s runtime
- **THEN** all 3 have independent async log streams and lifecycle management without thread pool exhaustion

### Requirement: Runtime selection unchanged

The runtime selection via `CONTAINER_RUNTIME` environment variable SHALL remain unchanged. The `create_runtime()` factory function SHALL return the same runtime types as before. The TaskManager SHALL call async methods on the returned runtime.

#### Scenario: K8s runtime in production

- **WHEN** `CONTAINER_RUNTIME=kubernetes`
- **THEN** `KubernetesRuntime` is used with native async methods

#### Scenario: Docker runtime in local dev

- **WHEN** `CONTAINER_RUNTIME` is unset (default `docker`)
- **THEN** `DockerRuntime` is used with sync methods wrapped in executor

### Requirement: DockerRuntime supports named network for task-runner containers

When the `TASK_RUNNER_NETWORK` environment variable is set, `DockerRuntime.prepare()` SHALL attach task-runner containers to the specified Docker network (using the `network` parameter) instead of using `network_mode="host"`. When `TASK_RUNNER_NETWORK` is unset, `DockerRuntime` SHALL fall back to `network_mode="host"` for backward compatibility with errand-desktop.

#### Scenario: Named network in docker-compose

- **WHEN** `TASK_RUNNER_NETWORK=errand-net` is set
- **THEN** task-runner containers are created with `network="errand-net"` and can resolve compose service DNS names

#### Scenario: Host network in errand-desktop

- **WHEN** `TASK_RUNNER_NETWORK` is unset
- **THEN** task-runner containers are created with `network_mode="host"` (current behaviour)
