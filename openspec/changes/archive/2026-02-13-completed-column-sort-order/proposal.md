## Why

The completed column currently sorts tasks by position (same as active columns), which places older tasks at the top. Users expect to see their most recently completed work first so they can quickly review outcomes and track recent progress.

## What Changes

- Change the sort order for the completed column so tasks are listed by most recently completed first (descending `updated_at`)
- Active columns (new, scheduled, pending, running, review) retain their current position-based ordering

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `task-ordering`: Add requirement that the completed column sorts by `updated_at` descending instead of position

## Impact

- Backend: `GET /api/tasks` query needs column-aware sort logic (completed uses `updated_at desc`, others use `position asc`)
- Frontend: No changes expected — the frontend renders tasks in the order received from the API
