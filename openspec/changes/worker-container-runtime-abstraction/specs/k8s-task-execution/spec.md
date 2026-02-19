## ADDED Requirements

### Requirement: Task-runner Jobs run in the worker's namespace
The KubernetesRuntime SHALL create Jobs in the same namespace as the worker pod. The namespace SHALL be read from the service account token mount at `/var/run/secrets/kubernetes.io/serviceaccount/namespace`, or from the `TASK_RUNNER_NAMESPACE` environment variable as an override.

#### Scenario: Namespace from service account
- **WHEN** the worker runs in a K8s pod in namespace `content-manager`
- **THEN** task-runner Jobs are created in the `content-manager` namespace

#### Scenario: Namespace override
- **WHEN** `TASK_RUNNER_NAMESPACE` is set to `task-runners`
- **THEN** task-runner Jobs are created in the `task-runners` namespace

### Requirement: Task-runner Jobs are labelled for identification
Each task-runner Job SHALL have labels `app.kubernetes.io/managed-by: content-manager-worker`, `app.kubernetes.io/component: task-runner`, and `content-manager/task-id: <task-uuid>`. These labels enable the worker to find orphaned Jobs on startup and enable NetworkPolicy targeting.

#### Scenario: Job has identifying labels
- **WHEN** a task-runner Job is created for task `abc-123`
- **THEN** the Job has label `content-manager/task-id: abc-123` and `app.kubernetes.io/component: task-runner`

### Requirement: Playwright accessible from task-runner Jobs
When Playwright is configured, the worker SHALL discover its own pod IP (via the Kubernetes Downward API or `POD_IP` env var) and pass `PLAYWRIGHT_URL=http://<pod-ip>:<playwright-port>/mcp` as an environment variable to the task-runner Job. The task-runner SHALL use this URL for Playwright MCP connectivity instead of `localhost`.

#### Scenario: Task-runner connects to worker's Playwright sidecar
- **WHEN** the worker pod has IP `10.42.0.15` and Playwright runs on port `8931`
- **THEN** the task-runner Job receives `PLAYWRIGHT_URL=http://10.42.0.15:8931/mcp`

#### Scenario: Playwright not configured
- **WHEN** `PLAYWRIGHT_MCP_IMAGE` is not set
- **THEN** no `PLAYWRIGHT_URL` is passed to the task-runner Job

### Requirement: Worker cleans up orphaned Jobs on startup
When using KubernetesRuntime, the worker SHALL check for orphaned task-runner Jobs (labelled with `app.kubernetes.io/managed-by: content-manager-worker`) on startup and delete them. This handles the case where the worker crashed before cleaning up a previous Job.

#### Scenario: Orphaned Jobs cleaned up on startup
- **WHEN** the worker starts and finds a completed Job with label `app.kubernetes.io/managed-by: content-manager-worker`
- **THEN** the worker deletes the orphaned Job and its associated ConfigMap

### Requirement: Worker ServiceAccount with RBAC
The worker SHALL use a Kubernetes ServiceAccount with a Role binding that grants: `create`, `get`, `list`, `watch`, `delete` on `jobs.batch`; `create`, `get`, `delete` on `configmaps`; `get`, `list` on `pods`; and `get` on `pods/log`. All permissions SHALL be scoped to the worker's namespace.

#### Scenario: Worker can create and delete Jobs
- **WHEN** the worker's ServiceAccount is bound to the required Role
- **THEN** the worker can create, watch, and delete Jobs in its namespace

#### Scenario: Worker can stream pod logs
- **WHEN** a task-runner pod is running
- **THEN** the worker can read its logs via `pods/log` API
