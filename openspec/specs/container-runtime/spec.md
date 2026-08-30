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

### Requirement: Orphaned task recovery uses the running event loop
The `_recover_orphaned_task` function SHALL be an async function that performs DB operations using the existing event loop. It SHALL NOT use `asyncio.run()` or create a new event loop. The `cleanup_orphaned_jobs` function SHALL be async and SHALL await `_recover_orphaned_task` directly. Since `cleanup_orphaned_jobs` is called during FastAPI lifespan startup (which runs inside the event loop), synchronous K8s API calls SHALL be wrapped in `asyncio.to_thread()` to avoid blocking the event loop.

#### Scenario: Orphaned task recovery during startup
- **WHEN** the server starts and finds orphaned K8s Jobs from a previous instance
- **THEN** `_recover_orphaned_task` successfully updates the task status in the DB using the running event loop (no "different loop" error)

#### Scenario: Orphaned task with retries remaining
- **WHEN** an orphaned task has `retry_count < MAX_RETRIES`
- **THEN** the task is moved to "scheduled" with exponential backoff and a WebSocket event is published

#### Scenario: Orphaned task with retries exhausted
- **WHEN** an orphaned task has `retry_count >= MAX_RETRIES`
- **THEN** the task is moved to "review" with an explanatory output message

<!-- Removed: Worker process health reporting — Worker merged into server; server has its own health endpoint. -->

### Requirement: Workspace mount parameter on prepare

`ContainerRuntime.prepare()` and `async_prepare()` SHALL accept an optional `mounts` parameter (list of workspace mount specifications, default `None`). A mount specification SHALL carry the container path (`/shared` in v1) and per-runtime source information: a host directory path for Docker and Apple runtimes, or NFS server address, export path, and subpath for the Kubernetes runtime. When `mounts` is `None` or empty, every runtime SHALL behave exactly as before this change.

#### Scenario: No mounts requested

- **WHEN** `prepare()` is called without mounts
- **THEN** the created container has no workspace volumes and behavior is unchanged from the pre-workspace implementation

#### Scenario: DockerRuntime attaches volume

- **WHEN** `prepare()` is called on `DockerRuntime` with a mount specifying a source and container path `/shared`
- **THEN** the container is created with a read-write volume mapping the source to `/shared`

#### Scenario: AppleContainerRuntime forwards mounts

- **WHEN** `prepare()` is called on `AppleContainerRuntime` with mounts
- **THEN** the bridge container-create payload includes a `mounts` array describing each host path and container path

### Requirement: Container runtimes return pod logs as decoded text

A runtime's `result()` SHALL return logs as decoded text with real line-break characters. It SHALL NOT return the `repr` of a bytes object, and SHALL NOT return a value in which line breaks are the two-character sequence backslash-`n`.

`KubernetesRuntime` SHALL read pod logs with `_preload_content=False` and decode the response itself, as its streaming path already does. It SHALL NOT rely on the Kubernetes client's preloaded `str` deserialisation, which returns `str(bytes)` — the bytes repr — whenever the response body is not valid JSON, as pod logs never are.

The logs a runtime returns for a completed task SHALL be byte-equivalent in form to what its streaming path yields for the same task, so that a consumer splitting on line breaks and parsing each line as JSON obtains the same events from both.

#### Scenario: Completed-task logs contain real line breaks

- **WHEN** `result()` returns logs for a task whose pod emitted multiple lines
- **THEN** the returned string contains real line-break characters
- **AND** it does not begin with `b'` or `b"`
- **AND** it contains no literal backslash-`n` sequences introduced in place of line breaks

#### Scenario: Each stored log line is independently parseable

- **WHEN** logs returned by `result()` are split on line breaks
- **THEN** a line the task-runner emitted as a JSON event parses as a JSON object exposing `type`
- **AND** it is not necessary to parse the whole log as a single value to reach it

#### Scenario: Stored and streamed logs agree

- **WHEN** the same task's logs are obtained from the streaming path and from `result()`
- **THEN** both yield the same sequence of task-runner event lines

