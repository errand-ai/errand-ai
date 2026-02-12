## Why

Archived tasks that were processed by the task runner have execution output, but the only way to view it is by clicking the row to open the full edit modal (in read-only mode) and scrolling to the runner logs section. A dedicated "View Output" button on each row would give quick access to the output without opening the full modal.

## What Changes

- Add a "View Output" button to each row in the archived tasks table
- Clicking the button opens the existing `TaskOutputModal` with the task's output
- The button only appears for tasks that have output (non-null, non-empty)
- Clicking the button does not trigger the row click (which opens the edit modal)

## Capabilities

### New Capabilities

_(none — this uses the existing `TaskOutputModal` component)_

### Modified Capabilities

- `archived-tasks-page`: Add a "View Output" button column to the archived tasks table that opens the `TaskOutputModal`

## Impact

- `frontend/src/pages/ArchivedTasksPage.vue` — add output button column, import `TaskOutputModal`, add state/handler
- No backend changes — the archived tasks API already returns the `output` field
- No new components — reuses existing `TaskOutputModal`
