## ADDED Requirements

### Requirement: Process uptime tracking
The telemetry module SHALL track process uptime.

#### Scenario: Uptime reported
- **WHEN** a telemetry report is being prepared
- **THEN** `health.uptime_seconds` SHALL be the number of seconds since the errand-server process started (integer)

### Requirement: Task failure count
The telemetry module SHALL count task failures since the last successful telemetry report.

#### Scenario: Failures counted since last report
- **WHEN** a telemetry report is being prepared and the last report time is known
- **THEN** `health.task_failure_count` SHALL be the count of tasks with status `failed` whose `updated_at` is after the last report time

#### Scenario: No previous report
- **WHEN** a telemetry report is being prepared and no previous report time exists
- **THEN** `health.task_failure_count` SHALL be the total count of tasks with status `failed`

#### Scenario: No failures
- **WHEN** no tasks have failed since the last report
- **THEN** `health.task_failure_count` SHALL be `0`
