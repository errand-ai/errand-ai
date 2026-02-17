## Why

The edit task modal currently allows editing completed tasks, which is unnecessary and risks accidental modifications. Additionally, the runner logs in the edit modal are displayed as a plain `<pre>` block, while the live task log viewer (TaskLogModal) renders the same structured events with rich formatting (collapsible tool calls, styled thinking/reasoning blocks, etc.). The edit modal should provide the same rich viewing experience for historical logs.

## What Changes

- When a task has `status = 'completed'`, the edit modal SHALL display all fields as read-only (no editing, no Save/Delete buttons)
- Extract the structured event rendering logic from TaskLogModal into a reusable component
- Replace the plain `<pre>` runner logs block in the edit modal with the rich event renderer
- The rich log renderer SHALL parse `runner_logs` (newline-delimited JSON events) and render them identically to the live view

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-edit-modal`: Add read-only mode for completed tasks; replace plain-text runner logs with rich structured event rendering

## Impact

- **frontend/src/components/TaskEditModal.vue**: Read-only mode for completed status, rich log rendering
- **frontend/src/components/TaskLogModal.vue**: Extract event rendering into a shared component
- **frontend/src/components/**: New shared event renderer component (extracted from TaskLogModal)
