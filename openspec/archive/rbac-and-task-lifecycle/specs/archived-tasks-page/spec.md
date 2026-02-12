## ADDED Requirements

### Requirement: Archived Tasks page

The frontend SHALL provide an "Archived Tasks" page at the `/archived` route. The page SHALL be accessible to all authenticated users (viewer, editor, admin). The page SHALL fetch tasks from `GET /api/tasks/archived` and display them in a chronological list ordered by most recent first. Each list entry SHALL display the task title, status badge ("Archived" or "Deleted"), tags, and the `updated_at` timestamp formatted as a human-readable date/time.

#### Scenario: Page displays archived tasks
- **WHEN** an editor navigates to `/archived` and archived tasks exist
- **THEN** the page displays a list of archived tasks with title, "Archived" badge, tags, and timestamp

#### Scenario: Admin sees deleted and archived tasks
- **WHEN** an admin navigates to `/archived`
- **THEN** the page displays both deleted tasks (with "Deleted" badge) and archived tasks (with "Archived" badge)

#### Scenario: Non-admin sees only archived tasks
- **WHEN** a viewer navigates to `/archived`
- **THEN** the page displays only archived tasks (deleted tasks are not shown)

#### Scenario: Empty state
- **WHEN** a user navigates to `/archived` and no archived tasks exist
- **THEN** the page displays a message "No archived tasks"

### Requirement: Archived Tasks page layout

The Archived Tasks page SHALL display a heading "Archived Tasks" and a table or list with columns: Title, Status, Tags, and Date. The page SHALL follow the same visual styling as the rest of the application (Tailwind CSS). The list SHALL be scrollable if there are many entries.

#### Scenario: Page renders with heading
- **WHEN** the user navigates to `/archived`
- **THEN** the page displays the heading "Archived Tasks"

#### Scenario: Tasks displayed in table format
- **WHEN** archived tasks exist
- **THEN** each task is displayed in a row with its title, status badge, tag pills, and formatted date

### Requirement: Archived Tasks page click to view

Clicking on a task row in the archived tasks list SHALL open the task edit modal in read-only mode, allowing the user to view the full task details including description, output, and runner logs.

#### Scenario: Click archived task opens read-only modal
- **WHEN** the user clicks on an archived task row
- **THEN** the task edit modal opens in read-only mode showing all task details

#### Scenario: Click deleted task opens read-only modal (admin)
- **WHEN** an admin clicks on a deleted task row
- **THEN** the task edit modal opens in read-only mode showing all task details

### Requirement: Archived Tasks route accessible to all roles

The `/archived` route SHALL have a navigation guard that checks `isAuthenticated` from the auth store. If the user is not authenticated, the guard SHALL redirect to `/auth/login`. No role check is needed — all authenticated users can access the page.

#### Scenario: Authenticated viewer accesses archived page
- **WHEN** an authenticated viewer navigates to `/archived`
- **THEN** the Archived Tasks page is rendered

#### Scenario: Unauthenticated user navigates to archived page
- **WHEN** an unauthenticated user navigates to `/archived`
- **THEN** the user is redirected to `/auth/login`
