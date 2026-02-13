## Context

The application has Keycloak OIDC authentication with three roles (viewer, editor, admin), but only enforces admin access on the Settings page via `require_admin`. The `get_current_user` dependency validates the JWT but does not check roles — all authenticated users can create, edit, drag, and delete tasks. The task model uses a text status field with values: new, scheduled, pending, running, review, completed. The `delete_task` endpoint permanently removes tasks (and their tag associations) from the database. The scheduler loop promotes scheduled tasks to pending using a Valkey distributed lock.

## Goals / Non-Goals

**Goals:**
- Enforce viewer (read-only) and editor (read-write) role restrictions on both frontend and backend
- Add `deleted` and `archived` hidden task states
- Convert hard delete to soft delete (status change preserving all data)
- Auto-archive completed tasks via the existing scheduler loop
- New Archived Tasks page for viewing hidden tasks with role-based filtering
- Protect running tasks from manual editing

**Non-Goals:**
- Changing Keycloak role definitions or adding new roles
- Adding a role management UI
- Archiving tasks in states other than completed
- Undo/restore functionality for deleted or archived tasks
- Fine-grained per-task or per-field permissions

## Decisions

### Decision: Add `require_editor` backend dependency

Create a `require_editor` dependency that accepts users with either the `editor` or `admin` role. Apply it to `POST /api/tasks`, `PATCH /api/tasks/{id}`, and `DELETE /api/tasks/{id}`. Keep `get_current_user` (any authenticated user) for `GET` endpoints.

**Rationale:** Admin is a superset of editor. A single dependency for write operations keeps the access model simple. GET endpoints remain accessible to viewers.

### Decision: Soft delete via status change

Change `DELETE /api/tasks/{id}` to set `status = 'deleted'` instead of removing the row. Keep the existing `task_deleted` WebSocket event so the kanban board removes the card. Do not delete the `task_tags` associations — they persist with the task.

**Rationale:** Preserves all task data, metadata, tags, output, and logs for audit purposes. Minimal change to the existing API contract — the endpoint still returns 204 and the kanban board still removes the card.

### Decision: Filter hidden statuses from `GET /api/tasks`

Add `WHERE status NOT IN ('deleted', 'archived')` to `list_tasks`. The kanban board only receives active tasks.

**Rationale:** The kanban board should only show active workflow states. Hidden tasks are accessible via the new archived endpoint.

### Decision: Separate archived endpoint with role-based filtering

Add `GET /api/tasks/archived` that returns tasks with `status IN ('deleted', 'archived')`. For non-admin users, filter to only `archived` status. For admin users, return both. Order by `updated_at` descending.

**Rationale:** Single endpoint with role-based filtering is simpler than separate endpoints. The admin check reuses the existing role extraction from JWT claims.

### Decision: Auto-archive in existing scheduler loop

Add auto-archive logic to the existing scheduler loop. After promoting scheduled tasks, query for tasks where `status = 'completed'` and `updated_at` is older than the `archive_after_days` setting (default 3). Update their status to `archived` and emit `task_updated` WebSocket events.

**Rationale:** Reuses existing scheduler infrastructure (Valkey lock, error handling, background task). The kanban board should ignore `task_updated` events for tasks with hidden statuses, or simply not find them in its local state.

### Decision: Frontend role checks via auth store computed properties

Add `isEditor` (roles includes "editor" or "admin") and `isViewer` (authenticated but neither editor nor admin) computed properties to the auth store. Use these in components for conditional rendering.

**Rationale:** Centralized role logic in the auth store, consistent with the existing `isAdmin` pattern.

### Decision: Running task protection on both frontend and backend

Frontend: edit modal displays all fields as read-only when task status is "running", with action buttons hidden. Backend: PATCH endpoint returns 409 Conflict if the task's current status is "running".

**Rationale:** Defence in depth — frontend provides the UX, backend enforces the invariant. The worker uses direct SQL UPDATE (not the PATCH endpoint), so it is unaffected by the backend guard.

### Decision: "Archive after" as integer days setting

Store the auto-archive interval as `archive_after_days` integer setting (default 3). Display as a number input on the Settings page with label "Archive after (days)".

**Rationale:** Simple integer is easier to validate and reason about than arbitrary interval strings. Days granularity is sufficient for archiving completed tasks.

### Decision: No database migration

The status column is a text field — no enum constraint to modify. The `archive_after_days` setting uses the existing settings table. New statuses are just new string values in the application layer.

**Rationale:** Zero migration risk. `VALID_STATUSES` constant in `main.py` is updated to include the new values.

## Risks / Trade-offs

- **[Soft delete data growth]** → Tasks accumulate forever in the database. Acceptable for now; a future cleanup/purge feature can be added if needed.
- **[Running task PATCH rejection]** → The worker uses direct SQL UPDATE, not the PATCH endpoint, so it is unaffected. Third-party API callers attempting PATCH on a running task will receive 409.
- **[WebSocket events on auto-archive]** → The scheduler emits `task_updated` for archived tasks. The kanban board should either ignore events for hidden statuses or simply not find the task in its local state (both work correctly since the board doesn't display hidden tasks).
- **[Viewer role detection]** → A user with no roles at all is different from a "viewer" — they get 403 from `get_current_user`. The `isViewer` check specifically means the user is authenticated with roles but lacks editor/admin.
