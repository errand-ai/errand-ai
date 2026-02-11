## Context

Tasks with category `scheduled` or `repeating` are placed in `scheduled` status with an `execute_at` timestamp by the task categoriser. Currently nothing checks whether that time has arrived. The worker only polls for `pending` tasks, so scheduled tasks sit indefinitely.

The backend may run multiple replicas behind a Kubernetes deployment. A naive in-process scheduler would run on every replica, causing duplicate promotions. We need coordination so exactly one replica runs the scheduler loop at a time.

The project already uses Valkey (Redis-compatible) via `redis-py` in `events.py` for WebSocket event pub/sub. The same connection can be reused for distributed locking.

## Goals / Non-Goals

**Goals:**
- Promote tasks in `scheduled` status to `pending` when `execute_at <= now()`
- Ensure only one backend replica runs the scheduler at a time
- Automatic failover if the lock-holding replica stops
- Reuse existing Valkey infrastructure — no new dependencies

**Non-Goals:**
- Repeating task rescheduling (future change — will need to compute next `execute_at` from `repeat_interval` after completion)
- Sub-second scheduling precision (minute-level granularity is sufficient)
- Dedicated scheduler deployment or sidecar — runs in-process in the backend
- Admin UI for viewing/managing scheduler state

## Decisions

### 1. Valkey distributed lock via `SET NX EX`

Use the Redis `SET key value NX EX ttl` pattern for distributed locking. One replica acquires the lock; others fail the `NX` (set-if-not-exists) check and skip. The lock has a TTL so it auto-expires if the holder crashes.

**Alternatives considered:**
- **PostgreSQL advisory locks**: Viable, but requires a dedicated persistent DB connection. Valkey is simpler and already connected.
- **Kubernetes Lease-based leader election**: Requires RBAC changes (pods need Lease permissions), harder to test locally without a cluster.
- **Single-replica scheduler deployment**: Simplest, but adds Helm complexity and has ~30s downtime on pod restarts.

**Lock parameters:**
- Key: `content-manager:scheduler-lock`
- TTL: 30 seconds
- Refresh: Every 10 seconds (well within TTL)
- Lock value: Pod hostname (for debugging — identifies which replica holds the lock)

### 2. Scheduler runs as a background asyncio task in the backend

Start the scheduler loop as an `asyncio.create_task()` in the FastAPI `lifespan` startup. Every replica attempts to acquire the lock on each cycle. The replica that holds the lock performs the task query; others sleep and retry.

**Why not a separate process?** The backend already initialises Valkey and the database engine. Running in-process avoids duplicating setup and keeps the deployment simple (no new containers, Dockerfiles, or Helm resources).

### 3. New `scheduler.py` module

Create `backend/scheduler.py` with:
- `run_scheduler()` — the async loop (acquire lock → query due tasks → promote → sleep)
- `promote_due_tasks()` — queries tasks where `status = 'scheduled'` and `execute_at <= now()`, updates them to `pending`
- Uses `SELECT ... FOR UPDATE SKIP LOCKED` as a safety net even though the Valkey lock prevents concurrent schedulers — defence in depth

**Poll interval:** 30 seconds (configurable via `SCHEDULER_INTERVAL` env var). Balances responsiveness with DB load. For a task like "send the report at 5pm," being up to 30 seconds late is acceptable.

### 4. Reuse `get_valkey()` from events module

The scheduler imports `get_valkey()` from `events.py` rather than creating its own Valkey connection. The connection is already initialised in the FastAPI lifespan before the scheduler starts.

### 5. Publish `task_updated` events on promotion

When tasks are promoted from `scheduled` to `pending`, publish `task_updated` WebSocket events via the existing `publish_event()` function. This keeps the frontend Kanban board in sync — tasks move from the Scheduled column to Pending in real time.

## Risks / Trade-offs

- **Lock expiry during long GC pause or event loop block** → The 30s TTL is generous; a 10s refresh interval gives 20s of buffer. If the lock expires, another replica takes over — worst case is one duplicate check cycle, and `FOR UPDATE SKIP LOCKED` prevents double-promotion.
- **Valkey downtime** → If Valkey is unavailable, no replica can acquire the lock, so the scheduler pauses. Tasks will be promoted once Valkey recovers. This is acceptable — Valkey downtime also breaks WebSocket events, so it's already a known degraded state.
- **Clock skew between replicas** → `execute_at` comparison uses the database `now()` (server-side), not Python `datetime.now()`, so replica clock differences don't matter.
- **Many due tasks at once** → Batch promotion with a `LIMIT` clause (e.g., 100 per cycle) prevents a single cycle from running too long. Remaining tasks are picked up in subsequent cycles.
