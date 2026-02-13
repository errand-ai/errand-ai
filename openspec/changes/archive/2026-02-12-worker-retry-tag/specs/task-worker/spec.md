## MODIFIED Requirements

### Requirement: Worker executes tasks in DinD containers

_(Append to existing requirement — retry and success tag behaviour)_

When the worker schedules a task for retry via `_schedule_retry`, it SHALL add a "Retry" tag to the task. If the "Retry" tag does not exist in the `tags` table, the worker SHALL create it. If the task already has the "Retry" tag, no duplicate association SHALL be created.

When the worker successfully processes a task (moves to `completed` or `review` status), it SHALL remove the "Retry" tag from the task if present. This ensures the tag does not persist on tasks that eventually succeed.

#### Scenario: Retry adds "Retry" tag
- **WHEN** the worker processes a task and the container exits with a non-zero exit code
- **THEN** the worker moves the task to `scheduled` status with exponential backoff and adds a "Retry" tag to the task

#### Scenario: Retry on unparseable output adds "Retry" tag
- **WHEN** the worker processes a task and the container exits with code 0 but stdout is not valid JSON
- **THEN** the worker moves the task to `scheduled` status and adds a "Retry" tag to the task

#### Scenario: Successful completion removes "Retry" tag
- **WHEN** the worker processes a task that has a "Retry" tag and the container exits with code 0 and valid structured output with status "completed"
- **THEN** the worker moves the task to `completed` status and removes the "Retry" tag

#### Scenario: Review status removes "Retry" tag
- **WHEN** the worker processes a task that has a "Retry" tag and the container exits with code 0 and valid structured output with status "needs_input"
- **THEN** the worker moves the task to `review` status, adds the "Input Needed" tag, and removes the "Retry" tag

#### Scenario: Retry tag created if not exists
- **WHEN** the worker schedules a task for retry and no "Retry" tag exists in the tags table
- **THEN** the worker creates the "Retry" tag and associates it with the task

#### Scenario: No duplicate retry tag
- **WHEN** the worker schedules a task for retry and the task already has a "Retry" tag from a previous retry
- **THEN** no duplicate tag association is created
