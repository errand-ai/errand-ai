## MODIFIED Requirements

### Requirement: TaskForm disables inputs during submission

When the user submits a new task (via Enter key or clicking the "Add Task" button), the TaskForm SHALL immediately disable the textarea, submit button, and voice input button. All disabled elements SHALL display a grayed-out appearance using `opacity-50` and a `cursor-not-allowed` cursor. The form SHALL remain disabled until the API call completes (success or failure), at which point all inputs SHALL be re-enabled.

#### Scenario: Inputs disabled on Enter key submission

- **WHEN** the user types a task description and presses Enter (without Shift)
- **THEN** the textarea, submit button, and voice input button are immediately disabled with reduced opacity and not-allowed cursor

#### Scenario: Inputs disabled on button click submission

- **WHEN** the user types a task description and clicks the "Add Task" button
- **THEN** the textarea, submit button, and voice input button are immediately disabled with reduced opacity and not-allowed cursor

#### Scenario: Inputs re-enabled after successful submission

- **WHEN** the task creation API call completes successfully
- **THEN** the textarea, submit button, and voice input button are re-enabled, the textarea is cleared and reset to single-line height, and normal styling is restored

#### Scenario: Inputs re-enabled after failed submission

- **WHEN** the task creation API call fails with an error
- **THEN** the textarea, submit button, and voice input button are re-enabled, the textarea text is preserved at its current height, the error message is displayed, and normal styling is restored

#### Scenario: Double submission prevented

- **WHEN** the user presses Enter twice rapidly while the first submission is still in progress
- **THEN** only one task is created because the second keypress is ignored by the disabled textarea

## ADDED Requirements

### Requirement: Auto-growing textarea for task input

The TaskForm SHALL use a `<textarea>` element instead of an `<input type="text">` for task description entry. The textarea SHALL start at a single-line height (matching the visual appearance of the previous input element) and SHALL automatically grow vertically as the user types content that exceeds the current height. The textarea SHALL NOT grow beyond a maximum height of approximately 6 lines (~144px at the current text size). When content exceeds the maximum height, the textarea SHALL become scrollable. The textarea SHALL use `resize: none` to prevent manual resizing by the user.

#### Scenario: Empty textarea matches single-line input appearance

- **WHEN** the TaskForm is rendered with an empty textarea
- **THEN** the textarea appears as a single-line input with the same height, border, padding, and placeholder text ("New task...") as the previous input element

#### Scenario: Textarea grows as content is typed

- **WHEN** the user types text that wraps to a second line
- **THEN** the textarea height increases to show both lines without scrolling

#### Scenario: Textarea grows up to maximum height

- **WHEN** the user types text that would require more than 6 lines to display
- **THEN** the textarea height stops growing at approximately 6 lines and the content becomes scrollable

#### Scenario: Textarea shrinks when content is deleted

- **WHEN** the user deletes text from a multi-line entry, reducing it to a single line
- **THEN** the textarea height shrinks back to match the content (minimum single-line height)

#### Scenario: Textarea resets after successful submission

- **WHEN** a task is successfully submitted
- **THEN** the textarea is cleared and its height resets to the initial single-line height

### Requirement: Enter to submit, Shift+Enter for newline

The TaskForm textarea SHALL submit the form when the user presses Enter without the Shift key held. Pressing Shift+Enter SHALL insert a newline character into the textarea without submitting. This behaviour SHALL match the convention used in chat applications (Slack, Discord, etc.).

#### Scenario: Enter submits the form

- **WHEN** the user presses Enter (without Shift) while the textarea has content
- **THEN** the form is submitted and the task is created

#### Scenario: Enter on empty textarea shows validation error

- **WHEN** the user presses Enter (without Shift) while the textarea is empty
- **THEN** the form shows the validation error "Task cannot be empty" and does not submit

#### Scenario: Shift+Enter inserts newline

- **WHEN** the user presses Shift+Enter while typing in the textarea
- **THEN** a newline character is inserted at the cursor position and the textarea grows if needed

#### Scenario: Enter does not insert newline

- **WHEN** the user presses Enter (without Shift) while typing in the textarea
- **THEN** no newline character is inserted into the textarea content
