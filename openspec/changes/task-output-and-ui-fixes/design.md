## Context

The worker publishes `task_updated` WebSocket events using `_task_to_dict()`, which only serialises a subset of task fields. The frontend replaces the entire task object on receiving an update, so any missing fields become `undefined`. This causes the description to disappear when a task moves to running.

Additionally, there is no way to view task execution output in the UI. Tasks in review/completed still show the scheduling `execute_at` time in the edit modal rather than when processing completed.

## Goals / Non-Goals

**Goals:**
- Fix `_task_to_dict()` to include all fields matching `TaskResponse`, preventing data loss on WebSocket updates
- Show `updated_at` as "Completed at" in the edit modal for review/completed tasks
- Add an output viewer popup accessible from task cards in review, completed, and scheduled columns
- Keep all changes minimal — no refactoring beyond what's needed

**Non-Goals:**
- Changing the WebSocket update strategy (e.g. merging partial updates) — fixing the payload is simpler
- Adding output editing — the viewer is read-only
- Implementing a scheduler for retry logic — that's a separate change

## Decisions

### Decision 1: Fix payload rather than merge strategy
**Choice:** Make `_task_to_dict()` return all fields matching `TaskResponse.from_task()`.
**Alternative:** Change the frontend to merge partial updates instead of replacing. Rejected because the worker should emit complete events — partial updates are fragile and would require changes across all event consumers.

### Decision 2: Separate output viewer popup (not inline in edit modal)
**Choice:** New `TaskOutputModal` component triggered by a button on the task card.
**Alternative:** Add an output section inside `TaskEditModal`. Rejected because the output can be large (up to 1MB) and mixing it with editable fields clutters the modal. A dedicated read-only viewer is cleaner.

### Decision 3: Use `updated_at` as completion time
**Choice:** For tasks in review/completed status, display `updated_at` with label "Completed at" instead of the `execute_at` field in the edit modal.
**Alternative:** Add a separate `completed_at` column. Rejected because `updated_at` already captures when the worker last updated the task (which is when it completed processing), and adding a new column would require a migration for no additional value.

## Risks / Trade-offs

- **Risk:** `_task_to_dict()` now needs to load task tags (a relationship). → Mitigation: Use `selectinload` or access `task.tags` after the session refresh to ensure tags are loaded.
- **Risk:** Large output in the viewer popup may cause rendering issues. → Mitigation: Use a scrollable `<pre>` block with overflow, matching the existing truncation in the worker (1MB max).
