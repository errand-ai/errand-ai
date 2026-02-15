## MODIFIED Requirements

### Requirement: Scheduler runs as background task in backend lifespan
The scheduler SHALL be started as an `asyncio.create_task()` during the FastAPI lifespan startup, after Valkey and the database engine are initialised. The scheduler task SHALL be cancelled during lifespan shutdown. The scheduler SHALL poll at a configurable interval (default 15 seconds) controlled by the `SCHEDULER_INTERVAL` environment variable.

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
- **THEN** the scheduler waits 15 seconds between cycles

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
