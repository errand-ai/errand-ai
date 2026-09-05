## ADDED Requirements

### Requirement: Task containers can resolve the host gateway

When a host gateway address is configured, the Docker runtime SHALL create task containers with a host entry mapping that name to the container host, so that a task can reach services running on the host machine. When no host gateway address is configured, container creation SHALL be unchanged.

#### Scenario: Host entry added when configured

- **WHEN** a host gateway address is configured and a task container is created on a named network
- **THEN** the container is created with a host entry resolving that name to the container host

#### Scenario: Unchanged when not configured

- **WHEN** no host gateway address is configured
- **THEN** the task container is created exactly as before, with no additional host entries

#### Scenario: Kubernetes runtime unaffected

- **WHEN** the Kubernetes runtime creates a task pod
- **THEN** no host gateway entry is added, because no host is addressable

### Requirement: Host-networked task containers cannot serve detected providers

A provider discovered by local detection SHALL be usable only when task containers run on a named network. When a detected provider is selected and task containers would run with host networking, the task SHALL fail with an explicit error naming the required configuration, rather than running against an address that resolves differently inside the container.

#### Scenario: Detected provider refused under host networking

- **WHEN** a task would run with host networking and its resolved provider was created by local detection
- **THEN** the task fails before starting
- **AND** the error states that a named task-runner network is required for locally detected providers

#### Scenario: Detected provider accepted on a named network

- **WHEN** task containers run on a named network and the resolved provider was created by local detection
- **THEN** the task starts normally

#### Scenario: Non-detected providers unaffected

- **WHEN** a task runs with host networking against a provider that was not created by local detection
- **THEN** the task starts normally
