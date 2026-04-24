## Purpose

Async TaskManager that runs as a FastAPI lifespan background task, using Postgres advisory lock for leader election and asyncio semaphore for concurrency control.

## Requirements

### Requirement: TaskManager class with leader-elected poll loop

The server SHALL include a `TaskManager` class in `errand/task_manager.py` that runs as an asyncio background task started during FastAPI lifespan. The TaskManager SHALL attempt to acquire a Postgres advisory lock (`pg_try_advisory_lock(hash('errand_task_manager'))`) on each poll cycle. If the lock is acquired, the TaskManager SHALL poll for pending tasks and process them. If the lock is not acquired (another replica holds it), the TaskManager SHALL log at INFO level and sleep and retry. The advisory lock SHALL be session-scoped — it releases automatically when the DB connection drops. The poll interval SHALL be configurable via `POLL_INTERVAL` environment variable (default: 5 seconds).

The advisory lock connection SHALL be created with TCP keepalive enabled via libpq connection parameters: `keepalives=1`, `keepalives_idle=10`, `keepalives_interval=10`, `keepalives_count=3`. This ensures Postgres detects dead connections within approximately 40 seconds of peer death, preventing stale locks from blocking task processing after pod restarts.

#### Scenario: Single replica acquires lock and processes tasks

- **WHEN** one server replica starts the TaskManager
- **THEN** it acquires the advisory lock, polls for pending tasks, and processes them

#### Scenario: Second replica waits as standby

- **WHEN** two server replicas start and replica 1 holds the advisory lock
- **THEN** replica 2's TaskManager detects the lock is held, logs at INFO level that another replica holds the lock, and retries after the sleep interval

#### Scenario: Leader pod crashes and standby takes over

- **WHEN** the leader pod is killed (SIGKILL, OOM, etc.) without clean shutdown
- **THEN** Postgres detects the dead TCP connection via keepalive probes within approximately 40 seconds, the advisory lock is released, and the standby replica acquires it on next poll and begins processing tasks

#### Scenario: Graceful shutdown

- **WHEN** the server receives SIGTERM
- **THEN** the TaskManager stops accepting new tasks, waits for in-flight tasks to complete (with a timeout), releases the advisory lock, and shuts down

### Requirement: Concurrent task processing with configurable limit

The TaskManager SHALL use an `asyncio.Semaphore` to limit the number of concurrently processing tasks. The semaphore size SHALL be read from the `max_concurrent_tasks` database setting (default: 3) on each poll cycle. When the setting changes, the TaskManager SHALL create a new semaphore with the updated size — in-flight tasks continue with the old semaphore, new tasks use the new one. Each dequeued task SHALL be processed in its own asyncio coroutine via `asyncio.create_task()`. The TaskManager SHALL only dequeue a new task when the semaphore has available capacity.

#### Scenario: Concurrent tasks up to limit

- **WHEN** `max_concurrent_tasks` is 3 and 3 tasks are pending
- **THEN** all 3 tasks are dequeued and processed concurrently

#### Scenario: Queue exceeds concurrency limit

- **WHEN** `max_concurrent_tasks` is 2 and 5 tasks are pending
- **THEN** 2 tasks are dequeued and started; the remaining 3 wait until a slot becomes available

#### Scenario: Concurrency limit changed at runtime

- **WHEN** a user changes `max_concurrent_tasks` from 2 to 5 via settings UI
- **THEN** the TaskManager picks up the new value on the next poll cycle and allows up to 5 concurrent tasks

#### Scenario: Sub-task does not deadlock

- **WHEN** a task-runner creates a sub-task via MCP `new_task` and polls `task_status`, with `max_concurrent_tasks` >= 2
- **THEN** the sub-task is dequeued and processed in a separate coroutine while the parent task's container continues running

### Requirement: Per-task coroutine lifecycle

Each task SHALL be processed in its own async coroutine that handles: (1) reading settings and resolving profile overrides, (2) preparing the container via the runtime, (3) streaming logs asynchronously and publishing to Valkey, (4) updating heartbeat periodically, (5) reading results and updating the database, (6) retry/reschedule logic on failure, (7) cleanup. Exceptions in one task's coroutine SHALL NOT affect other tasks or the TaskManager poll loop.

#### Scenario: Task coroutine runs to completion

- **WHEN** a task is dequeued and its container exits successfully
- **THEN** the coroutine parses the result, updates the DB, publishes events, and releases the semaphore slot

