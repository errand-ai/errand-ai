## ADDED Requirements

### Requirement: Worker reschedules completed repeating tasks
After the worker moves a task with `category = 'repeating'` to `status = 'completed'`, it SHALL check whether the task should be rescheduled. If `repeat_until` is set and the current UTC time is past `repeat_until`, the worker SHALL NOT create a new task. Otherwise, the worker SHALL create a new task by cloning the completed task's fields and setting `status = 'scheduled'` and `execute_at = now() + repeat_interval`.

#### Scenario: Repeating task is rescheduled after completion
- **WHEN** a task with `category = 'repeating'`, `repeat_interval = '30m'`, and `repeat_until = null` is moved to `completed`
- **THEN** the worker creates a new task with the same title, description, category, repeat_interval, repeat_until, and tags, with `status = 'scheduled'` and `execute_at` approximately 30 minutes from now

#### Scenario: Repeating task with repeat_until in the future is rescheduled
- **WHEN** a task with `category = 'repeating'`, `repeat_interval = '1h'`, and `repeat_until` set to 24 hours from now is moved to `completed`
- **THEN** the worker creates a new task with `status = 'scheduled'` and `execute_at` approximately 1 hour from now

#### Scenario: Repeating task with expired repeat_until is not rescheduled
- **WHEN** a task with `category = 'repeating'`, `repeat_interval = '1d'`, and `repeat_until` set to 1 hour ago is moved to `completed`
- **THEN** the worker does NOT create a new task

#### Scenario: Non-repeating completed task is not rescheduled
- **WHEN** a task with `category = 'immediate'` is moved to `completed`
- **THEN** the worker does NOT create a new task

#### Scenario: Repeating task that reaches needs_input is not rescheduled
- **WHEN** a task with `category = 'repeating'` is moved to `review` status (needs_input)
- **THEN** the worker does NOT create a new task (rescheduling only applies to `completed`)

### Requirement: Cloned task fields
The cloned task SHALL copy the following fields from the completed task: `title`, `description`, `category`, `repeat_interval`, `repeat_until`, and `tags`. The cloned task SHALL have a new UUID, `status = 'scheduled'`, `execute_at` set to the current UTC time plus the parsed `repeat_interval`, `position` set to the next available position in the `scheduled` column, and `output`, `runner_logs`, `retry_count` all reset to their defaults (null, null, 0). The `created_at` and `updated_at` fields SHALL be set to the current UTC time.

#### Scenario: Cloned task has fresh metadata
- **WHEN** a repeating task with output "Previous result" and runner_logs "Previous logs" and retry_count 2 is rescheduled
- **THEN** the new task has `output = null`, `runner_logs = null`, `retry_count = 0`, and a new UUID different from the original

#### Scenario: Cloned task copies tags
- **WHEN** a repeating task with tags ["Monitoring", "Production"] is rescheduled
- **THEN** the new task has the same tags ["Monitoring", "Production"]

### Requirement: Interval parsing for simple durations
The worker SHALL parse `repeat_interval` values in the format `<number><unit>` where unit is `m` (minutes), `h` (hours), `d` (days), or `w` (weeks). If the `repeat_interval` does not match this format, the worker SHALL log a warning and skip rescheduling.

#### Scenario: Parse minutes interval
- **WHEN** `repeat_interval` is `"30m"`
- **THEN** the parsed duration is 30 minutes

#### Scenario: Parse hours interval
- **WHEN** `repeat_interval` is `"2h"`
- **THEN** the parsed duration is 2 hours

#### Scenario: Parse days interval
- **WHEN** `repeat_interval` is `"1d"`
- **THEN** the parsed duration is 1 day (24 hours)

#### Scenario: Parse weeks interval
- **WHEN** `repeat_interval` is `"1w"`
- **THEN** the parsed duration is 7 days

#### Scenario: Unparseable interval skips rescheduling
- **WHEN** `repeat_interval` is `"0 9 * * MON-FRI"` (crontab format, not yet supported)
- **THEN** the worker logs a warning and does NOT create a new task

### Requirement: WebSocket event for rescheduled task
The worker SHALL publish a `task_created` WebSocket event for the newly created task, containing all task fields matching the `TaskResponse` schema. This allows the frontend to add the new task to the Kanban board in real time.

#### Scenario: WebSocket event published for rescheduled task
- **WHEN** the worker creates a rescheduled task
- **THEN** a `task_created` event is published containing the new task's id, title, description, status, position, category, execute_at, repeat_interval, repeat_until, output, runner_logs, retry_count, tags, created_at, and updated_at
