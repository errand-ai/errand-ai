## Context

The worker (`backend/worker.py`) processes tasks from the `pending` queue. When a task completes successfully (exit code 0, parsed status `completed`), it moves the task to `status = 'completed'`. For repeating tasks (category `repeating`), the lifecycle should continue: a new task is created with `execute_at` advanced by the `repeat_interval`, feeding back into the scheduler → worker pipeline. Currently this rescheduling step is missing.

The existing flow: scheduler promotes `scheduled` → `pending` → worker picks up → runs in container → moves to `completed`. The new flow adds: after moving to `completed`, if repeating + not expired → create clone as `scheduled`.

## Goals / Non-Goals

**Goals:**
- Automatically reschedule repeating tasks after successful completion
- Respect `repeat_until` to stop rescheduling when the series expires
- Parse simple interval strings (`15m`, `1h`, `1d`, `1w`) and crontab expressions into concrete `execute_at` datetimes
- Keep completed tasks as historical records (do not reuse the same row)
- Publish WebSocket events so the frontend updates in real time

**Non-Goals:**
- Rescheduling on failure (failed tasks use the existing retry mechanism)
- Rescheduling tasks that reach `needs_input` / `review` status (only `completed` triggers rescheduling)
- Frontend changes (existing WebSocket + Kanban handles new tasks automatically)
- Crontab expression evaluation for complex schedules (defer to a library like `croniter` if needed; for MVP, simple intervals cover the common cases and crontab can be added later)

## Decisions

### Decision 1: Clone vs reuse task row
**Choice**: Clone — create a new Task row for each iteration.
**Rationale**: Keeps completed iterations as a history trail. Each task has its own output, runner_logs, and timestamps. Reusing the row would lose the output from the previous run. Cloning also avoids race conditions with the frontend reading a task that's simultaneously being reset.

### Decision 2: Where to put the rescheduling logic
**Choice**: Inline in the worker's `run()` function, immediately after moving a task to `completed`.
**Rationale**: The worker already has the task object loaded with all fields. Adding rescheduling as a follow-up step in the same code path is the simplest approach. A separate function `_reschedule_if_repeating(task)` keeps the logic encapsulated and testable.

### Decision 3: Interval parsing approach
**Choice**: A helper function `parse_interval(interval_str)` that handles simple duration strings first. Returns a `timedelta`.
**Supported formats**:
- `15m` → 15 minutes
- `1h` → 1 hour
- `1d` → 1 day
- `1w` → 7 days
- Numeric variants: `30m`, `2h`, `7d`, `2w`

**Crontab**: Not supported in the initial implementation. If `repeat_interval` doesn't match a simple pattern, log a warning and skip rescheduling. Crontab support can be added later with `croniter`.

### Decision 4: What fields to copy forward
**Copy**: title, description, category, repeat_interval, repeat_until, tags
**Reset**: status → `scheduled`, execute_at → `now() + interval`, output → null, runner_logs → null, retry_count → 0, position → next position in scheduled column
**New**: fresh UUID, created_at, updated_at set to now

### Decision 5: WebSocket event type
**Choice**: Publish a `task_created` event for the new task (matching what the task creation API endpoint publishes), so the frontend's existing WebSocket handler adds it to the board.

## Risks / Trade-offs

- **[Rapid rescheduling]** A task with `repeat_interval: "1m"` that completes in seconds could generate many tasks quickly → Mitigation: This is intentional behavior; `repeat_until` provides the stop mechanism. The scheduler + worker pipeline naturally throttles by processing one at a time.
- **[Tag duplication]** Cloning tags requires looking up existing tag objects to create associations → Mitigation: Use the same tag rows (many-to-many), just insert new `task_tags` rows.
- **[Crontab gap]** Simple interval parsing doesn't handle crontab expressions → Mitigation: Log a warning and skip. Users see the task complete without rescheduling. Crontab support is a follow-up change.
