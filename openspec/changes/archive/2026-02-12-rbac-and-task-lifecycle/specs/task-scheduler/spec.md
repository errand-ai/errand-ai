## MODIFIED Requirements

### Requirement: Scheduler promotes due scheduled tasks to pending

_(Append to existing requirement — auto-archive completed tasks)_

After promoting due scheduled tasks, the scheduler SHALL check for tasks where `status = 'completed'` and `updated_at` is older than the configured archive interval. The archive interval SHALL be read from the `archive_after_days` setting (default 3 days if the setting does not exist). Matching tasks SHALL have their status updated to `'archived'` and a `task_updated` WebSocket event SHALL be emitted for each archived task.

#### Scenario: Completed task auto-archived after interval
- **WHEN** a task has `status = 'completed'` and `updated_at` is 4 days ago, and `archive_after_days` is 3
- **THEN** the scheduler updates the task's status to `'archived'` and emits a `task_updated` WebSocket event

#### Scenario: Recently completed task not archived
- **WHEN** a task has `status = 'completed'` and `updated_at` is 1 day ago, and `archive_after_days` is 3
- **THEN** the scheduler does not change the task's status

#### Scenario: Custom archive interval
- **WHEN** `archive_after_days` is set to `7` and a completed task has `updated_at` 5 days ago
- **THEN** the scheduler does not archive the task (5 < 7)

#### Scenario: Default archive interval when setting not configured
- **WHEN** no `archive_after_days` setting exists in the settings table
- **THEN** the scheduler uses a default of 3 days

#### Scenario: Multiple completed tasks archived in one cycle
- **WHEN** three tasks have `status = 'completed'` with `updated_at` older than the archive interval
- **THEN** the scheduler archives all three tasks in a single cycle

#### Scenario: Only completed tasks are archived
- **WHEN** a task has `status = 'review'` with `updated_at` older than the archive interval
- **THEN** the scheduler does not archive it (only `completed` tasks are auto-archived)