#### Scenario: Pod logs are read without client-side deserialisation

- **WHEN** `KubernetesRuntime` reads pod logs for a completed task
- **THEN** the read passes `_preload_content=False`
- **AND** the runtime decodes the response itself rather than accepting a client-deserialised `str`

### Requirement: Existing bytes-repr logs are repaired

Task logs already stored as a bytes repr SHALL be repaired to their decoded text, so the fix applies to tasks created before it as well as after.

A stored value SHALL be treated as corrupt only when every one of the following holds: it begins with `b'` or `b"`, it ends with the matching quote, it contains no real line-break characters, and evaluating it as a Python literal yields a `bytes` object. A value failing any of these SHALL be left unchanged.

A value that cannot be decoded cleanly SHALL be left unchanged rather than partially rewritten.

#### Scenario: A corrupt log is repaired

- **WHEN** a stored log satisfies every corruption condition
- **THEN** it is replaced by the decoded text of the bytes literal it represents
- **AND** the repaired value contains real line breaks

#### Scenario: A healthy log is untouched

- **WHEN** a stored log contains real line breaks
- **THEN** it is left byte-for-byte unchanged, whatever it begins with

#### Scenario: An ambiguous value is left alone

- **WHEN** a stored log begins with `b'` but does not evaluate to a `bytes` literal — for example because it was truncated before its closing quote
- **THEN** it is left unchanged
- **AND** the repair is reported as skipped rather than reported as applied

### Requirement: Log streaming completes only when the pod terminates

A runtime's log-streaming method SHALL NOT treat the end of the pod log stream as evidence that the pod finished. When the stream ends, the runtime SHALL read the pod's phase. Only a terminal phase (`Succeeded` or `Failed`) SHALL end the stream; while the pod is still running, the runtime SHALL resume streaming and continue yielding lines.

A resumed stream SHALL request only log content produced after the last line already yielded, so that a resume neither repeats nor loses output.

Resumption SHALL be bounded by pod state rather than by attempt count alone: it continues while the pod runs and stops when the pod terminates or can no longer be read. A bounded backstop MAY additionally limit resumption to guard against a pathological loop, but SHALL NOT be the primary termination condition.

The runtime SHALL distinguish, internally and in its logs, a stream that ended because the pod terminated from one that ended while the pod was still running. The two SHALL NOT be signalled identically.

#### Scenario: Stream ends while the pod is still running

- **WHEN** the pod log stream ends and the pod's phase is neither `Succeeded` nor `Failed`
- **THEN** the runtime resumes streaming instead of completing
- **AND** it records that the stream was interrupted and is being resumed

#### Scenario: Stream ends because the pod finished

- **WHEN** the pod log stream ends and the pod has reached a terminal phase
- **THEN** the runtime completes normally

#### Scenario: A resumed stream is continuous

- **WHEN** a stream is interrupted and resumed
- **THEN** the lines yielded across the interruption contain no duplicate of a line already yielded
- **AND** no line produced by the pod between the interruption and the resume is omitted

#### Scenario: Interruption is not silent

- **WHEN** a stream ends early and is resumed
- **THEN** the event is logged, naming the pod and that the pod was still running

### Requirement: A running container is never destroyed on an unknown exit code

A runtime SHALL NOT delete a Job or otherwise destroy a container whose exit code could not be determined while that container is still running. Where the exit code is unknown, the runtime SHALL establish whether the container has terminated before any cleanup, and SHALL leave a still-running container in place.

#### Scenario: Cleanup is withheld from a running container

- **WHEN** cleanup would run for a task whose exit code is unknown
- **AND** the pod's container is still running
- **THEN** the Job is not deleted
- **AND** the condition is logged

#### Scenario: Cleanup proceeds for a terminated container

- **WHEN** the container has terminated
- **THEN** cleanup deletes the Job and its associated resources as before

#### Scenario: An abandoned pod is still reclaimed

- **WHEN** a container is left in place because it was still running
- **THEN** it remains subject to the Job's `ttlSecondsAfterFinished` and to orphaned-Job recovery, so it is not leaked indefinitely

