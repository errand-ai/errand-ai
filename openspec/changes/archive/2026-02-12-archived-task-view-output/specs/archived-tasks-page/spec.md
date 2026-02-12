## MODIFIED Requirements

### Requirement: Archived Tasks page layout

The Archived Tasks page SHALL display a heading "Archived Tasks" and a table with columns: Title, Status, Tags, Date, and Actions. The page SHALL follow the same visual styling as the rest of the application (Tailwind CSS). The list SHALL be scrollable if there are many entries. The Actions column SHALL contain a "View Output" button for tasks that have non-null, non-empty output.

#### Scenario: Page renders with heading
- **WHEN** the user navigates to `/archived`
- **THEN** the page displays the heading "Archived Tasks"

#### Scenario: Tasks displayed in table format
- **WHEN** archived tasks exist
- **THEN** each task is displayed in a row with its title, status badge, tag pills, formatted date, and an actions cell

#### Scenario: View Output button shown for tasks with output
- **WHEN** an archived task has a non-null, non-empty `output` field
- **THEN** the Actions cell for that row SHALL display a "View Output" button

#### Scenario: View Output button hidden for tasks without output
- **WHEN** an archived task has a null or empty `output` field
- **THEN** the Actions cell for that row SHALL be empty (no button)

### Requirement: Archived Tasks page view output action

Clicking the "View Output" button on an archived task row SHALL open the `TaskOutputModal` with the task's title and output. Clicking the button SHALL NOT trigger the row-click handler that opens the edit modal.

#### Scenario: Click View Output opens output modal
- **WHEN** the user clicks the "View Output" button on an archived task row
- **THEN** the `TaskOutputModal` opens showing the task title and output in a monospace pre block

#### Scenario: Click View Output does not open edit modal
- **WHEN** the user clicks the "View Output" button on an archived task row
- **THEN** the `TaskEditModal` does NOT open

#### Scenario: Close output modal
- **WHEN** the `TaskOutputModal` is open and the user closes it (Close button, Escape, or backdrop click)
- **THEN** the modal closes and the archived tasks table is visible
