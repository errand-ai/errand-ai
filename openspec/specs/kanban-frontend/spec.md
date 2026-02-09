## Requirements

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
The frontend SHALL connect to the backend WebSocket endpoint (`/api/ws/tasks`) to receive real-time task events. When a WebSocket event is received, the frontend SHALL update its local task store immediately without a full reload. The frontend SHALL fall back to polling `GET /api/tasks` at a regular interval if the WebSocket connection is unavailable.

#### Scenario: Task moves columns via WebSocket event
- **WHEN** a `task_updated` event is received with a new status
- **THEN** the task card moves to the appropriate column immediately without waiting for a poll cycle

#### Scenario: New task appears via WebSocket event
- **WHEN** a `task_created` event is received
- **THEN** the new task card appears in the New column immediately

#### Scenario: WebSocket connection established on load
- **WHEN** the user navigates to the application root and is authenticated
- **THEN** the frontend opens a WebSocket connection to `/api/ws/tasks` with the JWT token

#### Scenario: Fallback to polling on WebSocket failure
- **WHEN** the WebSocket connection cannot be established or is lost
- **THEN** the frontend falls back to polling `GET /api/tasks` every 5 seconds

#### Scenario: WebSocket reconnection with backoff
- **WHEN** the WebSocket connection is lost
- **THEN** the frontend attempts to reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)

#### Scenario: Polling stops when WebSocket reconnects
- **WHEN** the WebSocket connection is re-established after a fallback to polling
- **THEN** the frontend stops polling and resumes receiving events via WebSocket

#### Scenario: Task movement is animated
- **WHEN** a task card moves between columns after a WebSocket event
- **THEN** the card animates out of the source column and into the destination column using Vue's TransitionGroup

### Requirement: Frontend is served as static assets
The frontend SHALL be built as static files and served by an nginx container. The nginx configuration SHALL proxy `/api/*` and `/auth/*` requests to the backend service.

#### Scenario: Static assets served
- **WHEN** a browser requests the application root
- **THEN** nginx serves the built Vue application

#### Scenario: API requests proxied
- **WHEN** the frontend makes a request to `/api/tasks`
- **THEN** nginx proxies the request to the backend service

#### Scenario: Auth requests proxied
- **WHEN** the browser requests `/auth/login`
- **THEN** nginx proxies the request to the backend service

### Requirement: Display current user identity
The frontend SHALL display the authenticated user's name or email in the app header, derived from the access token claims.

#### Scenario: User identity shown
- **WHEN** a user is authenticated
- **THEN** the app header displays the user's name or email from the token

### Requirement: Logout button in header
The frontend SHALL display a logout button in the app header that triggers the logout action (redirect to `/auth/logout`).

#### Scenario: User clicks logout
- **WHEN** the user clicks the logout button
- **THEN** the browser navigates to `/auth/logout`

### Requirement: App is inaccessible without authentication
The Kanban board SHALL NOT render until the user is authenticated. Unauthenticated users SHALL be redirected to `/auth/login`.

#### Scenario: Unauthenticated user
- **WHEN** an unauthenticated user navigates to the app root
- **THEN** they are redirected to `/auth/login` before seeing any task data
