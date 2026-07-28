## ADDED Requirements

### Requirement: Claude image permitted only on allowlisted runtimes
The container runtime SHALL accept the `"claude"` container image value only when `CONTAINER_RUNTIME` is `docker` or `apple`, and SHALL reject it on every other runtime — including `kubernetes` and any runtime added later — with an error stating that the claude task-runner is supported only on local and desktop deployments.

The rule is an allowlist rather than a denylist on the literal string `kubernetes` so that a future shared runtime does not silently inherit permission to run a personal subscription on shared infrastructure.

#### Scenario: Claude image accepted on Docker
- **WHEN** container preparation requests image `"claude"` with `CONTAINER_RUNTIME=docker`
- **THEN** preparation proceeds using the claude-task-runner image

#### Scenario: Claude image accepted on Apple
- **WHEN** container preparation requests image `"claude"` with `CONTAINER_RUNTIME=apple`
- **THEN** preparation proceeds using the claude-task-runner image

#### Scenario: Claude image rejected on Kubernetes
- **WHEN** container preparation requests image `"claude"` with `CONTAINER_RUNTIME=kubernetes`
- **THEN** preparation fails with an error stating the claude task-runner is not supported on this deployment

#### Scenario: Unknown future runtime rejected
- **WHEN** container preparation requests image `"claude"` with a `CONTAINER_RUNTIME` value that is neither `docker` nor `apple`
- **THEN** preparation fails rather than defaulting to permitted

#### Scenario: Custom images unaffected
- **WHEN** container preparation requests image `"my-registry/custom:v1"` with `CONTAINER_RUNTIME=kubernetes`
- **THEN** preparation proceeds normally — only the literal `"claude"` value is restricted

### Requirement: Claude support exposed to the frontend
The backend SHALL expose a boolean `claude_supported` flag derived from the active `CONTAINER_RUNTIME` so the profile editor can show or hide the Claude image option.

#### Scenario: Docker runtime reports support
- **WHEN** the frontend queries the status endpoint with `CONTAINER_RUNTIME=docker`
- **THEN** the response includes `claude_supported: true`

#### Scenario: Apple runtime reports support
- **WHEN** the frontend queries the status endpoint with `CONTAINER_RUNTIME=apple`
- **THEN** the response includes `claude_supported: true`

#### Scenario: Kubernetes runtime reports no support
- **WHEN** the frontend queries the status endpoint with `CONTAINER_RUNTIME=kubernetes`
- **THEN** the response includes `claude_supported: false`
