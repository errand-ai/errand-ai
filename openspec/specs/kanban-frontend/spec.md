## ADDED Requirements

### Requirement: Kanban board displays task columns
The frontend SHALL render a Kanban board with columns representing task statuses: Pending, Running, Completed, and Failed. Each column SHALL display task cards belonging to that status.

#### Scenario: Board loads with tasks
- **WHEN** the user navigates to the application root
- **THEN** the frontend fetches tasks from `GET /api/tasks` and displays them in the appropriate status columns

#### Scenario: Board shows empty state
- **WHEN** there are no tasks in the system
- **THEN** each column renders empty with a placeholder message

### Requirement: Task cards display summary information
Each task card SHALL display the task title and current status. Cards SHALL be visually distinct per column.

#### Scenario: Task card content
- **WHEN** a task exists with title "Process report" and status "running"
- **THEN** the card appears in the Running column showing the task title

### Requirement: User can create a new task
The frontend SHALL provide a UI control to create a new task by specifying a title. The task SHALL be created via `POST /api/tasks` and appear in the Pending column.

#### Scenario: Successful task creation
- **WHEN** the user enters a task title and submits
- **THEN** the frontend sends a POST request and the new task appears in the Pending column

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

### Requirement: Frontend is served as static assets
The frontend SHALL be built as static files and served by an nginx container. The nginx configuration SHALL proxy `/api/*` requests to the backend service.

#### Scenario: Static assets served
- **WHEN** a browser requests the application root
- **THEN** nginx serves the built Vue application

#### Scenario: API requests proxied
- **WHEN** the frontend makes a request to `/api/tasks`
- **THEN** nginx proxies the request to the backend service
