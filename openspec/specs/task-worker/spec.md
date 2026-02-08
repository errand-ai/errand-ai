## ADDED Requirements

### Requirement: Worker polls for pending tasks
The worker SHALL poll the database for tasks with status `pending` using `SELECT ... FOR UPDATE SKIP LOCKED` to safely dequeue a single task without contention with other workers.

#### Scenario: Task available
- **WHEN** the worker polls and a task with status `pending` exists
- **THEN** the worker acquires the task, sets its status to `running`, and begins processing

#### Scenario: No tasks available
- **WHEN** the worker polls and no tasks have status `pending`
- **THEN** the worker waits for a configurable interval before polling again

### Requirement: Worker processes one task at a time
Each worker instance SHALL process exactly one task at a time. The worker MUST complete or fail the current task before polling for the next one.

#### Scenario: Sequential processing
- **WHEN** the worker finishes processing a task
- **THEN** it sets the task status to `completed` and immediately polls for the next task

### Requirement: Worker marks failed tasks
If task processing raises an exception, the worker SHALL set the task status to `failed` and continue polling for the next task. The worker process MUST NOT crash on task failure.

#### Scenario: Task processing fails
- **WHEN** processing a task raises an unhandled exception
- **THEN** the worker sets the task status to `failed`, logs the error, and continues polling

### Requirement: Worker uses same database models as backend
The worker SHALL import database models and connection configuration from the shared backend Python package to prevent schema drift.

#### Scenario: Shared models
- **WHEN** the backend adds a new column to the tasks table
- **THEN** the worker sees the same column because it uses the same SQLAlchemy model

### Requirement: Worker graceful shutdown
The worker SHALL handle SIGTERM by finishing the current task (if any) before exiting. It MUST NOT abandon a task in `running` status on shutdown.

#### Scenario: SIGTERM during task processing
- **WHEN** the worker receives SIGTERM while processing a task
- **THEN** it finishes processing the current task, updates its status, and then exits

#### Scenario: SIGTERM while idle
- **WHEN** the worker receives SIGTERM while waiting to poll
- **THEN** it exits immediately
