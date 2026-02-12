## MODIFIED Requirements

### Requirement: Task cards display summary information

_(Append to existing requirement — role-based and status-based delete button visibility)_

The delete icon on task cards SHALL NOT be displayed when the user has the `viewer` role (checked via `isViewer` from the auth store). The delete icon SHALL also NOT be displayed on task cards in the Running column, regardless of the user's role.

#### Scenario: Viewer cannot see delete button
- **WHEN** a viewer user views a task card in any column
- **THEN** the delete icon is not rendered on the card

#### Scenario: Editor sees delete button on non-running task
- **WHEN** an editor views a task card in the New column
- **THEN** the delete icon is visible on the card

#### Scenario: No delete button on running tasks
- **WHEN** any user views a task card in the Running column
- **THEN** the delete icon is not rendered on the card

#### Scenario: Delete button visible on completed task for editor
- **WHEN** an editor views a task card in the Completed column
- **THEN** the delete icon is visible on the card

### Requirement: Task creation hidden for viewer

The task creation form (input field and "Add Task" button) SHALL NOT be displayed when the user has the `viewer` role. Only users with the `editor` or `admin` role SHALL see the task creation form.

#### Scenario: Viewer cannot see create form
- **WHEN** a viewer user views the kanban board
- **THEN** the task creation form is not rendered

#### Scenario: Editor sees create form
- **WHEN** an editor user views the kanban board
- **THEN** the task creation form is displayed as normal

#### Scenario: Admin sees create form
- **WHEN** an admin user views the kanban board
- **THEN** the task creation form is displayed as normal
