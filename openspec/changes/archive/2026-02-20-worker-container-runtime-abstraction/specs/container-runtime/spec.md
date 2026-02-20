## ADDED Requirements

### Requirement: ContainerRuntime abstract interface
The worker SHALL define a `ContainerRuntime` abstract base class with methods: `prepare(image, env, files, output_dir) -> Handle`, `run(handle) -> Iterator[str]`, `result(handle) -> tuple[int, str, str]`, and `cleanup(handle)`. The `prepare` method SHALL create a container or Job and inject input files without starting execution. The `run` method SHALL start execution and yield log lines in real-time, blocking until the container exits. The `result` method SHALL return the exit code, stdout content, and stderr content after execution completes. The `cleanup` method SHALL remove the container/Job and any temporary resources.

#### Scenario: Interface defines all lifecycle methods
- **WHEN** a class inherits from `ContainerRuntime`
- **THEN** it must implement `prepare`, `run`, `result`, and `cleanup` methods

### Requirement: Runtime selection via environment variable
The worker SHALL select the container runtime implementation based on the `CONTAINER_RUNTIME` environment variable. The value `docker` (or unset) SHALL select `DockerRuntime`. The value `kubernetes` SHALL select `KubernetesRuntime`. The runtime SHALL be instantiated once at worker startup. An unrecognised value SHALL cause the worker to exit with an error.

#### Scenario: Default runtime is Docker
- **WHEN** `CONTAINER_RUNTIME` is not set
- **THEN** the worker uses `DockerRuntime`

#### Scenario: Kubernetes runtime selected
- **WHEN** `CONTAINER_RUNTIME` is set to `kubernetes`
- **THEN** the worker uses `KubernetesRuntime`

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
