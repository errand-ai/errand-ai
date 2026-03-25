## MODIFIED Requirements

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
