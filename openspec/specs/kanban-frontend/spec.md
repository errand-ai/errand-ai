## Requirements

### Requirement: Task cards display summary information

Each task card SHALL display the task title, any associated tags, and a truncated description preview. The description preview SHALL display the first 2 lines of the task's description text using `line-clamp-2`, styled as `text-xs text-gray-500`. If the task has no description, the preview SHALL be omitted.

Cards with `category === 'repeating'` SHALL display a repeat icon (loop/refresh SVG) alongside the repeat interval text between the title and description.

Cards SHALL display the `execute_at` value as a relative time string on all columns where the value is non-null (not only the Scheduled column).

Cards in the Running column SHALL display a pulsing activity indicator: a blue dot with `animate-ping` overlay and "Running..." text, styled as `text-xs text-blue-600`. The card SHALL also have a `border-l-2 border-blue-400` left border accent when in the running state.

Cards in the Review, Completed, or Scheduled columns SHALL display a "View Output" button (eye icon) when the task has a non-null `output` field. This button opens the `TaskOutputModal` for viewing the task's final markdown output.

Cards SHALL display a "View Logs" button (terminal/code icon) when any of the following conditions are met:
- The task is in the `running` status (live logs via WebSocket)
- The task is in `review`, `completed`, or `scheduled` status and has a non-null `runner_logs` field (static logs)

When the "View Logs" button is clicked, the `KanbanBoard` SHALL open the `TaskLogModal`. For running tasks, the modal SHALL receive the `taskId` prop (live WebSocket mode). For non-running tasks with `runner_logs`, the modal SHALL receive the `runnerLogs` prop (static rendering mode). Both modes SHALL receive the `title` prop.

#### Scenario: Task card shows description preview

- **WHEN** a task has description "Generate a weekly summary report from the analytics dashboard data and email it to the team"
- **THEN** the card shows the first 2 lines of the description as a truncated preview below the title

#### Scenario: Repeating task shows repeat indicator

- **WHEN** a task has `category === 'repeating'` and `repeat_interval === '1d'`
- **THEN** the card displays a repeat icon and "1d" text between the title and description

#### Scenario: Execute_at shown on non-scheduled columns

- **WHEN** a task in the Pending column has a non-null `execute_at` value
- **THEN** the card displays the execution time as a relative time string

#### Scenario: Running task shows pulsing indicator

- **WHEN** a task is in the Running column
- **THEN** the card displays a pulsing blue dot with "Running..." text and a left blue border accent

#### Scenario: Task card without description hides preview

- **WHEN** a task has no description (null or empty string)
- **THEN** no description preview line is shown on the card

#### Scenario: Running task shows logs button

- **WHEN** a task card is rendered in the Running column
- **THEN** the card displays a "View Logs" button (terminal/code icon)

#### Scenario: Completed task with runner_logs shows logs button

- **WHEN** a task card is rendered in the Completed column and the task has a non-null `runner_logs` field
- **THEN** the card displays a "View Logs" button (terminal/code icon)

#### Scenario: Review task with runner_logs shows logs button

- **WHEN** a task card is rendered in the Review column and the task has a non-null `runner_logs` field
- **THEN** the card displays a "View Logs" button (terminal/code icon)

#### Scenario: Completed task without runner_logs hides logs button

- **WHEN** a task card is rendered in the Completed column and the task has a null `runner_logs` field
- **THEN** the "View Logs" button is not displayed

#### Scenario: Logs button opens live modal for running task

- **WHEN** the user clicks the "View Logs" button on a running task card
- **THEN** the `TaskLogModal` opens with the task's ID (WebSocket live mode)

#### Scenario: Logs button opens static modal for completed task

- **WHEN** the user clicks the "View Logs" button on a completed task card with `runner_logs`
- **THEN** the `TaskLogModal` opens with the task's `runner_logs` string (static rendering mode)

#### Scenario: Review task card shows output button

- **WHEN** a task in the Review column has a non-null output field
- **THEN** the card displays a "View Output" button (eye icon) that opens the `TaskOutputModal`

#### Scenario: Completed task card shows output button

- **WHEN** a task in the Completed column has a non-null output field
- **THEN** the card displays a "View Output" button (eye icon) that opens the `TaskOutputModal`

#### Scenario: Task card without output hides output button

- **WHEN** a task in the Review column has a null output field
- **THEN** the card does not display the "View Output" button

#### Scenario: Both logs and output buttons visible

- **WHEN** a task in the Review column has both a non-null `output` field and a non-null `runner_logs` field
- **THEN** the card displays both the "View Logs" button (terminal/code icon) and the "View Output" button (eye icon)

Tags SHALL be displayed as small pills/badges below the title. Cards SHALL NOT display the task status text. Cards SHALL have an edit button and a delete icon. Cards SHALL have `draggable="true"` to support drag-and-drop interaction. Cards in the Scheduled column SHALL additionally display the `execute_at` value as a human-readable relative time string (e.g. "in 15 minutes", "at 5:00 PM today", "tomorrow at 9:00 AM") between the title and the tags. The relative time display on Scheduled column cards SHALL auto-refresh approximately every 30 seconds so the countdown stays accurate without requiring a page reload.

The delete icon on task cards SHALL NOT be displayed when the user has the `viewer` role (checked via `isViewer` from the auth store). The delete icon SHALL also NOT be displayed on task cards in the Running column, regardless of the user's role.

#### Scenario: Delete icon shows styled confirmation modal

- **WHEN** the user clicks the delete icon on a task card
- **THEN** a Tailwind-styled delete confirmation modal appears asking "Delete this task?" with the task title, a red "Delete" button, and a "Cancel" button

#### Scenario: Viewer cannot see delete button

- **WHEN** a viewer user views a task card in any column
- **THEN** the delete icon is not rendered on the card

#### Scenario: No delete button on running tasks

- **WHEN** any user views a task card in the Running column
- **THEN** the delete icon is not rendered on the card
