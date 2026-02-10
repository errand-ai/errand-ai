## MODIFIED Requirements

### Requirement: Kanban board displays task columns
The frontend SHALL render a Kanban board with six columns representing task statuses, displayed left to right: New, Scheduled, Pending, Running, Review, Completed. Each column SHALL display task cards belonging to that status. The board SHALL use a 6-column grid layout with horizontal scrolling on smaller viewports.

#### Scenario: Board loads with tasks
- **WHEN** the user navigates to the application root
- **THEN** the frontend fetches tasks from `GET /api/tasks` and displays them in the appropriate status columns in order: New, Scheduled, Pending, Running, Review, Completed

#### Scenario: Board shows empty state
- **WHEN** there are no tasks in the system
- **THEN** each of the six columns renders empty with a placeholder message

#### Scenario: Board scrolls horizontally on small screens
- **WHEN** the viewport width is too narrow to display all six columns
- **THEN** the board allows horizontal scrolling to access all columns

### Requirement: Task cards display summary information
Each task card SHALL display the task title and any associated tags. Tags SHALL be displayed as small pills/badges below the title. Cards SHALL NOT display the task status text. Cards SHALL have an edit button. Cards SHALL have `draggable="true"` to support drag-and-drop interaction.

#### Scenario: Task card with title and tags
- **WHEN** a task exists with title "Fix auth bug" and tags "urgent" and "bug"
- **THEN** the card shows the title and two tag pills labeled "urgent" and "bug"

#### Scenario: Task card with no tags
- **WHEN** a task exists with title "Process report" and no tags
- **THEN** the card shows only the title and edit button, with no tag pills

### Requirement: User can create a new task
The frontend SHALL provide a UI control to create a new task by entering text. The input placeholder SHALL be "New task...". The task SHALL be created via `POST /api/tasks` and appear in the New column.

#### Scenario: Successful task creation
- **WHEN** the user enters task text and submits
- **THEN** the frontend sends a POST request and the new task appears in the New column

#### Scenario: Empty input rejected
- **WHEN** the user submits with an empty input
- **THEN** the frontend displays a validation error without sending a request

## REMOVED Requirements

### Requirement: Need Input column
**Reason**: The "Need Input" column is replaced by the tagging system. Tasks that need additional information are now tagged with "Needs Info" instead of being placed in a dedicated column.
**Migration**: Existing tasks with `need-input` status are migrated to `new` status with a "Needs Info" tag via Alembic migration.
