## Purpose

Pluggable container runtime abstraction (Docker, Kubernetes, Apple) with runtime selection via environment variable.

## Requirements

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

### Requirement: Runtime selection via environment variable
The worker SHALL select the container runtime implementation based on the `CONTAINER_RUNTIME` environment variable. The value `docker` (or unset) SHALL select `DockerRuntime`. The value `kubernetes` SHALL select `KubernetesRuntime`. The value `apple` SHALL select `AppleContainerRuntime`. The runtime SHALL be instantiated once at worker startup. An unrecognised value SHALL cause the worker to exit with an error.

#### Scenario: Default runtime is Docker
- **WHEN** `CONTAINER_RUNTIME` is not set
- **THEN** the worker uses `DockerRuntime`

#### Scenario: Kubernetes runtime selected
- **WHEN** `CONTAINER_RUNTIME` is set to `kubernetes`
- **THEN** the worker uses `KubernetesRuntime`

#### Scenario: Apple runtime selected
- **WHEN** `CONTAINER_RUNTIME` is set to `apple`
- **THEN** the worker uses `AppleContainerRuntime`

#### Scenario: Invalid runtime value
- **WHEN** `CONTAINER_RUNTIME` is set to `invalid`
- **THEN** the worker logs an error and exits

### Requirement: DockerRuntime wraps existing Docker SDK logic
The `DockerRuntime` SHALL implement the `ContainerRuntime` interface using the Docker SDK (current `process_task_in_container` logic). The `prepare` method SHALL pull the image if not found locally, create the container with `network_mode="host"`, and copy input files via `put_archive()`. The `run` method SHALL start the container and yield stderr lines from `container.logs(stream=True, follow=True, stderr=True, stdout=False)`. The `result` method SHALL call `container.wait()` and capture stdout and stderr via `container.logs()`. The `cleanup` method SHALL remove the container.

#### Scenario: Docker container created and started
- **WHEN** `DockerRuntime.prepare()` is called with an image and files
- **THEN** a Docker container is created with the specified image, env vars, and files injected via put_archive

#### Scenario: Docker logs streamed in real-time
- **WHEN** `DockerRuntime.run()` is called
- **THEN** stderr lines are yielded in real-time as the container executes

#### Scenario: Docker stdout captured separately
- **WHEN** `DockerRuntime.result()` is called after the container exits
- **THEN** stdout and stderr are captured independently via `container.logs()`

### Requirement: DockerRuntime supports named network for task-runner containers

When the `TASK_RUNNER_NETWORK` environment variable is set, `DockerRuntime.prepare()` SHALL attach task-runner containers to the specified Docker network (using the `network` parameter) instead of using `network_mode="host"`. When `TASK_RUNNER_NETWORK` is unset, `DockerRuntime` SHALL fall back to `network_mode="host"` for backward compatibility with errand-desktop.

#### Scenario: Named network in docker-compose

- **WHEN** `TASK_RUNNER_NETWORK=errand-net` is set
- **THEN** task-runner containers are created with `network="errand-net"` and can resolve compose service DNS names

#### Scenario: Host network in errand-desktop

- **WHEN** `TASK_RUNNER_NETWORK` is unset
- **THEN** task-runner containers are created with `network_mode="host"` (current behaviour)

### Requirement: KubernetesRuntime creates Jobs and ConfigMaps
The `KubernetesRuntime` SHALL implement the `ContainerRuntime` interface using the Kubernetes Python client. The `prepare` method SHALL create a ConfigMap containing input files (`prompt.txt`, `system_prompt.txt`, `mcp.json`) and a Job with the ConfigMap mounted at `/workspace` and an `emptyDir` volume mounted at `/output`. The `run` method SHALL wait for the Job's pod to start, then stream pod logs via `read_namespaced_pod_log(follow=True)`, yielding lines in real-time, and blocking until the pod exits. The `result` method SHALL read `/output/result.json` from the completed pod (via exec or cp), read the full pod logs as stderr, and return the exit code from the pod's termination status. The `cleanup` method SHALL delete the Job (with propagation) and the ConfigMap.

#### Scenario: K8s Job created with ConfigMap
- **WHEN** `KubernetesRuntime.prepare()` is called with input files
- **THEN** a ConfigMap is created with the file contents and a Job is created with the ConfigMap mounted at `/workspace`

#### Scenario: K8s pod logs streamed in real-time
- **WHEN** `KubernetesRuntime.run()` is called
- **THEN** pod log lines are yielded in real-time as the task-runner executes

#### Scenario: K8s output read from file
- **WHEN** `KubernetesRuntime.result()` is called after the Job completes
- **THEN** the structured output is read from `/output/result.json` in the completed pod

#### Scenario: K8s cleanup removes Job and ConfigMap
- **WHEN** `KubernetesRuntime.cleanup()` is called
- **THEN** the Job and its associated ConfigMap are deleted from the namespace

#### Scenario: Job has TTL for orphan protection
- **WHEN** a K8s Job is created
- **THEN** the Job spec includes `ttlSecondsAfterFinished` so completed Jobs are automatically cleaned up if the worker crashes before cleanup

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

### Requirement: AppleContainerRuntime implementation
The worker SHALL include an `AppleContainerRuntime` implementation of the `ContainerRuntime` interface. This runtime SHALL communicate with the macOS app's bridge API to create, monitor, and clean up task-runner containers. The runtime SHALL be selected when `CONTAINER_RUNTIME` is set to `apple`.

#### Scenario: Apple runtime creates container via bridge API
- **WHEN** `AppleContainerRuntime.prepare()` is called with an image, env vars, and files
- **THEN** the runtime sends `POST /containers` to the bridge API with the container specification

#### Scenario: Apple runtime streams logs via bridge API
- **WHEN** `AppleContainerRuntime.run()` is called
- **THEN** the runtime opens an SSE connection to `GET /containers/{id}/logs` and yields log lines

#### Scenario: Apple runtime reads output via bridge API
- **WHEN** `AppleContainerRuntime.result()` is called after the container exits
- **THEN** the runtime reads the exit code from `GET /containers/{id}/status` and the structured output from `GET /containers/{id}/output`

#### Scenario: Apple runtime cleans up via bridge API
- **WHEN** `AppleContainerRuntime.cleanup()` is called
- **THEN** the runtime sends `DELETE /containers/{id}` to remove the container

<!-- Removed: Worker process health reporting — Worker merged into server; server has its own health endpoint. -->
