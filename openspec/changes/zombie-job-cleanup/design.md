## Context

When a worker crashes or is restarted mid-task, tasks stuck in `status="running"` are never recovered. The scheduler (`run_scheduler()` in `main.py`) only handles `scheduled→pending` promotion and `completed→archived` transitions — it has no awareness of stale running tasks. In K8s mode, the worker's `cleanup_orphaned_jobs()` deletes all orphaned Jobs on startup without checking or updating task status in the database.

Current architecture:
- **Worker** (`worker.py`): `run_worker()` is async, picks pending tasks, sets them to `running`, then delegates to `process_task_in_container()` via `run_in_executor`. Log streaming happens in a sync `for line in runtime.run(handle)` loop inside the executor thread.
- **Scheduler** (`scheduler.py`): Runs in the main service lifespan. Uses Valkey distributed lock (`errand:scheduler-lock`, TTL 30s) to prevent concurrent execution across replicas. Loops every 15s.
- **K8s cleanup** (`container_runtime.py`): `cleanup_orphaned_jobs()` runs at worker startup, lists Jobs by label `app.kubernetes.io/managed-by=content-manager-worker`, deletes them all.
- **Retry logic** (`_schedule_retry()`): Exponential backoff `2^retry_count` minutes, increments `retry_count`, moves to `scheduled`. Max retries handled by `MAX_GIT_RETRIES = 5` in the git error path only — no general max-retry cap outside git errors.

## Goals / Non-Goals

**Goals:**
- Automatically detect tasks stuck in "running" state beyond a configurable timeout
- Recover zombie tasks by moving them back to "scheduled" (with backoff) or "review" (if retries exhausted)
- Track worker liveness via a `heartbeat_at` timestamp on the task row
- Improve K8s orphaned Job cleanup to cross-reference task database before deleting
- Publish WebSocket events so the frontend reflects recovered tasks immediately

**Non-Goals:**
- Worker-to-worker health checks or worker registration system — the heartbeat is per-task, not per-worker
- Cleaning up Docker runtime orphans (Docker mode is local dev only, no multi-replica concerns)
- Changing the existing retry/backoff formula or max retry count
- Adding a UI for zombie task management — recovery is fully automatic

## Decisions

### Decision 1: Heartbeat via direct DB update from the executor thread

**Choice:** Update `heartbeat_at` using a sync SQLAlchemy engine + `UPDATE` statement from within the log-streaming loop (which runs in a thread via `run_in_executor`).

**Why:** The log-streaming loop is synchronous (iterating `runtime.run(handle)`). We can't use the async session from this thread (cross-event-loop issues, same problem we fixed for GH_TOKEN). A dedicated sync engine using the same `DATABASE_URL` keeps it simple.

**Alternatives considered:**
- *Publish heartbeat via Valkey, process in async caller* — adds complexity (message protocol, subscriber loop) for a simple periodic write
- *Use `asyncio.run()` with a fresh async engine* — works but is heavier than a sync engine for a single UPDATE statement
- *Thread-safe queue between executor and async loop* — over-engineered for a timestamp update

**Implementation:** Create a module-level sync engine (lazily initialized from `DATABASE_URL`), use `engine.execute(text("UPDATE tasks SET heartbeat_at = NOW() WHERE id = :id"), {"id": task_id})` every 60 seconds during log streaming. Wrap in try/except — heartbeat failure must never block task execution.

### Decision 2: Zombie cleanup as a separate background loop in the main service

**Choice:** Add `run_zombie_cleanup()` as a new background task in the main service lifespan, parallel to `run_scheduler()`. Uses its own Valkey distributed lock (`errand:zombie-cleanup-lock`).

**Why:** The main service already runs the scheduler loop with the same pattern (lock, query, update, publish events). Zombie cleanup is conceptually a scheduler concern. Using a separate lock (not the scheduler lock) allows both loops to run independently and avoids extending the scheduler's lock hold time.

**Alternatives considered:**
- *Add to existing scheduler loop* — couples concerns, extends lock hold time, makes scheduler cycle time unpredictable if many zombies found
- *Run in worker process* — workers are ephemeral and may be the ones that crashed; the main service is the right place for oversight
- *Cron job / external process* — adds operational complexity, no advantage over in-process loop

### Decision 3: Heartbeat timeout fallback to `updated_at` for pre-existing tasks

**Choice:** When `heartbeat_at` is NULL (tasks that started running before the heartbeat feature was deployed), fall back to `updated_at` for zombie detection.

**Why:** After deployment, there may be tasks already in "running" state that were set before the heartbeat column existed. Using `updated_at` as a fallback ensures these aren't stuck forever. Once all running tasks have heartbeats, this code path becomes dormant.

### Decision 4: K8s cleanup reads `content-manager/task-id` label from Jobs

**Choice:** The existing K8s Job label `content-manager/task-id` (already set during Job creation) is used to look up the corresponding task in the database during orphaned Job cleanup.

**Why:** No schema changes needed on the K8s side — the label is already there. The cleanup function just needs a database session to query task status before deleting.

### Decision 5: General max-retry cap of 5 for zombie recovery

**Choice:** Use the same max-retry threshold (5) already used for git errors. When a zombie task's `retry_count >= 5`, move to "review" instead of "scheduled".

**Why:** Prevents infinite retry loops for tasks that keep crashing workers. The threshold of 5 matches the existing `MAX_GIT_RETRIES` convention, giving the system up to 5 chances (with exponential backoff: 1, 2, 4, 8, 16 minutes) before escalating to human review.

## Risks / Trade-offs

**[Risk] Heartbeat DB writes add load during task execution** → The update is a single-row UPDATE by primary key every 60 seconds — negligible load. If the DB is temporarily unreachable, the heartbeat silently fails and the task continues processing normally.

**[Risk] Zombie timeout too aggressive could recover still-running tasks** → Default timeout is 300 seconds (5 minutes), which is generous for a 60-second heartbeat interval. A task would need to miss 5 consecutive heartbeats before being flagged. Configurable via `ZOMBIE_TIMEOUT_SECONDS` env var.

**[Risk] Race condition between worker completing a task and zombie cleanup recovering it** → The zombie cleanup only touches tasks with stale heartbeats. A worker that's actively processing will have a fresh heartbeat. If the worker finishes between the zombie check and the status update, the task will be in "completed" or "scheduled", not "running", so the zombie UPDATE (which filters on `status = "running"`) will affect 0 rows.

**[Risk] K8s cleanup now requires DB access from worker** → The worker already has DB access (it reads settings, updates task status). The cleanup function just needs to query tasks by ID, which is a simple read operation.

**[Trade-off] Sync engine for heartbeat vs reusing async infrastructure** → We accept a second database connection (sync) in the worker to keep the heartbeat logic simple and avoid cross-event-loop issues. The sync connection is only used for the periodic heartbeat UPDATE during active task execution.
