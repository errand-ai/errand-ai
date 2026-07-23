## ADDED Requirements

### Requirement: Mounts field in container-create payload

The bridge API `POST /containers` payload SHALL accept an optional `mounts` array. Each entry SHALL specify `host_path` (absolute path on the macOS host) and `container_path`. The desktop app SHALL attach each mount to the container as a read-write virtiofs directory share scoped to that container only. When `mounts` is absent, container creation SHALL behave exactly as before. The bridge SHALL reject mounts whose `host_path` is outside the user-approved workspace directory configured in the desktop app.

#### Scenario: Workspace mount created

- **WHEN** the server posts a container-create payload with `mounts: [{"host_path": "/Users/x/Google Drive/My Drive/Errand", "container_path": "/shared"}]`
- **THEN** the created container has that host directory available read-write at `/shared` via virtiofs

#### Scenario: Unapproved path rejected

- **WHEN** the payload requests a host path outside the approved workspace directory
- **THEN** the bridge returns an error and no container is created

#### Scenario: Payload without mounts

- **WHEN** the payload contains no `mounts` field
- **THEN** the container is created with no shares, identical to pre-workspace behavior