#### Scenario: Task coroutine fails with exception

- **WHEN** a task's coroutine raises an unhandled exception
- **THEN** the exception is caught and logged, the task is retried via the existing backoff logic, and the semaphore slot is released

#### Scenario: Multiple tasks stream logs concurrently

- **WHEN** 3 tasks are running concurrently
- **THEN** each task streams its own logs to its own Valkey channel (`task_logs:{task_id}`) independently

### Requirement: FastAPI lifespan integration

The server's FastAPI app SHALL start the TaskManager during the lifespan startup phase and stop it during shutdown. The TaskManager SHALL be started via `asyncio.create_task(task_manager.run())`. The TaskManager SHALL respect the `TASK_MANAGER_ENABLED` environment variable (default: `true`) — when set to `false`, no TaskManager is started, allowing a server replica to run as a pure API server.

#### Scenario: Server starts with TaskManager

- **WHEN** the server starts with `TASK_MANAGER_ENABLED=true` (default)
- **THEN** the TaskManager background task is created and begins polling

#### Scenario: Server starts without TaskManager

- **WHEN** the server starts with `TASK_MANAGER_ENABLED=false`
- **THEN** no TaskManager is created; the server only serves API requests

#### Scenario: Server shutdown stops TaskManager

- **WHEN** the server shuts down
- **THEN** the TaskManager is signalled to stop, waits for in-flight tasks, and the background task completes

### Requirement: max_concurrent_tasks setting

The settings registry SHALL include a `max_concurrent_tasks` setting with default value `3`. The setting SHALL be displayed in the Task Management settings tab as a numeric input. The setting SHALL be readable by the TaskManager on each poll cycle without restart.

#### Scenario: Default value

- **WHEN** `max_concurrent_tasks` has no database entry
- **THEN** the TaskManager uses the default of 3

#### Scenario: User changes via settings UI

- **WHEN** a user sets `max_concurrent_tasks` to 5 in the settings UI
- **THEN** the value is persisted to the database and the TaskManager picks it up on the next poll cycle

### Requirement: Safe ORM task data handoff after session close

When the TaskManager dequeues a task for processing, it SHALL copy all required task fields into a plain Python object (dataclass or dict) while the database session is still open. The ORM instance SHALL NOT be passed to the spawned processing coroutine. This prevents `DetachedInstanceError` from attribute access after the source session is closed.

#### Scenario: Task fields accessible after session closes

- **WHEN** a task is dequeued and the database session is closed before the processing coroutine runs
- **THEN** the processing coroutine can access all task fields without raising `DetachedInstanceError`

#### Scenario: ORM instance not referenced after session close

- **WHEN** a task processing coroutine starts
- **THEN** it receives a plain data object (not a SQLAlchemy ORM instance bound to a closed session)

### Requirement: Skip review state for external client tasks

When a task completes with `needs_input` status and was created by an external client, the task manager SHALL move it directly to `completed` instead of `review`.

#### Scenario: External client task with needs_input
- **WHEN** a task finishes with `parsed.status == "needs_input"`
- **AND** the task's `created_by` is not a known internal source (`"system"`, `"mcp"`, an email address, or `"email_poller"`)
- **THEN** the task SHALL move to `completed` status (not `review`)
- **AND** the task's output and questions SHALL still be stored

#### Scenario: Internal task with needs_input (unchanged)
- **WHEN** a task finishes with `parsed.status == "needs_input"`
- **AND** the task's `created_by` is a known internal source (e.g. `"mcp"`, `"system"`, a user email)
- **THEN** the task SHALL move to `review` status as before (backward compatible)

#### Scenario: Completed task (unchanged)
- **WHEN** a task finishes with `parsed.status == "completed"`
- **THEN** the task SHALL move to `completed` status regardless of `created_by`

### Requirement: Cached sync database engine

The `_resolve_provider_sync` function SHALL use a module-level cached sync engine instead of calling `create_sync_engine()` on every invocation. The engine SHALL be created once (lazily on first call or at module import) and reused for all subsequent calls. The engine SHALL never be created more than once per process lifetime.

#### Scenario: Engine created once per process

- **WHEN** `_resolve_provider_sync` is called multiple times during the lifetime of the server process
- **THEN** `create_sync_engine()` is called exactly once and the same engine instance is reused

#### Scenario: Engine reused across concurrent calls

- **WHEN** multiple tasks call `_resolve_provider_sync` concurrently
- **THEN** all calls use the same cached engine and no new connection pools are created
