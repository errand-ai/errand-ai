## Purpose

Anonymous usage telemetry collection and reporting to errand-cloud.

## Requirements

### Requirement: Installation identity
The service SHALL generate and persist a unique installation identifier for telemetry purposes.

#### Scenario: First run generates UUID
- **WHEN** the telemetry reporter runs for the first time and no `telemetry_installation_id` exists in the settings table
- **THEN** the service SHALL generate a UUID4, store it in the settings table under the key `telemetry_installation_id`, and use it for all subsequent telemetry reports

#### Scenario: Subsequent runs reuse existing UUID
- **WHEN** the telemetry reporter runs and `telemetry_installation_id` already exists in the settings table
- **THEN** the service SHALL use the existing UUID

### Requirement: Deployment type detection
The service SHALL auto-detect the deployment type at startup.

#### Scenario: Kubernetes deployment
- **WHEN** the path `/var/run/secrets/kubernetes.io` exists on the filesystem
- **THEN** the deployment type SHALL be `kubernetes`

#### Scenario: Host-declared container runtime
- **WHEN** `/var/run/secrets/kubernetes.io` does not exist and the `ERRAND_CONTAINER_RUNTIME` environment variable is set
- **THEN** the deployment type SHALL be the value of `ERRAND_CONTAINER_RUNTIME` (e.g. `apple-container`, `apple-docker`, `windows-docker`, `linux-docker`)

#### Scenario: Default deployment type
- **WHEN** neither Kubernetes secrets nor `ERRAND_CONTAINER_RUNTIME` are detected
- **THEN** the deployment type SHALL be `unknown-docker`

### Requirement: Usage metrics collection
The service SHALL collect usage metrics from the database at report time, grouped by UTC hour.

#### Scenario: Completed tasks counted since last report
- **WHEN** a telemetry report is being prepared
- **THEN** the service SHALL query tasks with status `completed` or `archived` whose `updated_at` is after the last successful report time, grouped by UTC hour

#### Scenario: Pending and scheduled counts
- **WHEN** a telemetry report is being prepared
- **THEN** the service SHALL include point-in-time counts of `pending` and `scheduled` tasks

#### Scenario: No tasks completed
- **WHEN** no tasks have been completed since the last report
- **THEN** the service SHALL include the current hour with `tasks_completed: 0` and the current pending/scheduled counts

### Requirement: System information collection
The service SHALL collect system information for inclusion in telemetry reports, extended with resource metrics.

#### Scenario: Collect system info
- **WHEN** the telemetry reporter initializes
- **THEN** the service SHALL collect: OS name (e.g., `linux`, `darwin`), CPU architecture (e.g., `arm64`, `x86_64`), errand version (from the `VERSION` file), worker count, CPU count, total memory, and container resource limits
- **AND** resource metrics (CPU count, total memory, container limits) SHALL be cached for the process lifetime; other static values (OS, arch, version) MAY be recomputed each cycle as they are trivial to collect

### Requirement: Active integrations collection
The service SHALL collect the list of active integrations for each telemetry report.

#### Scenario: Collect active integrations
- **WHEN** a telemetry report is being prepared
- **THEN** the service SHALL query the current set of configured/enabled integrations and include their names as a string array in the report

### Requirement: Periodic telemetry reporting
The errand-server process SHALL POST telemetry reports to errand-cloud at a regular interval.

#### Scenario: Periodic report with jitter
- **WHEN** 6 hours have elapsed since the last report
- **THEN** the service SHALL POST a JSON payload to `https://service.errand.cloud/api/telemetry/report` containing:
  - Top-level: `installation_id`, `version`, `deployment_type`, `os`, `arch`, `worker_count`, `integrations`, `hourly_buckets` (existing, preserved for backward compatibility)
  - `system`: `cpu_count`, `memory_total_mb`, `memory_available_mb`, `container_memory_limit_mb`, `container_cpu_limit`, `disk_available_mb`
  - `infrastructure`: `postgres_version`, `valkey_version`, `valkey_connected`
  - `llm`: `providers` (array of {type, category}), `models` (object keyed by setting name with {category, model})
  - `health`: `uptime_seconds`, `task_failure_count`
- **AND** a random jitter of up to 15 minutes SHALL be added to the interval to avoid synchronized reporting across installations

### Requirement: Multi-replica safety
The telemetry reporter SHALL use a Valkey distributed lock to ensure only one server replica reports per cycle.

#### Scenario: Lock acquired
- **WHEN** the telemetry reporter cycle starts and the `errand:telemetry-lock` Valkey key can be acquired
- **THEN** the service SHALL proceed with the report

#### Scenario: Lock held by another replica
- **WHEN** the `errand:telemetry-lock` is held by another server replica
- **THEN** the service SHALL skip the cycle and try again on the next interval

### Requirement: Telemetry opt-out setting
The service SHALL provide a setting to disable telemetry.

#### Scenario: Setting in registry
- **WHEN** the settings registry is loaded
- **THEN** it SHALL contain `telemetry_enabled` with env var `TELEMETRY_ENABLED`, default `true`, and `sensitive: false`

#### Scenario: Env var override
- **WHEN** the `TELEMETRY_ENABLED` environment variable is set to `false`
- **THEN** the setting SHALL be readonly in the UI and telemetry SHALL be disabled
