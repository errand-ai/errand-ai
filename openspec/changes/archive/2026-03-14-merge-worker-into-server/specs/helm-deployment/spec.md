## MODIFIED Requirements

### Requirement: Helm chart deploys all application components

The Helm chart SHALL define Kubernetes resources for: server Deployment and Service, database migration Job (pre-upgrade hook), Ingress, Playwright Deployment and Service, and server ServiceAccount with RBAC. The Helm chart SHALL NOT include a separate worker Deployment. The server Deployment SHALL handle both API serving and task processing (via the integrated TaskManager).

The server Deployment SHALL include environment variables previously only on the worker: `CONTAINER_RUNTIME=kubernetes`, `TASK_RUNNER_IMAGE`, `ERRAND_MCP_URL` (pointing to itself), `PLAYWRIGHT_MCP_URL` (pointing to Playwright Service), and all credential/integration variables. The `POD_IP` downward API field SHALL be removed (no longer needed for Playwright routing).

The server's ServiceAccount SHALL have RBAC rules for: jobs (create, get, list, delete), configmaps (create, get, delete), pods (get, list), pods/log (get), and pods/exec (create). These are the same permissions previously on the worker's ServiceAccount.

The server and worker deployments SHALL render LLM provider environment variables from the `llmProviders` values array. For each entry at index `i`, the templates SHALL render `LLM_PROVIDER_{i}_NAME`, `LLM_PROVIDER_{i}_BASE_URL`, and `LLM_PROVIDER_{i}_API_KEY`. If the entry has `existingSecret` set, `LLM_PROVIDER_{i}_API_KEY` SHALL use `valueFrom.secretKeyRef` referencing that secret and `secretKeyApiKey` key; otherwise it SHALL use the `apiKey` value directly.

#### Scenario: Full deployment without separate worker

- **WHEN** `helm install` is run
- **THEN** server Deployment, Playwright Deployment, and ServiceAccount with RBAC are created; no worker Deployment exists

#### Scenario: Server has task processing env vars

- **WHEN** the server Deployment is rendered
- **THEN** it includes `CONTAINER_RUNTIME`, `TASK_RUNNER_IMAGE`, `ERRAND_MCP_URL`, and `PLAYWRIGHT_MCP_URL`

#### Scenario: Server ServiceAccount has RBAC for Jobs

- **WHEN** the server Deployment runs
- **THEN** it can create, get, list, and delete K8s Jobs and ConfigMaps in its namespace

## REMOVED Requirements

### Requirement: Worker Deployment

**Reason**: Worker functionality merged into the server's TaskManager.
**Migration**: Remove `worker-deployment.yaml`, worker ServiceAccount, and worker RBAC templates from the Helm chart. All task processing is handled by the server.

## ADDED Requirements

### Requirement: Playwright Deployment and Service

The Helm chart SHALL include a Playwright Deployment and Service when `playwright.enabled` is `true`. The Deployment SHALL use the `playwright.image` values with args `["--isolated", "--port", "<port>", "--host", "0.0.0.0", "--allowed-hosts", "*"]`. The Service SHALL expose the Playwright port for internal cluster access. The server Deployment SHALL set `PLAYWRIGHT_MCP_URL` to the Playwright Service's internal DNS URL.

#### Scenario: Playwright enabled

- **WHEN** `playwright.enabled` is `true`
- **THEN** a Playwright Deployment and Service are created, and the server's `PLAYWRIGHT_MCP_URL` points to the Service

#### Scenario: Playwright disabled

- **WHEN** `playwright.enabled` is `false`
- **THEN** no Playwright Deployment or Service is created, and `PLAYWRIGHT_MCP_URL` is not set

### Requirement: max_concurrent_tasks in server env vars

The Helm chart SHALL pass `MAX_CONCURRENT_TASKS` to the server Deployment from `values.server.maxConcurrentTasks` if set.

#### Scenario: Custom concurrency limit

- **WHEN** `server.maxConcurrentTasks` is set to 5
- **THEN** the server Deployment includes `MAX_CONCURRENT_TASKS=5`
