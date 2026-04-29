## Why

Opening the Task Logs modal on a running task currently shows a blank "Waiting for logs..." screen until the *next* runner event arrives. Tasks frequently spend many seconds (or minutes) between events — agent thinking, long-running tool calls — so users see no logs at all even when the task has produced substantial output earlier in the run. This makes the live log view feel broken and forces users to wait for output they have no way of knowing is coming.

The root cause is that log events are published to a Valkey pub/sub channel only; pub/sub does not replay history, so any client connecting after publication sees nothing until the *next* publish. There is no backlog stored anywhere accessible to the SSE endpoint mid-run (`runner_logs` on the Task row is only populated when the task finishes).

## What Changes

- Add a per-task event buffer in Valkey: when the task manager publishes a log event to the `task_logs:{task_id}` pub/sub channel, it SHALL also append the event JSON to a capped Valkey list `task_logs_buffer:{task_id}` (or equivalent structure). The buffer SHALL be trimmed to a configurable maximum length and SHALL be deleted (or expired) when the task ends.
- Modify the SSE log streaming endpoint (`GET /api/tasks/{task_id}/logs/stream`) so that on connect, before forwarding live pub/sub messages, it SHALL replay all buffered events for the task, in order, as `data:` SSE messages identical to live ones. Subscription to pub/sub SHALL happen before reading the buffer to avoid race-window event loss.
- The frontend `TaskLogViewer` in live mode requires no behavioural change: replayed events arrive as ordinary `task_event` messages, so the existing renderer immediately shows them and the "Waiting for logs..." placeholder disappears as soon as the first replayed event arrives.

## Capabilities

### New Capabilities

(none — this fix extends existing log-streaming behaviour)

### Modified Capabilities

- `sse-log-streaming`: the SSE log endpoint SHALL replay the buffered event history before forwarding live events; the backend SHALL maintain a per-task event buffer in Valkey alongside pub/sub publishing.
- `live-task-log-streaming`: clarify that, in live mode, the modal SHALL render any events the SSE stream delivers immediately on connect (i.e., backlog replay) and SHALL NOT show "Waiting for logs..." once any event has been received, whether buffered or live.

## Impact

- **Backend**: `errand/task_manager.py` log-publish loop must also `RPUSH` (and `LTRIM`) to a Valkey list per task, and clean up the list when publishing `task_log_end`. `errand/main.py` SSE endpoint must `LRANGE` the buffer and emit those entries before entering the pub/sub forwarding loop.
- **Frontend**: no API or component contract changes; the existing `TaskLogViewer` live mode handles the larger initial burst of events naturally.
- **Valkey usage**: additional memory per running task proportional to event buffer cap (e.g., 5,000 entries × ~1 KB ≈ a few MB per long-running task). Buffer is removed on task end.
- **Auth, schema, migrations**: none.
