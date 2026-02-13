## Why

Currently, Keycloak defines three roles (viewer, editor, admin) in the JWT token, but the application only enforces admin access on the Settings page. All other authenticated users have full create/edit/delete access regardless of role. Additionally, when a task is deleted, it is permanently removed from the database with no audit trail. There is also no lifecycle progression for completed tasks — they accumulate in the Completed column indefinitely.

## What Changes

- **Role-based access controls**: Enforce viewer (read-only) and editor (create/edit/delete) role restrictions throughout frontend and backend
- **New task states**: Add `deleted` and `archived` states, hidden from the kanban board
- **Soft delete**: `DELETE /api/tasks/{id}` moves tasks to `deleted` status instead of removing from the database — all metadata, output, and logs persist for audit
- **Auto-archive**: Scheduler automatically moves completed tasks to `archived` status after a configurable interval (default 3 days)
- **Archived Tasks page**: New page showing archived tasks (all roles) and deleted tasks (admin only), in chronological order
- **Running task protection**: Edit modal is read-only for tasks in the running state; backend rejects PATCH on running tasks
- **Viewer restrictions**: No task creation, editing, dragging, or delete buttons for viewer-role users
- **Delete button hidden on Running column**: For all users, not just viewers

## Capabilities

### New Capabilities

- `archived-tasks-page`: New page listing archived and deleted tasks with role-based filtering and chronological ordering

### Modified Capabilities

- `frontend-auth`: Add `isEditor` and `isViewer` computed properties to auth store
- `task-api`: Soft delete, exclude hidden statuses from task list, new archived endpoint, editor role enforcement on write endpoints, running task PATCH guard
- `kanban-frontend`: Hide delete button on Running column and for viewers, hide create form for viewers
- `admin-settings-ui`: Add "Archive after" setting, add "Archived Tasks" navigation link to header dropdown
- `task-scheduler`: Auto-archive completed tasks older than configured interval
- `task-edit-modal`: Read-only mode for running tasks and viewer users
- `task-drag-drop`: Disable drag-and-drop for viewer users

## Impact

- `backend/main.py`: New `require_editor` dependency, soft delete, filtered task list, archived endpoint, running task PATCH guard
- `backend/main.py` (scheduler): Auto-archive logic in scheduler loop
- `frontend/src/stores/auth.ts`: `isEditor`, `isViewer` computed properties
- `frontend/src/pages/KanbanBoard.vue` (or equivalent): Conditional UI based on role
- `frontend/src/pages/ArchivedTasksPage.vue`: New page component
- `frontend/src/router/`: New `/archived` route
- `frontend/src/components/TaskEditModal.vue` (or equivalent): Read-only mode
- No database migration needed — status is a text field, archive_after uses existing settings table
