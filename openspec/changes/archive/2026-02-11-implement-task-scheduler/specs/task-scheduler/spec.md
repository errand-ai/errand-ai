## ADDED Requirements

### Requirement: Scheduler promotes due scheduled tasks to pending
The backend SHALL run a scheduler loop that periodically queries for tasks where `status = 'scheduled'` and `execute_at <= now()` (using database server time), and updates their status to `pending`. The scheduler SHALL use `SELECT ... FOR UPDATE SKIP LOCKED` when claiming tasks to prevent duplicate promotion. Promoted tasks SHALL have their `updated_at` timestamp set to the current time. The scheduler SHALL process tasks in batches of up to 100 per cycle.

#### Scenario: Scheduled task with past execute_at is promoted
- **WHEN** a task exists with `status = 'scheduled'` and `execute_at` is 5 minutes in the past
- **THEN** the scheduler updates the task's status to `pending` and sets `updated_at` to the current time

#### Scenario: Scheduled task with future execute_at is not promoted
- **WHEN** a task exists with `status = 'scheduled'` and `execute_at` is 10 minutes in the future
- **THEN** the scheduler does not change the task's status

#### Scenario: Task with null execute_at is not promoted
- **WHEN** a task exists with `status = 'scheduled'` and `execute_at` is null
- **THEN** the scheduler does not change the task's status

#### Scenario: Only scheduled-status tasks are promoted
- **WHEN** a task exists with `status = 'completed'` and `execute_at` is in the past
- **THEN** the scheduler does not change the task's status

#### Scenario: Multiple due tasks are promoted in one cycle
- **WHEN** three tasks exist with `status = 'scheduled'` and `execute_at` in the past
- **THEN** the scheduler promotes all three tasks to `pending` in a single cycle

### Requirement: Scheduler publishes WebSocket events on promotion
The scheduler SHALL publish a `task_updated` WebSocket event via the existing `publish_event()` function for each task promoted from `scheduled` to `pending`. The event payload SHALL include all task fields matching the `TaskResponse` schema.

#### Scenario: WebSocket event sent on promotion
- **WHEN** the scheduler promotes a task from `scheduled` to `pending`
- **THEN** a `task_updated` event is published to Valkey containing the full task data including id, title, description, status, position, category, execute_at, repeat_interval, repeat_until, output, retry_count, tags, created_at, and updated_at

### Requirement: Valkey distributed lock ensures single scheduler instance
The scheduler SHALL acquire a Valkey distributed lock before checking for due tasks. The lock SHALL use the `SET key value NX EX ttl` pattern with key `content-manager:scheduler-lock`, a TTL of 30 seconds, and the pod hostname as the lock value. If lock acquisition fails (another replica holds the lock), the scheduler SHALL skip the cycle and sleep until the next interval. The lock SHALL be refreshed every cycle while held.

#### Scenario: First replica acquires the lock and runs scheduler
- **WHEN** a single backend replica starts and no lock exists in Valkey
- **THEN** the replica acquires the lock and runs the scheduler check

#### Scenario: Second replica fails to acquire lock and skips
- **WHEN** two backend replicas are running and the first holds the lock
- **THEN** the second replica's `SET NX` returns false and it skips the scheduler cycle

#### Scenario: Lock expires and another replica takes over
- **WHEN** the lock-holding replica crashes and the lock TTL expires
- **THEN** another replica acquires the lock on its next cycle and resumes scheduling

#### Scenario: Lock is refreshed each cycle
- **WHEN** the lock-holding replica completes a scheduler cycle
- **THEN** it refreshes the lock TTL back to 30 seconds before sleeping

### Requirement: Scheduler runs as background task in backend lifespan
The scheduler SHALL be started as an `asyncio.create_task()` during the FastAPI lifespan startup, after Valkey and the database engine are initialised. The scheduler task SHALL be cancelled during lifespan shutdown. The scheduler SHALL poll at a configurable interval (default 30 seconds) controlled by the `SCHEDULER_INTERVAL` environment variable.

#### Scenario: Scheduler starts with the backend
- **WHEN** the FastAPI application starts up
- **THEN** the scheduler background task begins running

#### Scenario: Scheduler stops on shutdown
- **WHEN** the FastAPI application shuts down
- **THEN** the scheduler background task is cancelled and the Valkey lock is released if held

#### Scenario: Custom poll interval
- **WHEN** the `SCHEDULER_INTERVAL` environment variable is set to `60`
- **THEN** the scheduler waits 60 seconds between cycles

#### Scenario: Default poll interval
- **WHEN** the `SCHEDULER_INTERVAL` environment variable is not set
- **THEN** the scheduler waits 30 seconds between cycles

### Requirement: Scheduler is resilient to transient errors
The scheduler SHALL catch and log exceptions during each cycle without crashing. If a database or Valkey error occurs, the scheduler SHALL log the error and continue to the next cycle after the normal sleep interval.

#### Scenario: Database error during task query
- **WHEN** the database is temporarily unreachable during a scheduler cycle
- **THEN** the scheduler logs the error and retries on the next cycle

#### Scenario: Valkey error during lock acquisition
- **WHEN** Valkey is temporarily unreachable during lock acquisition
- **THEN** the scheduler logs the error and retries on the next cycle
