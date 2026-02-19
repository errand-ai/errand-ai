## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

The worker SHALL execute each task by delegating container operations to the configured `ContainerRuntime` implementation. The worker SHALL: (1) retrieve settings from the database (unchanged), (2) if Playwright is configured, start the Playwright sidecar via the runtime-appropriate mechanism (Docker: create container in DinD with `network_mode="host"`; K8s: Playwright is a pre-deployed sidecar on the worker pod — the worker health-checks it but does not start it), (3) build the environment variables and input files (unchanged), (4) call `runtime.prepare(image, env, files, output_dir)` to create the container/Job with injected files, (5) call `runtime.run(handle)` and publish each yielded log line to the Valkey channel `task_logs:{task_id}`, (6) call `runtime.result(handle)` to get `(exit_code, stdout, stderr)`, (7) call `runtime.cleanup(handle)`, (8) parse the structured output and update the task in the database (unchanged).

The Playwright container cleanup in Docker mode SHALL occur in a `finally` block (unchanged). In K8s mode, Playwright is managed by the pod spec and does not need explicit cleanup by the worker.

The worker SHALL pre-pull required Docker images on startup only when using `DockerRuntime`. When using `KubernetesRuntime`, the K8s node's container runtime handles image pulling.

All other behaviour (settings retrieval, system prompt construction, MCP configuration injection, Perplexity injection, Hindsight recall, skills injection, SSH credential injection, env var substitution, log publishing to Valkey, output parsing, retry logic, repeating task rescheduling, WebSocket event publishing) SHALL remain unchanged.

#### Scenario: Docker runtime processes task (unchanged behaviour)
- **WHEN** `CONTAINER_RUNTIME` is `docker` (or unset) and the worker processes a task
- **THEN** the worker creates a Docker container in DinD, streams stderr to Valkey, captures stdout for parsing, and cleans up the container — identical to current behaviour

#### Scenario: Kubernetes runtime processes task
- **WHEN** `CONTAINER_RUNTIME` is `kubernetes` and the worker processes a task
- **THEN** the worker creates a K8s Job with a ConfigMap for input files, streams pod logs to Valkey, reads structured output from `/output/result.json`, and cleans up the Job and ConfigMap

#### Scenario: Playwright health check uses pod IP in K8s mode
- **WHEN** the worker uses `KubernetesRuntime` and Playwright is configured as a sidecar
- **THEN** the worker health-checks Playwright at `http://localhost:<port>/mcp` (same pod) and passes `http://<pod-ip>:<port>/mcp` to the task-runner Job

#### Scenario: Images pre-pulled only in Docker mode
- **WHEN** the worker starts with `CONTAINER_RUNTIME=docker`
- **THEN** it pre-pulls the task-runner and Playwright images via Docker SDK

#### Scenario: No image pre-pull in K8s mode
- **WHEN** the worker starts with `CONTAINER_RUNTIME=kubernetes`
- **THEN** no image pre-pull occurs (K8s handles image pulling)
