## 1. Backend role enforcement

- [x] 1.1 Add `require_editor` dependency in `main.py` that accepts users with `editor` or `admin` role (pattern matches existing `require_admin`)
- [x] 1.2 Apply `require_editor` to `POST /api/tasks` (create_task), `PATCH /api/tasks/{id}` (update_task), and `DELETE /api/tasks/{id}` (delete_task) — replacing `get_current_user` on these endpoints
- [x] 1.3 Add running task PATCH guard: in `update_task`, before applying field updates, check if the task's current status is `"running"` and return HTTP 409 with `{"detail": "Cannot edit a running task"}`

## 2. Soft delete and hidden statuses

- [x] 2.1 Add `"deleted"` and `"archived"` to the `VALID_STATUSES` constant in `main.py`
- [x] 2.2 Change `delete_task` to set `task.status = "deleted"` instead of deleting the row — remove the `task_tags` delete and `session.delete(task)` calls, add `task.status = "deleted"`, commit, and emit `task_deleted` event
- [x] 2.3 Filter `list_tasks` to exclude hidden statuses: add `.where(Task.status.not_in(["deleted", "archived"]))` to the select query

## 3. Archived tasks API

- [x] 3.1 Add `GET /api/tasks/archived` endpoint using `get_current_user` dependency — extract roles from claims, query tasks with `status IN ('deleted', 'archived')` for admin or `status = 'archived'` for non-admin, order by `updated_at` descending
- [x] 3.2 Return `list[TaskResponse]` with tags eagerly loaded (same pattern as `list_tasks`)

## 4. Auto-archive in scheduler

- [x] 4.1 In the scheduler loop (after promoting scheduled tasks), read the `archive_after_days` setting from the settings table (default 3 if not set)
- [x] 4.2 Query for tasks with `status = 'completed'` and `updated_at < now() - archive_after_days`, update their status to `'archived'`, and emit `task_updated` WebSocket events for each

## 5. Frontend auth store

- [x] 5.1 Add `isEditor` computed property to `useAuthStore`: returns `true` if `roles` includes `"editor"` or `"admin"`
- [x] 5.2 Add `isViewer` computed property to `useAuthStore`: returns `true` if `isAuthenticated` is true and `isEditor` is false

## 6. Kanban board viewer restrictions

- [x] 6.1 Hide the task creation form (input + "Add Task" button) when `isViewer` is true
- [x] 6.2 Hide the delete icon on task cards when `isViewer` is true
- [x] 6.3 Hide the delete icon on task cards in the Running column for all users
- [x] 6.4 Set `draggable` to `false` on task cards when `isViewer` is true; disable drop target highlighting for viewers

## 7. Edit modal restrictions

- [x] 7.1 Add read-only mode to the edit modal: when active, disable all form inputs and hide Save/Delete buttons (keep Close/Cancel visible)
- [x] 7.2 Activate read-only mode when the task's status is `"running"`
- [x] 7.3 Activate read-only mode when `isViewer` is true (regardless of task status)

## 8. Settings page: Archive after

- [x] 8.1 Add a "Task Archiving" section to the Settings page with a number input labelled "Archive after (days)", loading from `archive_after_days` setting (default 3), with a Save button that sends `PUT /api/settings` with `{"archive_after_days": <number>}`

## 9. Archived Tasks page

- [x] 9.1 Create `ArchivedTasksPage.vue` component: heading "Archived Tasks", fetches from `GET /api/tasks/archived`, displays tasks in a table with columns Title, Status (badge), Tags (pills), Date (`updated_at` formatted)
- [x] 9.2 Add `/archived` route in the router with an auth guard (redirect to login if not authenticated, no role restriction)
- [x] 9.3 Add "Archived Tasks" link to the header user dropdown, visible to all authenticated users, positioned above the Settings link
- [x] 9.4 Clicking a task row opens the edit modal in read-only mode showing full task details

## 10. Backend tests

- [x] 10.1 Test `require_editor`: editor allowed, admin allowed, viewer denied (403), unauthenticated denied (401)
- [x] 10.2 Test soft delete: task status changes to "deleted", row persists, tag associations persist, returns 204
- [x] 10.3 Test `list_tasks` excludes deleted and archived tasks
- [x] 10.4 Test archived endpoint: admin sees both deleted and archived, non-admin sees only archived
- [x] 10.5 Test running task PATCH guard: returns 409 for running task, allows PATCH for non-running task
- [x] 10.6 Test scheduler auto-archive: completed task older than interval is archived, recent completed task is not

## 11. Frontend tests

- [x] 11.1 Test `isEditor` and `isViewer` computed properties in auth store
- [x] 11.2 Test viewer cannot see delete button, create form, or drag tasks
- [x] 11.3 Test edit modal read-only for running tasks and viewer users
- [x] 11.4 Test archived tasks page renders and displays tasks

## 12. Version bump and verification

- [x] 12.1 Bump VERSION file (minor increment)
- [x] 12.2 Run full backend and frontend test suites and verify all tests pass
