## Requirements

### Requirement: Task cards display summary information
Each task card SHALL display the task title, any associated tags, and a truncated description preview. The description preview SHALL display the first 2 lines of the task's description text using `line-clamp-2`, styled as `text-xs text-gray-500`. If the task has no description, the preview SHALL be omitted.

Cards with `category === 'repeating'` SHALL display a repeat icon (loop/refresh SVG) alongside the repeat interval text between the title and description.

Cards SHALL display the `execute_at` value as a relative time string on all columns where the value is non-null (not only the Scheduled column).

Cards in the Running column SHALL display a pulsing activity indicator: a blue dot with `animate-ping` overlay and "Running..." text, styled as `text-xs text-blue-600`. The card SHALL also have a `border-l-2 border-blue-400` left border accent when in the running state.

Cards in the Review, Completed, or Scheduled columns SHALL display a "View Output" button (eye icon) when the task has a non-null `output` field.

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

Tags SHALL be displayed as small pills/badges below the title. Cards SHALL NOT display the task status text. Cards SHALL have an edit button and a delete icon. Cards SHALL have `draggable="true"` to support drag-and-drop interaction. Cards in the Scheduled column SHALL additionally display the `execute_at` value as a human-readable relative time string (e.g. "in 15 minutes", "at 5:00 PM today", "tomorrow at 9:00 AM") between the title and the tags. The relative time display on Scheduled column cards SHALL auto-refresh approximately every 30 seconds so the countdown stays accurate without requiring a page reload.

Cards in the Review, Completed, or Scheduled columns SHALL display a "View Output" button (eye icon) when the task has a non-null `output` field. Clicking this button SHALL open the task output viewer popup. For Scheduled column cards (failed retries), the button SHALL also be shown when `output` contains error information.

#### Scenario: Task card with title and tags
- **WHEN** a task exists with title "Fix auth bug" and tags "urgent" and "bug"
- **THEN** the card shows the title, two tag pills labeled "urgent" and "bug", an edit button, and a delete icon

#### Scenario: Task card with no tags
- **WHEN** a task exists with title "Process report" and no tags
- **THEN** the card shows only the title, edit button, and delete icon, with no tag pills

#### Scenario: Scheduled task card shows execute_at
- **WHEN** a task in the Scheduled column has execute_at set to a future time
- **THEN** the card displays the execution time as a relative time string between the title and tags

#### Scenario: Scheduled task card with null execute_at
- **WHEN** a task in the Scheduled column has execute_at set to null
- **THEN** the card does not display any execution time

#### Scenario: Non-scheduled task card hides execute_at
- **WHEN** a task in the Pending or Running column has an execute_at value
- **THEN** the card does not display the execution time

#### Scenario: Scheduled card countdown refreshes automatically
- **WHEN** a task in the Scheduled column displays "in 5m" and 30 seconds elapse
- **THEN** the displayed relative time updates to reflect the current remaining time without user interaction

#### Scenario: Countdown timer only active for scheduled cards
- **WHEN** a task card is displayed in a non-scheduled column (e.g. Pending, Running)
- **THEN** no periodic refresh timer is active for that card

#### Scenario: Review task card shows output button
- **WHEN** a task in the Review column has a non-null output field
- **THEN** the card displays a "View Output" button (eye icon) that opens the output viewer popup

#### Scenario: Completed task card shows output button
- **WHEN** a task in the Completed column has a non-null output field
- **THEN** the card displays a "View Output" button (eye icon) that opens the output viewer popup

#### Scenario: Scheduled retry task card shows output button
- **WHEN** a task in the Scheduled column has a non-null output field (from a failed execution)
- **THEN** the card displays a "View Output" button (eye icon) that opens the output viewer popup

#### Scenario: Task card without output hides button
- **WHEN** a task in the Review column has a null output field
- **THEN** the card does not display the "View Output" button

#### Scenario: Delete icon shows styled confirmation modal
- **WHEN** the user clicks the delete icon on a task card
- **THEN** a Tailwind-styled delete confirmation modal appears asking "Delete this task?" with the task title, a red "Delete" button, and a "Cancel" button

#### Scenario: Confirm delete removes task
- **WHEN** the user confirms the deletion in the styled modal
- **THEN** the frontend sends `DELETE /api/tasks/{id}` and removes the task card from the board

#### Scenario: Cancel delete keeps task
- **WHEN** the user cancels the deletion in the styled modal
- **THEN** no API call is made and the task card remains on the board

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

### Requirement: Kanban column layout
Each Kanban column SHALL have a minimum width of `min-w-[240px]` and use `flex-1` to fill available space. Column headers SHALL display the column label and a task count in a pill badge (`rounded-full bg-white/70 px-1.5 text-xs font-medium`).

#### Scenario: Column count displayed as pill badge
- **WHEN** the Review column contains 3 tasks
- **THEN** the column header shows "REVIEW" followed by a pill badge containing "3"

#### Scenario: Column minimum width
- **WHEN** the browser viewport is narrower than the total of all columns
- **THEN** each column maintains at least 240px width and the board scrolls horizontally

### Requirement: Kanban empty state
When the board has zero tasks across all columns, the board area SHALL display a centered empty state with an icon, "No tasks yet" heading, and "Create your first task using the form above" guidance text. Individual empty columns SHALL NOT display "No tasks" text — an empty column is self-evident.

#### Scenario: Board-level empty state
- **WHEN** all columns have zero tasks
- **THEN** the board displays a centered empty state icon with guidance text instead of the column layout

#### Scenario: Individual empty column
- **WHEN** the New column has zero tasks but other columns have tasks
- **THEN** the New column shows no placeholder text

### Requirement: Kanban skeleton loading state
While tasks are loading, the board SHALL display skeleton placeholders that match the column layout: 6 gray rounded column shapes with `animate-pulse`, each containing 2-3 skeleton card shapes. The "Loading tasks..." text SHALL be replaced by these skeleton placeholders.

#### Scenario: Skeleton shown during initial load
- **WHEN** the Kanban board is fetching tasks for the first time
- **THEN** the board displays 6 skeleton columns with pulsing card placeholders instead of "Loading tasks..." text

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

The task creation form SHALL display a microphone icon button between the text input and the "Add Task" button, but only when voice input is available (browser supports `MediaRecorder` AND `GET /api/transcribe/status` returns `{"enabled": true}`). The form layout SHALL accommodate the microphone button without breaking the existing responsive design. When voice input is not available, the form SHALL render unchanged (text input + "Add Task" button only).

#### Scenario: Form with microphone button (transcription enabled)
- **WHEN** the kanban board loads, the browser supports MediaRecorder, and transcription is enabled
- **THEN** the task creation form displays: text input, microphone button, "Add Task" button

#### Scenario: Form without microphone button (transcription disabled)
- **WHEN** the kanban board loads and transcription is not enabled (no model selected by admin)
- **THEN** the task creation form displays only: text input, "Add Task" button (unchanged)

#### Scenario: Form without microphone button (browser unsupported)
- **WHEN** the kanban board loads in a browser not supporting MediaRecorder
- **THEN** the task creation form displays only: text input, "Add Task" button (unchanged)

#### Scenario: Voice input populates text field
- **WHEN** the user records audio and transcription succeeds
- **THEN** the transcript text appears in the text input field, ready for the user to review and submit with "Add Task"
