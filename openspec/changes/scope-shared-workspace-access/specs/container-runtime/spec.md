## MODIFIED Requirements

### Requirement: Workspace mount parameter on prepare

`ContainerRuntime.prepare()` and `async_prepare()` SHALL accept an optional `mounts` parameter (list of workspace mount specifications, default `None`). A mount specification SHALL carry the container path (`/shared` in v1), a read-only flag, and per-runtime source information: a host directory path for Docker and Apple runtimes, or NFS server address, export path, and subpath for the Kubernetes runtime. When `mounts` is `None` or empty, every runtime SHALL behave exactly as before this change.

#### Scenario: No mounts requested

- **WHEN** `prepare()` is called without mounts
- **THEN** the created container has no workspace volumes and behavior is unchanged from the pre-workspace implementation

#### Scenario: DockerRuntime attaches volume

- **WHEN** `prepare()` is called on `DockerRuntime` with a mount specifying a source and container path `/shared`, and the mount is not marked read-only
- **THEN** the container is created with a read-write volume mapping the source to `/shared`

#### Scenario: AppleContainerRuntime forwards mounts

- **WHEN** `prepare()` is called on `AppleContainerRuntime` with mounts
- **THEN** the bridge container-create payload includes a `mounts` array describing each host path, container path, and read-only flag

## ADDED Requirements

### Requirement: Workspace mounts are attached read-only when the profile requires it

When a workspace mount specification is marked read-only, the runtime SHALL attach it such that the container cannot write to it, using the runtime's own mechanism rather than any check inside the task-runner.

Enforcement SHALL be at the mount, because a check performed by the task-runner is not a control: `execute_command` runs arbitrary shell in the same container and would bypass any restriction applied to the file tools alone.

#### Scenario: Docker attaches a read-only bind mount

- **WHEN** `prepare()` is called on `DockerRuntime` with a mount marked read-only
- **THEN** the container is created with the source mapped to `/shared` read-only

#### Scenario: Kubernetes sets readOnly on the volume mount

- **WHEN** `prepare()` is called on `KubernetesRuntime` with a mount marked read-only
- **THEN** the Job's container volumeMount for that path has `readOnly: true`

#### Scenario: A write to a read-only workspace fails

- **WHEN** a task running under a read-only workspace mount attempts to modify a file under `/shared`, by any means including `write_file` and `execute_command`
- **THEN** the write does not take effect

### Requirement: A runtime that cannot enforce read-only refuses the mount

Where a runtime cannot attach a mount read-only, it SHALL refuse to attach the mount at all rather than attach it read-write. Downgrading a read-only request to read-write would silently grant a profile write access to the user's workspace that it explicitly did not ask for.

This mirrors the existing refusal when a Docker named volume cannot be scoped to a requested subpath.

#### Scenario: Unsupported read-only mount is refused

- **WHEN** a read-only mount is requested from a runtime that cannot enforce it
- **THEN** the mount is not attached
- **AND** the task fails or starts without the workspace rather than receiving a writable mount

#### Scenario: The refusal names the cause

- **WHEN** a mount is refused because read-only cannot be enforced
- **THEN** the recorded error identifies the runtime and states that read-only enforcement is unavailable, so it is not mistaken for a mount or network failure
