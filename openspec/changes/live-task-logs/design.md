## Context

When a task enters the "running" state, the worker calls `process_task_in_container` in a sync thread executor. This function creates a Docker container, starts it, calls `container.wait()` (blocking until exit), then captures stdout/stderr with `container.logs()`. The captured stderr is stored in the task's `runner_logs` field after execution.

The frontend receives task lifecycle events via a single WebSocket endpoint (`/api/ws/tasks`) backed by Valkey pub/sub on the `task_events` channel. There is currently no mechanism to stream data during task execution — all log output is only available after completion.

The worker runs in a sync thread (via `asyncio.run_in_executor`), while the event system is async. The Docker Python SDK supports streaming logs from a running container via `container.logs(stream=True, follow=True)`.

## Goals / Non-Goals

**Goals:**
- Stream task runner stderr to the frontend in real-time while a task is running
- Provide a UI to view live logs from a running task card
- Maintain backward compatibility — existing post-execution log capture and `runner_logs` storage remain unchanged
- Support multiple simultaneous viewers of the same task's logs

**Non-Goals:**
- Streaming stdout (stdout contains the structured JSON result, not human-readable logs)
- Persisting streamed log history in Valkey (full logs are stored in `runner_logs` after execution)
- Log search, filtering, or log-level highlighting in the viewer (plain text stream is sufficient for v1)
- Buffering historical log lines for late-joining viewers (they see "from now" — full logs available post-completion)

## Decisions

### 1. Sync Redis client in executor thread for publishing

**Decision**: Use a synchronous `redis.Redis` client from within the executor thread to publish log chunks to Valkey, rather than refactoring to an async Docker client.

**Alternatives considered**:
- *aiodocker (async Docker client)*: Would eliminate the executor thread entirely but is a large refactor touching the core task processing loop, with a different API surface and less battle-tested than the official Docker SDK.
- *Shared queue between thread and async loop*: Adds complexity with cross-thread queue coordination and polling intervals.

**Rationale**: The `redis` package (already installed — it provides both `redis.Redis` and `redis.asyncio.Redis`) supports sync publishing. A sync client in the executor thread is the simplest bridge between the blocking Docker SDK and the async Valkey event system. The sync client is created per-task invocation and closed after execution.

### 2. Per-task Valkey pub/sub channel

**Decision**: Use a per-task channel pattern `task_logs:{task_id}` for streaming log lines, separate from the existing `task_events` channel.

**Alternatives considered**:
- *Multiplex on existing `task_events` channel*: Would add noise to all connected clients and require client-side filtering. Every open Kanban board would receive log data for every running task.
- *Valkey Streams (XADD/XREAD)*: Supports replay and consumer groups but adds operational complexity for a feature that doesn't need persistence or replay.

**Rationale**: Per-task channels ensure only clients actively viewing a task's logs receive the data. Valkey automatically garbage-collects channels with no subscribers, so no cleanup is needed.

### 3. Dedicated WebSocket endpoint per task

**Decision**: Add a new WebSocket endpoint at `/api/ws/tasks/{task_id}/logs` rather than extending the existing `/api/ws/tasks` endpoint.

**Alternatives considered**:
- *Extend existing WS with subscribe/unsubscribe messages*: Would add protocol complexity to the existing event stream and mix log data with task lifecycle events.

**Rationale**: A dedicated endpoint keeps concerns separate. The frontend opens this connection only when the log viewer modal is open and closes it when the modal closes. Auth follows the same JWT-in-query-param pattern as the existing endpoint.

### 4. Replace `container.wait()` with streaming `container.logs(follow=True)`

**Decision**: Replace the current `container.start()` → `container.wait()` → `container.logs()` sequence with `container.start()` → iterate `container.logs(stream=True, follow=True, stderr=True, stdout=False)` → then capture final stdout/stderr for parsing.

**Rationale**: `container.logs(follow=True)` blocks until the container exits (like `wait()`), so it naturally replaces the wait call. After the streaming loop completes, we know the container has exited and can get the exit code via `container.wait()` (which returns immediately since the container already exited) and capture the full stdout for JSON parsing. The full stderr is accumulated during streaming for storage in `runner_logs`.

### 5. Log message format

**Decision**: Each Valkey message on `task_logs:{task_id}` is a JSON object: `{"event": "task_log", "line": "<stderr line>"}`. A final `{"event": "task_log_end"}` message is published when streaming completes (container exited).

**Rationale**: JSON wrapping is consistent with the existing `task_events` message format. The `task_log_end` sentinel lets the frontend know streaming is done without relying solely on detecting the task status change via the separate `task_events` WebSocket (which may arrive slightly later due to DB commit timing).

### 6. Frontend: separate modal component with dedicated WebSocket

**Decision**: Create a new `TaskLogModal.vue` component that manages its own WebSocket connection to `/api/ws/tasks/{task_id}/logs`. The connection is opened when the modal mounts and closed when it unmounts.

**Rationale**: Lifecycle is simple — modal open = connected, modal close = disconnected. No need for a global log subscription manager. The component accumulates log lines in a reactive array and auto-scrolls a `<pre>` block.

## Risks / Trade-offs

**[High log volume could stress Valkey pub/sub]** → Mitigation: Task runner stderr is typically low-volume (tens of lines per minute, not thousands). If a task runner produces extremely verbose output, the per-task channel isolates it from other subscribers. Future enhancement: add a rate limiter or line batching if needed.

**[Sync Redis client per task adds a connection]** → Mitigation: The connection is short-lived (duration of one task execution) and only one task runs at a time per worker. Connection pooling is not needed.

**[Late-joining viewers miss earlier log lines]** → Accepted trade-off for v1. Full logs are available in `runner_logs` after task completion. A future enhancement could use a Valkey list as a rolling buffer, but the added complexity isn't justified yet.

**[WebSocket endpoint open while task finishes]** → Mitigation: The `task_log_end` sentinel tells the frontend to stop waiting for more lines. The backend also unsubscribes from the per-task channel when the WebSocket closes. If the task is already finished when the modal opens, the backend can detect this (check task status) and immediately send `task_log_end`.
