## ADDED Requirements

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
