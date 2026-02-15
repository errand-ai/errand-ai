## Why

Scheduled tasks with minute-accuracy `execute_at` times (e.g. `14:30:00`) are not being promoted to pending at the exact target time. Users observe up to a full minute of delay before the scheduler picks them up. Additionally, the scheduled column's relative time display (e.g. "in 5m") is static — it renders once and never updates, so users see stale countdowns that don't reflect the actual time remaining as minutes tick by.

## What Changes

- **Investigate and fix scheduler promotion timing**: The scheduler query already uses `execute_at <= func.now()` (not `<`), so the comparison operator is correct. The likely cause is the 30-second default polling interval combined with possible lock contention or timezone/precision mismatches between application time and database `now()`. The fix may involve reducing the polling interval, aligning datetime precision, or adding sub-minute scheduling for tasks that are imminently due.
- **Add periodic UI refresh for scheduled column**: Task cards in the Scheduled column that display relative time strings ("in 5m", "in 2h") will auto-refresh on a timer so the displayed countdown stays accurate as time passes. When a card's countdown reaches zero or goes past, the WebSocket `task_updated` event from the scheduler will handle moving it to Pending — but the countdown display itself needs to tick independently.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-scheduler`: Fix timing behaviour so tasks with minute-accuracy `execute_at` are promoted within seconds of their target time, not up to a minute late. May involve adjusting the poll interval, datetime comparison precision, or adding an "imminent due" fast-poll mechanism.
- `kanban-frontend`: Add periodic refresh of relative time display on scheduled task cards so the countdown ("in 5m" → "in 4m" → ...) updates live without requiring a page reload or manual refresh.

## Impact

- **Backend**: `backend/scheduler.py` — scheduler polling interval and/or promotion logic
- **Frontend**: `frontend/src/components/TaskCard.vue` and `frontend/src/composables/useRelativeTime.ts` — add a timer-based re-render for scheduled cards
- **No API changes**: Both fixes are internal (scheduler timing) and UI-only (periodic refresh)
- **No database changes**: No schema or migration changes required
