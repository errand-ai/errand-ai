## Why

When a task is in the "running" state, the user has no visibility into what the task runner is doing. They must wait for the task to complete (or fail) before seeing any output. For long-running tasks, this is a poor experience — there's no way to tell if the task is progressing, stuck, or about to fail. Live stderr streaming would give immediate feedback and help users decide whether to wait or intervene.

## What Changes

- Stream task runner container stderr in real-time during execution (currently only captured after container exit)
- Add a per-task Valkey pub/sub channel for log streaming (`task_logs:{task_id}`)
- Add a new WebSocket endpoint (`/api/ws/tasks/{task_id}/logs`) that streams live logs to connected clients
- Add a "View Logs" button on running task cards that opens a live log viewer modal
- Create a `TaskLogModal` component that connects to the log WebSocket, displays streaming log lines in a scrollable terminal-style view with auto-scroll, and transitions gracefully when the task finishes

## Capabilities

### New Capabilities
- `live-task-log-streaming`: Real-time streaming of task runner stderr from the worker through Valkey pub/sub to a frontend WebSocket, including the per-task channel design, the backend WS endpoint, and the frontend log viewer modal

### Modified Capabilities
- `task-worker`: The worker must stream stderr lines during container execution (not just capture after exit), publishing each chunk to a per-task Valkey channel. The existing post-execution log capture and `runner_logs` storage remain unchanged.
- `websocket-events`: A new per-task WebSocket endpoint is added for log streaming alongside the existing task-events endpoint. Follows the same auth pattern (JWT in query param).

## Impact

- **Backend (worker.py)**: `process_task_in_container` changes from `container.wait()` + `container.logs()` to streaming `container.logs(stream=True, follow=True)` with real-time Valkey publishing. Needs a sync Redis client in the executor thread.
- **Backend (main.py)**: New WebSocket endpoint `/api/ws/tasks/{task_id}/logs` subscribing to per-task Valkey channel.
- **Backend (events.py)**: May need a helper for per-task channel publishing (or worker uses sync Redis directly from thread).
- **Frontend (TaskCard.vue)**: New "View Logs" button visible when task status is `running`.
- **Frontend (new component)**: `TaskLogModal.vue` — terminal-style log viewer with dedicated WebSocket connection, auto-scroll, and task-completion detection.
- **Frontend (KanbanBoard.vue)**: Wire up the new log viewer modal and event handler.
- **Infrastructure**: No new dependencies — Valkey pub/sub already in use, Docker SDK streaming is built-in. Sync `redis` package already available (async `redis.asyncio` is currently used; sync `redis.Redis` is in the same package).
