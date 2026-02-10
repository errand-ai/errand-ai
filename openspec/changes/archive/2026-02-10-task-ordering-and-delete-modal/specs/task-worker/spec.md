## MODIFIED Requirements

### Requirement: Worker polls for pending tasks
The worker SHALL poll the database for tasks with status `pending` using `SELECT ... FOR UPDATE SKIP LOCKED` to safely dequeue a single task without contention with other workers. Tasks SHALL be dequeued in order of `position` ascending, with ties broken by `created_at` ascending, so that user-prioritised tasks are processed first.

#### Scenario: Task available
- **WHEN** the worker polls and a task with status `pending` exists
- **THEN** the worker acquires the task with the lowest position value, sets its status to `running`, and begins processing

#### Scenario: No tasks available
- **WHEN** the worker polls and no tasks have status `pending`
- **THEN** the worker waits for a configurable interval before polling again

#### Scenario: Multiple pending tasks with different positions
- **WHEN** the worker polls and tasks exist at positions 1, 3, and 5 in the Pending column
- **THEN** the worker acquires the task at position 1 (highest priority)
