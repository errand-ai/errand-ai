## 1. Backend: Remove `new` status

- [x] 1.1 Remove `"new"` from `VALID_STATUSES` in `backend/main.py`
- [x] 1.2 Update task creation auto-routing: change "Needs Info" tasks from staying in `new` to being set to `review`
- [x] 1.3 Remove auto-promotion logic from PATCH endpoint (the `new` + "Needs Info" + description + scheduling → `scheduled` code path)
- [x] 1.4 Update the `GET /api/tasks` active status filter to exclude `new` (remove from the active statuses list)

## 2. Database Migration

- [x] 2.1 Create Alembic migration to `UPDATE tasks SET status = 'review' WHERE status = 'new'`

## 3. Backend Tests

- [x] 3.1 Update task creation tests: verify "Needs Info" tasks get `status = 'review'` instead of `new`
- [x] 3.2 Remove auto-promotion tests (test_task_promoted_from_new_to_scheduled and similar)
- [x] 3.3 Update any tests that create tasks with `status = 'new'` to use `review` or another valid status
- [x] 3.4 Add test verifying `status = 'new'` is rejected by PATCH validation

## 4. Frontend: Update Kanban columns

- [x] 4.1 Remove the `new` column entry from the `columns` array in `KanbanBoard.vue`
- [x] 4.2 Move `review` to be the first entry in the `columns` array (leftmost column)
- [x] 4.3 Update `REORDERABLE_COLUMNS` from `['new', 'pending']` to `['review', 'pending']`
- [x] 4.4 Update skeleton loading to render 5 columns instead of 6

## 5. Frontend Tests

- [x] 5.1 Update `KanbanBoard` tests that reference the "New" column
- [x] 5.2 Update `TaskCard` tests that use `columnStatus: 'new'` to use `'review'` (no changes needed — no references found)
- [x] 5.3 Update drag-and-drop tests referencing "New" column scenarios
