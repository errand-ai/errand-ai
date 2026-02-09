## MODIFIED Requirements

### Requirement: Kanban board displays task columns
The frontend SHALL render a Kanban board with seven columns representing task statuses, displayed left to right: New, Need Input, Scheduled, Pending, Running, Review, Completed. Each column SHALL display task cards belonging to that status. The board SHALL use a 7-column grid layout with horizontal scrolling on smaller viewports.

#### Scenario: Board loads with tasks
- **WHEN** the user navigates to the application root
- **THEN** the frontend fetches tasks from `GET /api/tasks` and displays them in the appropriate status columns in order: New, Need Input, Scheduled, Pending, Running, Review, Completed

#### Scenario: Board shows empty state
- **WHEN** there are no tasks in the system
- **THEN** each of the seven columns renders empty with a placeholder message

#### Scenario: Board scrolls horizontally on small screens
- **WHEN** the viewport width is too narrow to display all seven columns
- **THEN** the board allows horizontal scrolling to access all columns

### Requirement: Task cards display summary information
Each task card SHALL display the task title, current status, and an edit button. Cards SHALL be visually distinct per column. Cards SHALL have `draggable="true"` to support drag-and-drop interaction.

#### Scenario: Task card content
- **WHEN** a task exists with title "Process report" and status "running"
- **THEN** the card appears in the Running column showing the task title and an edit button

### Requirement: User can create a new task
The frontend SHALL provide a UI control to create a new task by specifying a title. The task SHALL be created via `POST /api/tasks` and appear in the New column.

#### Scenario: Successful task creation
- **WHEN** the user enters a task title and submits
- **THEN** the frontend sends a POST request and the new task appears in the New column

#### Scenario: Empty title rejected
- **WHEN** the user submits with an empty title
- **THEN** the frontend displays a validation error without sending a request

### Requirement: Board reflects live task state
The frontend SHALL poll `GET /api/tasks` at a regular interval to reflect task state changes made by the backend and workers.

#### Scenario: Task moves columns after worker processes it
- **WHEN** a task transitions from "pending" to "running" on the backend
- **THEN** the task card moves from the Pending column to the Running column on the next poll

#### Scenario: Task movement is animated
- **WHEN** a task card moves between columns after a poll update
- **THEN** the card animates out of the source column and into the destination column using Vue's TransitionGroup
