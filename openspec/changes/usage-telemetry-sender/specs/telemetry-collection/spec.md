## ADDED Requirements

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

#### Scenario: macOS desktop deployment
- **WHEN** `/var/run/secrets/kubernetes.io` does not exist and the `APPLE_CONTAINER_RUNTIME` environment variable is set
- **THEN** the deployment type SHALL be `macos-desktop`

#### Scenario: Default deployment type
- **WHEN** neither Kubernetes secrets nor `APPLE_CONTAINER_RUNTIME` are detected
- **THEN** the deployment type SHALL be `docker-other`

### Requirement: Hourly bucket accumulation
The service SHALL accumulate usage metrics in hourly buckets aligned to UTC hour boundaries.

#### Scenario: Task completed increments counter
- **WHEN** a task completes (successfully or with error)
- **THEN** the service SHALL increment `tasks_completed` in the current UTC hourly bucket

#### Scenario: Pending queue high-water mark
- **WHEN** a task is enqueued or dequeued
- **THEN** the service SHALL update `max_pending` in the current UTC hourly bucket to the maximum of the current value and the current pending queue size

#### Scenario: Scheduled tasks snapshot
- **WHEN** a telemetry report is being prepared
- **THEN** the service SHALL query the count of tasks with status `scheduled` and set `tasks_scheduled` in each unsent hourly bucket to this value at the time of report generation

#### Scenario: Hour boundary rollover
- **WHEN** the current UTC hour changes
- **THEN** the service SHALL create a new hourly bucket for the new hour with all counters initialized to zero

### Requirement: System information collection
The service SHALL collect static system information at startup for inclusion in telemetry reports.

#### Scenario: Collect system info
- **WHEN** the telemetry reporter initializes
- **THEN** the service SHALL collect: OS name (e.g., `linux`, `darwin`), CPU architecture (e.g., `arm64`, `x86_64`), errand version (from the `VERSION` file), and worker count (number of concurrent workers configured)

### Requirement: Active integrations collection
The service SHALL collect the list of active integrations for each telemetry report.

#### Scenario: Collect active integrations
- **WHEN** a telemetry report is being prepared
- **THEN** the service SHALL query the current set of configured/enabled integrations and include their names as a string array in the report

### Requirement: Periodic telemetry reporting
The service SHALL POST telemetry reports to the errand-cloud service at a regular interval.

#### Scenario: Successful report
- **WHEN** 6 hours have elapsed since the last report (or since startup if no report has been sent)
- **THEN** the service SHALL POST a JSON payload to `https://cloud.errand.ai/api/telemetry/report` containing: `installation_id`, `version`, `deployment_type`, `os`, `arch`, `worker_count`, `integrations`, and all accumulated `hourly_buckets` since the last successful report
- **AND** upon receiving HTTP 200, the service SHALL clear the successfully sent hourly buckets

#### Scenario: Failed report (network error or non-2xx)
- **WHEN** the POST to errand-cloud fails
- **THEN** the service SHALL log a warning and retain the hourly buckets for the next reporting cycle

#### Scenario: Telemetry disabled
- **WHEN** the `telemetry_enabled` setting is `false`
- **THEN** the service SHALL NOT send telemetry reports and SHALL NOT accumulate hourly buckets

### Requirement: Bucket persistence across restarts
The service SHALL persist unsent hourly buckets to the database to survive process restarts.

#### Scenario: Persist on shutdown
- **WHEN** the worker process is shutting down and there are unsent hourly buckets
- **THEN** the service SHALL write the pending buckets to the database

#### Scenario: Restore on startup
- **WHEN** the worker process starts and there are persisted unsent buckets in the database
- **THEN** the service SHALL load them into memory and include them in the next telemetry report
