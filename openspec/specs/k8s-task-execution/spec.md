## Purpose

Kubernetes-specific task runner execution — Job creation, labelling, namespace resolution, input injection via ConfigMap, and output retrieval.
## Requirements
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
When using KubernetesRuntime, the worker SHALL check for orphaned task-runner Jobs (labelled with `app.kubernetes.io/managed-by: content-manager-worker`) on startup and delete them. For each orphaned Job found, the worker SHALL:

1. Read the `content-manager/task-id` label from the Job metadata
2. Query the `tasks` table for the corresponding task
3. If the task exists and has `status = "running"`:
   - Move the task to `status = "scheduled"` with exponential backoff `execute_at` and increment `retry_count` (using the same retry formula as `_schedule_retry`)
   - If `retry_count >= 5`, move to `status = "review"` instead with output indicating the task was recovered during worker startup
   - Publish a `task_updated` WebSocket event
4. Delete the orphaned Job and its associated ConfigMap and Secrets

This replaces the previous behaviour of deleting all orphaned Jobs indiscriminately without updating task status.

#### Scenario: Orphaned Job with running task recovered on startup

- **WHEN** the worker starts and finds an orphaned Job labelled with task ID `abc-123`, and that task has `status="running"` in the database
- **THEN** the worker moves the task to `status="scheduled"` with backoff, deletes the Job/ConfigMap, and publishes a `task_updated` event

#### Scenario: Orphaned Job with non-running task cleaned up silently

- **WHEN** the worker starts and finds an orphaned Job labelled with task ID `abc-123`, and that task has `status="completed"` in the database
- **THEN** the worker deletes the Job/ConfigMap without modifying the task

#### Scenario: Orphaned Job with missing task cleaned up silently

- **WHEN** the worker starts and finds an orphaned Job with a task ID that does not exist in the database
- **THEN** the worker deletes the Job/ConfigMap and logs a warning

#### Scenario: Orphaned Job task with exhausted retries moved to review

- **WHEN** the worker starts and finds an orphaned Job for a task with `status="running"` and `retry_count >= 5`
- **THEN** the worker moves the task to `status="review"` with output indicating startup recovery

### Requirement: Worker ServiceAccount with RBAC
The worker SHALL use a Kubernetes ServiceAccount with a Role binding that grants: `create`, `get`, `list`, `watch`, `delete` on `jobs.batch`; `create`, `get`, `list`, `delete` on `configmaps`; `get`, `list` on `pods`; `get` on `pods/log`; and `create` on `pods/exec`. The `pods/exec` permission is required to read `/output/result.json` from completed task-runner pods. All permissions SHALL be scoped to the worker's namespace.

#### Scenario: Worker can create and delete Jobs
- **WHEN** the worker's ServiceAccount is bound to the required Role
- **THEN** the worker can create, watch, and delete Jobs in its namespace

#### Scenario: Worker can stream pod logs
- **WHEN** a task-runner pod is running
- **THEN** the worker can read its logs via `pods/log` API

#### Scenario: Worker can exec into pods to read output
- **WHEN** a task-runner pod has completed
- **THEN** the worker can exec into the pod via `pods/exec` to read `/output/result.json`

### Requirement: Task Jobs mount the workspace over native NFS

When a task's mount specification includes a shared workspace, `KubernetesRuntime` SHALL mount the gateway over NFS targeting the gateway's static ClusterIP (not a DNS name, since kubelet performs the mount from the node network where cluster DNS is unavailable), mounted read-write at the container path. Because pod-inline `nfs:` volumes cannot carry mount options (spike finding F7), the required NFSv3 options — including `nolock` (no NLM support in the gateway), `soft` with conservative timeouts (so a dead gateway produces I/O errors in the task rather than an unkillable hung pod), explicit `port`/`mountport` (rclone does not register with rpcbind), and **`proto=tcp`/`mountproto=tcp`** (rclone serve nfs is TCP-only, yet some clients — e.g. the CentOS 7 kubelet — default NFSv3 to UDP and the mount then times out; finding F8) — SHALL be expressed on a **PersistentVolume** (static, CSI-free) whose PVC the Job binds, or via a StorageClass `mountOptions`. No CSI driver SHALL be required.

Conservative timeouts are required because the spike observed that aggressive `soft` timeouts (`timeo=30,retrans=2`) cause the *first* cold directory access to fail with an I/O error while rclone populates the VFS from the cloud; the mount options SHALL allow enough time for a cold cloud listing to complete.

#### Scenario: Mount options applied via PersistentVolume

- **WHEN** a workspace mount is added to a task Job
- **THEN** the `vers=3,nolock,soft` (and timeout) options are carried on a PersistentVolume / StorageClass, not an inline pod `nfs:` volume, so they actually take effect

### Requirement: Nodes require an NFS client for workspace mounts

Task Jobs mount the gateway via the kubelet, which shells out to the host `mount.nfs` helper. Therefore every node that can schedule task Jobs SHALL have an NFS client (`nfs-utils` or equivalent) installed; the `nfs` kernel module alone is insufficient (spike finding F2). This SHALL be documented as a cluster prerequisite for enabling the workspace.

#### Scenario: Node without NFS client

- **WHEN** a workspace-enabled task Job is scheduled to a node lacking `mount.nfs`
- **THEN** the mount fails and the failure is surfaced (task error / event), rather than the feature silently misbehaving — and the prerequisite is documented so operators can remediate

#### Scenario: Workspace-enabled task Job

- **WHEN** a task with a workspace mount runs on Kubernetes
- **THEN** the Job pod contains an `nfs` volume pointing at the gateway ClusterIP with the profile's subpath, mounted at `/shared`

#### Scenario: Gateway down mid-task

- **WHEN** the gateway becomes unreachable while a task pod holds the mount
- **THEN** file operations on `/shared` fail with I/O errors after the soft-mount timeout and the pod remains schedulable/terminable

#### Scenario: Non-workspace task unaffected

- **WHEN** a task without workspace enablement runs on Kubernetes
- **THEN** the Job spec contains no NFS volume and is identical to pre-workspace behavior

