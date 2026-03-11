## MODIFIED Requirements

### Requirement: System information collection
The service SHALL collect system information for inclusion in telemetry reports, extended with resource metrics.

#### Scenario: Collect system info
- **WHEN** the telemetry reporter initializes
- **THEN** the service SHALL collect: OS name (e.g., `linux`, `darwin`), CPU architecture (e.g., `arm64`, `x86_64`), errand version (from the `VERSION` file), worker count, CPU count, total memory, and container resource limits
- **AND** resource metrics (CPU count, total memory, container limits) SHALL be cached for the process lifetime; other static values (OS, arch, version) MAY be recomputed each cycle as they are trivial to collect

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
