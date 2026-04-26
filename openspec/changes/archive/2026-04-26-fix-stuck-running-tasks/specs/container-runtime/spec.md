## ADDED Requirements

### Requirement: Orphaned task recovery uses the running event loop
The `_recover_orphaned_task` function SHALL be an async function that performs DB operations using the existing event loop. It SHALL NOT use `asyncio.run()` or create a new event loop. The `cleanup_orphaned_jobs` function SHALL be async and SHALL await `_recover_orphaned_task` directly. Since `cleanup_orphaned_jobs` is called during FastAPI lifespan startup (which runs inside the event loop), synchronous K8s API calls SHALL be wrapped in `asyncio.to_thread()` to avoid blocking the event loop.

#### Scenario: Orphaned task recovery during startup
- **WHEN** the server starts and finds orphaned K8s Jobs from a previous instance
- **THEN** `_recover_orphaned_task` successfully updates the task status in the DB using the running event loop (no "different loop" error)

#### Scenario: Orphaned task with retries remaining
- **WHEN** an orphaned task has `retry_count < MAX_RETRIES`
- **THEN** the task is moved to "scheduled" with exponential backoff and a WebSocket event is published

#### Scenario: Orphaned task with retries exhausted
- **WHEN** an orphaned task has `retry_count >= MAX_RETRIES`
- **THEN** the task is moved to "review" with an explanatory output message
