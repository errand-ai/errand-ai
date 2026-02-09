## Requirements

### Requirement: Frontend test infrastructure
The frontend SHALL have a Vitest test suite using `@vue/test-utils` and `jsdom`. Tests SHALL mock the API layer (`fetch` or `useApi` composable) to avoid real HTTP requests. The Pinia store SHALL be instantiated fresh for each test using `createTestingPinia` or manual setup.

#### Scenario: Test suite runs without backend
- **WHEN** a developer runs `npm test` in the frontend directory
- **THEN** all tests execute without requiring a running backend or any external service

#### Scenario: Test isolation
- **WHEN** multiple test functions run sequentially
- **THEN** each test starts with a fresh DOM, fresh store state, and fresh mocks

### Requirement: Test kanban board column rendering
The test suite SHALL verify that the KanbanBoard component renders all seven columns with correct labels and task placement.

#### Scenario: Board loads with tasks
- **WHEN** the store contains tasks in various statuses
- **THEN** the component renders seven columns (New, Need Input, Scheduled, Pending, Running, Review, Completed) with tasks placed in the correct columns

#### Scenario: Board shows empty state
- **WHEN** the store contains no tasks
- **THEN** each column renders with a "No tasks" placeholder message

### Requirement: Test task card rendering
The test suite SHALL verify that TaskCard displays task information and supports drag interactions.

#### Scenario: Task card content
- **WHEN** a TaskCard is rendered with a task titled "Process report" and status "running"
- **THEN** the card displays the title "Process report" and an edit button

#### Scenario: Task card is draggable
- **WHEN** a TaskCard is rendered
- **THEN** the card element has `draggable="true"` attribute

#### Scenario: Edit button emits event
- **WHEN** the user clicks the edit button on a TaskCard
- **THEN** the component emits an `edit` event

### Requirement: Test task creation form
The test suite SHALL verify that TaskForm handles task creation with client-side validation.

#### Scenario: Successful task creation
- **WHEN** the user enters "New task" in the title input and submits the form
- **THEN** the store's `addTask` method is called with "New task"

#### Scenario: Empty title rejected
- **WHEN** the user submits the form with an empty title
- **THEN** the form displays "Title cannot be empty" error and does not call the store

### Requirement: Test task edit modal
The test suite SHALL verify TaskEditModal rendering, field population, save, cancel, and validation behavior.

#### Scenario: Modal shows current task data
- **WHEN** the TaskEditModal is opened for a task with title "Process report" and status "running"
- **THEN** the title input contains "Process report" and the status select shows "running"

#### Scenario: Status selector shows all valid statuses
- **WHEN** the TaskEditModal is open
- **THEN** the status select contains seven options: New, Need Input, Scheduled, Pending, Running, Review, Completed

#### Scenario: Successful save emits event
- **WHEN** the user changes the title to "Updated report" and clicks Save
- **THEN** the component emits a `save` event with `{ title: "Updated report", status: <current> }`

#### Scenario: Save with empty title shows validation error
- **WHEN** the user clears the title field and clicks Save
- **THEN** the modal displays "Title cannot be empty" and does not emit a `save` event

#### Scenario: Cancel emits event
- **WHEN** the user clicks Cancel
- **THEN** the component emits a `cancel` event without emitting `save`

### Requirement: Test drag-and-drop interactions
The test suite SHALL verify that KanbanBoard handles drag events and triggers status updates via the store.

#### Scenario: Drop on a different column triggers update
- **WHEN** a drag event carries a task ID and a drop event fires on a column with a different status
- **THEN** the store's `updateTask` method is called with the task ID and the target column's status

#### Scenario: Drop on the same column does nothing
- **WHEN** a drag event carries a task ID and a drop event fires on the same column the task is already in
- **THEN** the store's `updateTask` method is NOT called

#### Scenario: Drag enter highlights target column
- **WHEN** a drag enters a column
- **THEN** the column receives a visual highlight class (`ring-2 ring-blue-400`)

### Requirement: Frontend test script
The frontend SHALL have a `test` script in `package.json` runnable via `npm test`. Dev dependencies (`vitest`, `@vue/test-utils`, `jsdom`) SHALL be listed in `devDependencies`.

#### Scenario: Run frontend tests
- **WHEN** a developer runs `npm install && npm test` in the frontend directory
- **THEN** all frontend tests execute and report results
