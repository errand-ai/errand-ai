## 1. Worker: Stream stderr in real-time

- [x] 1.1 Refactor `process_task_in_container` to accept `task_id` parameter (currently receives full `Task` object — need task ID for the Valkey channel name)
- [x] 1.2 Create a sync `redis.Redis` client at the start of `process_task_in_container`, closed in a `finally` block, using `VALKEY_URL`
- [x] 1.3 Replace `container.wait()` with `container.logs(stream=True, follow=True, stderr=True, stdout=False)` iteration that publishes each chunk as `{"event": "task_log", "line": "<chunk>"}` to `task_logs:{task_id}`
- [x] 1.4 After the streaming loop, publish `{"event": "task_log_end"}` to the same channel
- [x] 1.5 After streaming completes, call `container.wait()` for exit code and `container.logs()` for full stdout/stderr capture (existing parsing logic unchanged)
- [x] 1.6 Handle sync Redis publish failures with a warning log (no interruption to task processing)

## 2. Backend: WebSocket endpoint for log streaming

- [x] 2.1 Add `ws_task_logs` WebSocket endpoint at `/api/ws/tasks/{task_id}/logs` with JWT auth via `token` query param (same pattern as `ws_tasks`)
- [x] 2.2 On connect, check task exists in DB — close with 4004 if not found
- [x] 2.3 On connect, check task status — if not `running`, send `{"event": "task_log_end"}` and close with 1000
- [x] 2.4 Subscribe to Valkey channel `task_logs:{task_id}` and forward messages to the WebSocket client
- [x] 2.5 On receiving `task_log_end` from Valkey, forward to client and close WebSocket with 1000
- [x] 2.6 Clean up Valkey subscription on client disconnect

## 3. Frontend: TaskCard log button

- [x] 3.1 Add `view-logs` emit to `TaskCard.vue` component
- [x] 3.2 Add computed `showLogButton` that returns true when `columnStatus === 'running'`
- [x] 3.3 Add "View Logs" button (terminal/console icon) visible when `showLogButton` is true, emitting `view-logs` on click

## 4. Frontend: TaskLogModal component

- [x] 4.1 Create `TaskLogModal.vue` — `<dialog>` modal with terminal-style dark background, monospace font, scrollable log area
- [x] 4.2 On mount, open WebSocket to `/api/ws/tasks/{task_id}/logs?token=...` using the auth store token
- [x] 4.3 Append received `task_log` lines to a reactive array, render in a `<pre>` block
- [x] 4.4 Implement auto-scroll: scroll to bottom on each new line (respect if user has scrolled up)
- [x] 4.5 On `task_log_end` event, show "Task finished" indicator and stop waiting
- [x] 4.6 Show "Waiting for logs..." placeholder when no lines received yet
- [x] 4.7 Close WebSocket on modal unmount (Close button, Escape, or backdrop click)

## 5. Frontend: Wire up in KanbanBoard

- [x] 5.1 Add `logTask` ref and `onViewLogs` handler in `KanbanBoard.vue`
- [x] 5.2 Listen for `view-logs` event on TaskCard in the running column, calling `onViewLogs`
- [x] 5.3 Render `TaskLogModal` conditionally when `logTask` is set, passing task id and title

## 6. Tests

- [x] 6.1 Backend test: `ws_task_logs` rejects missing/invalid/expired tokens (close code 4001)
- [x] 6.2 Backend test: `ws_task_logs` returns `task_log_end` for non-running task
- [x] 6.3 Backend test: `ws_task_logs` returns 4004 for non-existent task
- [x] 6.4 Backend test: `ws_task_logs` forwards Valkey messages and closes on `task_log_end`
- [x] 6.5 Frontend test: TaskCard shows log button only when status is `running`
- [x] 6.6 Frontend test: TaskCard emits `view-logs` on log button click
- [x] 6.7 Frontend test: TaskLogModal connects WebSocket on mount and disconnects on unmount
- [x] 6.8 Frontend test: TaskLogModal appends log lines and shows end indicator
