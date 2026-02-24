## Why

Completed task runner logs are currently embedded inside the edit modal, which is a poor UX fit — the edit modal is for editing task details, not reviewing execution logs. Meanwhile, the live logs modal (`TaskLogModal`) already provides a purpose-built, full-height viewer with auto-scroll, dark theme, and the `TaskEventLog` renderer. Unifying these into one modal reduces code duplication, gives completed logs the same rich viewing experience as live logs, and makes the log-access pattern consistent: same icon, same modal, regardless of task state.

## What Changes

- **Reuse `TaskLogModal` for completed task logs**: When a completed/review task has `runner_logs`, open the same `TaskLogModal` modal instead of showing logs inline in the edit modal. The modal will detect whether to connect a WebSocket (running task) or render static JSONL logs (completed task).
- **Unify the task card icon**: Show the same logs icon for both running tasks (live streaming) and completed/review tasks with `runner_logs`. Remove the separate "view output" eye icon for runner logs — the `TaskOutputModal` remains for viewing `task.output` (final markdown result).
- **Remove runner logs section from `TaskEditModal`**: The edit modal will no longer display the "Task Runner Logs" panel. This simplifies the edit modal back to its core purpose: editing task metadata.
- **Static log rendering in `TaskLogModal`**: Add a mode where `TaskLogModal` accepts pre-recorded `runner_logs` (JSONL string) instead of a WebSocket task ID, parses them into events, and renders them with `TaskEventLog` — same display, no WebSocket connection.

## Capabilities

### New Capabilities

_(none — this change modifies existing capabilities)_

### Modified Capabilities

- `live-task-log-streaming`: The `TaskLogModal` component gains a static-logs mode that accepts a `runner_logs` string prop, parses JSONL into events, and renders them without a WebSocket connection. The header adjusts to show "Task Logs" instead of "Live Logs" when viewing static logs.
- `task-edit-modal`: Remove the runner logs section (`TaskEventLog` panel and "Task Runner Logs" heading) from the edit modal. The modal no longer renders logs for any task status.
- `kanban-frontend`: The task card shows the logs icon for completed/review tasks that have `runner_logs`, in addition to running tasks. The `KanbanBoard` routes the log-view action to `TaskLogModal` with the appropriate props (task ID for running, runner_logs string for completed).

## Impact

- **Frontend components**: `TaskLogModal.vue`, `TaskEditModal.vue`, `TaskCard.vue`, `KanbanBoard.vue`
- **No backend changes**: All data (`runner_logs`, WebSocket endpoint) already exists
- **No API changes**: No new endpoints or data model changes
- **Spec updates**: Delta specs for `live-task-log-streaming`, `task-edit-modal`, `kanban-frontend`
- **`TaskOutputModal`**: Unchanged — still used for viewing `task.output` (final markdown result), which is a separate concern from runner logs
