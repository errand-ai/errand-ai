## MODIFIED Requirements

### Requirement: Create a task
The backend SHALL expose `POST /api/tasks` accepting a JSON body with a `title` field. The task SHALL be created with status `new`. After successful creation, the backend SHALL publish a `task_created` event to the Valkey pub/sub channel containing the full task object.

#### Scenario: Successful creation
- **WHEN** a client sends `POST /api/tasks` with `{"title": "Run analysis"}`
- **THEN** the backend returns HTTP 201 with the created task object including a generated `id` and status `new`

#### Scenario: Event published after creation
- **WHEN** a task is successfully created
- **THEN** the backend publishes a `task_created` event to the Valkey `task_events` channel with the serialized task object

#### Scenario: Missing title
- **WHEN** a client sends `POST /api/tasks` with an empty or missing `title`
- **THEN** the backend returns HTTP 422 with a validation error and no event is published

### Requirement: Update a task
The backend SHALL expose `PATCH /api/tasks/{id}` accepting a JSON body with optional `title` and `status` fields. The endpoint SHALL update only the provided fields and return the updated task object. After successful update, the backend SHALL publish a `task_updated` event to the Valkey pub/sub channel containing the full updated task object.

#### Scenario: Update task status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "scheduled"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing status `scheduled` and an updated `updated_at` timestamp

#### Scenario: Event published after update
- **WHEN** a task is successfully updated
- **THEN** the backend publishes a `task_updated` event to the Valkey `task_events` channel with the serialized updated task object

#### Scenario: Update task title
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": "New title"}`
- **THEN** the backend returns HTTP 200 with the updated task object showing the new title

#### Scenario: Update both title and status
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": "New title", "status": "review"}`
- **THEN** the backend returns HTTP 200 with the updated task object reflecting both changes

#### Scenario: Task not found
- **WHEN** a client sends `PATCH /api/tasks/999` and task 999 does not exist
- **THEN** the backend returns HTTP 404 and no event is published

#### Scenario: Invalid status value
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"status": "invalid"}`
- **THEN** the backend returns HTTP 422 with a validation error listing the valid statuses and no event is published

#### Scenario: Empty title rejected
- **WHEN** a client sends `PATCH /api/tasks/{id}` with `{"title": ""}`
- **THEN** the backend returns HTTP 422 with a validation error and no event is published
