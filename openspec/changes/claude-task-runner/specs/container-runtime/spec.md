## ADDED Requirements

### Requirement: Claude image validation on K8s runtime
When `CONTAINER_RUNTIME` is set to `kubernetes`, the container runtime SHALL reject container image values of `"claude"` during container preparation. The rejection SHALL raise a clear error indicating that claude-task-runner is not supported on Kubernetes deployments.

#### Scenario: Claude image rejected on K8s
- **WHEN** TaskManager attempts to prepare a container with image `"claude"` and `CONTAINER_RUNTIME=kubernetes`
- **THEN** the preparation fails with an error message: "Claude task-runner is not supported on Kubernetes deployments"

#### Scenario: Claude image accepted on Docker
- **WHEN** TaskManager attempts to prepare a container with image `"claude"` and `CONTAINER_RUNTIME=docker`
- **THEN** the preparation proceeds normally using the claude-task-runner image

#### Scenario: Claude image accepted on Apple
- **WHEN** TaskManager attempts to prepare a container with image `"claude"` and `CONTAINER_RUNTIME=apple`
- **THEN** the preparation proceeds normally using the claude-task-runner image

#### Scenario: Custom images allowed on K8s
- **WHEN** TaskManager attempts to prepare a container with image `"my-registry/custom:v1"` and `CONTAINER_RUNTIME=kubernetes`
- **THEN** the preparation proceeds normally (only the literal `"claude"` value is blocked)

### Requirement: Deployment mode exposed to frontend
The backend API SHALL expose the current `CONTAINER_RUNTIME` value (or a boolean `claude_supported` flag) via the settings or status endpoint so the frontend can conditionally show/hide the Claude image option in Task Profile forms.

#### Scenario: Docker runtime reports claude support
- **WHEN** the frontend queries the settings/status endpoint and `CONTAINER_RUNTIME=docker`
- **THEN** the response includes `claude_supported: true`

#### Scenario: K8s runtime reports no claude support
- **WHEN** the frontend queries the settings/status endpoint and `CONTAINER_RUNTIME=kubernetes`
- **THEN** the response includes `claude_supported: false`
