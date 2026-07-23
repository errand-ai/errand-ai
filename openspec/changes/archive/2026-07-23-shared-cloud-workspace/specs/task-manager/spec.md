## ADDED Requirements

### Requirement: TaskManager resolves workspace mounts from the profile

When starting a task whose profile has `shared_workspace_enabled=true` and the deployment has a workspace configured, the TaskManager SHALL build a workspace mount specification (container path `/shared`, source resolved per runtime: gateway NFS ClusterIP/export/subpath for Kubernetes and compose, local sync-folder path for desktop runtimes) and pass it to `ContainerRuntime.prepare()`. The profile's `shared_workspace_subpath` SHALL be applied to the mount source. If the profile requests the workspace but the deployment has none configured, the TaskManager SHALL start the task without the mount and emit a structured warning event to the task transcript.

#### Scenario: Mount passed to runtime

- **WHEN** a workspace-enabled task starts on a deployment with a configured gateway
- **THEN** `prepare()` receives a mount for `/shared` scoped to the profile's subpath

#### Scenario: Workspace requested but unconfigured

- **WHEN** a workspace-enabled task starts on a deployment without workspace configuration
- **THEN** the task runs without the mount and the transcript contains a warning event noting the missing workspace

#### Scenario: Default profiles unaffected

- **WHEN** a task runs under a profile with `shared_workspace_enabled=false`
- **THEN** `prepare()` is called without mounts and behavior matches pre-workspace semantics
