## Context

The frontend currently has two separate paths for viewing task runner logs:

1. **Running tasks**: `TaskLogModal` — full-height (70vh) modal with dark theme, WebSocket streaming, auto-scroll, and the `TaskEventLog` renderer. Accessed via a terminal icon on the task card.
2. **Completed tasks**: `TaskEditModal` — logs embedded as a `max-h-96` section at the bottom of the edit form, using the same `TaskEventLog` renderer but parsing static JSONL from `task.runner_logs`. Accessed by opening the edit modal.

Both paths use the same `TaskEventLog` component to render events, but the completed-task path is buried inside a form and constrained to a small viewport area. The `TaskOutputModal` is a third, unrelated component that renders `task.output` (the markdown final result) — it is not affected by this change.

## Goals / Non-Goals

**Goals:**
- Unify log viewing into `TaskLogModal` for both live and static logs
- Show a consistent logs icon on task cards for any task that has viewable logs (running or completed with `runner_logs`)
- Remove log rendering from the edit modal to simplify it
- Preserve the existing `TaskOutputModal` for viewing `task.output`

**Non-Goals:**
- Changing the `TaskOutputModal` or the `task.output` viewing flow
- Modifying the backend, WebSocket endpoint, or data model
- Adding log persistence for tasks that don't already have `runner_logs`
- Changing the `TaskEventLog` renderer itself

## Decisions

### 1. Dual-mode `TaskLogModal` via optional `runnerLogs` prop

**Decision**: Add an optional `runnerLogs: string` prop to `TaskLogModal`. When provided, the modal parses the JSONL string into events and renders them statically (no WebSocket). When absent, it connects via WebSocket as today.

**Rationale**: This keeps a single modal component with two code paths rather than creating a wrapper or a new component. The parsing logic already exists in `TaskEditModal.parseRunnerLogs()` — it moves into the modal. The `taskId` prop becomes optional (required only for live mode).

**Alternatives considered**:
- *New `StaticLogModal` component*: Rejected — duplicates the modal shell, header, dark-theme container, and scroll logic. The two modes share 90% of the UI.
- *Wrapper component that selects between modals*: Rejected — adds indirection without benefit when the modes differ only in data source.

### 2. Adjust props: `taskId` optional, `runnerLogs` optional, at least one required

**Decision**: Change `TaskLogModal` props to:
```ts
defineProps<{
  taskId?: string
  title: string
  runnerLogs?: string
}>()
```

At mount time: if `runnerLogs` is provided, parse and render statically; otherwise, connect WebSocket using `taskId`. A runtime warning is logged if neither is provided.

**Rationale**: Clean separation of modes without a discriminated-union prop pattern that Vue `defineProps` doesn't support well. The `KanbanBoard` already knows which mode to use based on task status.

### 3. Reuse the same task card icon (terminal/code icon) for both modes

**Decision**: The task card shows the existing terminal-style icon (currently used for running tasks) for all tasks with viewable logs: `running` status OR `(review|completed|scheduled) && runner_logs`. Both emit `view-logs`. Remove the separate eye-icon "view output" button that was used for `runner_logs` access.

**Rationale**: One icon, one action, one modal. The eye icon for `task.output` viewing is handled separately by `showOutputButton` and `TaskOutputModal` — that flow is unchanged.

**Note**: The `showOutputButton` computed and `view-output` emit remain for tasks that have `task.output` (the markdown final result). The change only removes the eye icon's role as a runner-logs viewer — which it wasn't doing anyway; the eye icon currently shows `TaskOutputModal` (markdown output), not runner logs. The runner logs were only accessible via the edit modal. So the actual change is: add the terminal icon for completed tasks with `runner_logs`.

### 4. Header text adapts to mode

**Decision**: The modal header shows "Live Logs: {title}" for WebSocket mode and "Task Logs: {title}" for static mode.

**Rationale**: Communicates whether logs are streaming or historical. Minimal UI change.

### 5. Extract `parseRunnerLogs` to a shared utility

**Decision**: Move the JSONL parsing logic from `TaskEditModal` into a shared function (in `TaskLogModal` or a small composable) since `TaskEditModal` will no longer need it.

**Rationale**: The function moves from `TaskEditModal` to `TaskLogModal` — it doesn't need a separate utility file since only one component uses it after this change.

## Risks / Trade-offs

- **Minor prop API change**: `TaskLogModal.taskId` becomes optional. Since the component is only instantiated by `KanbanBoard`, the blast radius is one file. → Mitigation: TypeScript will catch misuse at compile time.
- **Static logs lose the "Task finished" indicator**: The green dot indicator is only meaningful for live streams. For static logs, the indicator is omitted since the task is already completed. → Acceptable: the modal header ("Task Logs" vs "Live Logs") communicates the mode.
- **Edit modal loses a read path for logs**: Users who previously opened the edit modal to read logs must now use the card icon instead. → This is the intended UX improvement — the edit modal returns to its core purpose.
