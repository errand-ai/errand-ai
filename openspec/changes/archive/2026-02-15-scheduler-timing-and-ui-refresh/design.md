## Context

The scheduler (`backend/scheduler.py`) polls every `SCHEDULER_INTERVAL` seconds (default 30) and promotes tasks where `status = 'scheduled' AND execute_at <= func.now()` to `pending`. The query comparison is correct (`<=`), but users report tasks scheduled to the minute (e.g. `14:30:00`) being promoted up to a minute late.

The frontend (`TaskCard.vue`) displays `execute_at` as a relative time string via `formatRelativeTime()` from `useRelativeTime.ts`. This value is computed once at render and never updates — the displayed countdown goes stale as time passes.

## Goals / Non-Goals

**Goals:**

- Reduce worst-case scheduler promotion delay so tasks with minute-accuracy `execute_at` are promoted within a few seconds of their target time
- Make the relative time display on scheduled task cards update live (approximately every 30 seconds) without requiring page reload
- Keep both changes simple and low-risk

**Non-Goals:**

- Sub-second scheduling precision (not needed for this use case)
- Real-time push-based scheduling (e.g. scheduling exact timers per task) — polling is sufficient
- Changing the scheduler architecture (distributed lock, batch size, etc.)
- Refreshing cards in non-scheduled columns

## Decisions

### 1. Reduce default scheduler poll interval from 30s to 15s

**Rationale**: The worst-case promotion delay equals the poll interval. Reducing from 30s to 15s cuts the maximum delay in half while keeping the database load minimal (one lightweight query every 15s). The interval remains configurable via `SCHEDULER_INTERVAL` env var.

**Alternatives considered**:
- *10s interval*: Marginally better but doubles query rate vs current. 15s is a good balance.
- *Adaptive polling (faster when tasks are imminent)*: Over-engineered for this problem. The scheduler would need to peek at the next `execute_at` and adjust sleep time, adding complexity for little benefit.
- *Task-specific timers via asyncio.call_at*: Would require tracking individual timers, handling cancellation on task updates, and complicating the distributed lock model. Not worth it.

### 2. Use a reactive `now` ref with `setInterval` in a Vue composable for live countdown

**Rationale**: Vue's reactivity system won't re-render `formatRelativeTime(task.execute_at)` because the input (`task.execute_at`) doesn't change — only wall-clock time changes. The fix is a composable `useNow(intervalMs)` that returns a reactive `Ref<Date>` updated on a timer. TaskCard uses this `now` ref as a dependency so the template re-evaluates the relative time string periodically.

The composable will:
- Return a `ref(new Date())` that updates every 30 seconds
- Clean up the interval via `onUnmounted` (or `onScopeDispose`)
- Be called once per TaskCard instance in the scheduled column

Since each scheduled task card creates its own composable instance, the interval is only active while cards are mounted. When there are no scheduled tasks visible, no timers run.

**Alternatives considered**:
- *Global timer in the task store*: Would run even when the user isn't viewing scheduled tasks. Per-component is more efficient.
- *`key` hack on the `<p>` element bound to a ticking counter*: Forces DOM recreation, which is heavier than a reactive re-render.
- *Watchers or computed with `Date.now()`*: Vue doesn't track `Date.now()` — a computed using it would never re-evaluate. A reactive ref is required.

### 3. Pass `now` as a parameter to `formatRelativeTime` instead of modifying it

**Rationale**: Keeping `formatRelativeTime` as a pure function (takes `isoString` and `now`, returns string) makes it easily testable and avoids hidden dependencies on the clock. The existing tests continue to work unchanged since the `now` parameter defaults to `new Date()`.

## Risks / Trade-offs

- **[Slightly more DB load]** → 15s interval doubles the query rate from ~2/min to ~4/min. The query is indexed (`status + execute_at`) and typically returns 0 rows, so the impact is negligible.
- **[Timer per card]** → Each scheduled card runs a 30s `setInterval`. With many scheduled tasks visible (e.g. 50+), that's 50 timers. This is fine — `setInterval` callbacks are lightweight and the browser coalesces timer wakeups. If it ever becomes a concern, a single shared timer could be introduced.
- **[No change in scheduler architecture]** → The polling model has inherent latency (up to `SCHEDULER_INTERVAL` seconds). This is acceptable for minute-accuracy scheduling but would not suit sub-second use cases.
