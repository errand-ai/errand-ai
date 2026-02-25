## ADDED Requirements

### Requirement: TaskForm disables inputs during submission

When the user submits a new task (via Enter key or clicking the "Add Task" button), the TaskForm SHALL immediately disable the text input, submit button, and voice input button. All disabled elements SHALL display a grayed-out appearance using `opacity-50` and a `cursor-not-allowed` cursor. The form SHALL remain disabled until the API call completes (success or failure), at which point all inputs SHALL be re-enabled.

#### Scenario: Inputs disabled on Enter key submission

- **WHEN** the user types a task description and presses Enter
- **THEN** the text input, submit button, and voice input button are immediately disabled with reduced opacity and not-allowed cursor

#### Scenario: Inputs disabled on button click submission

- **WHEN** the user types a task description and clicks the "Add Task" button
- **THEN** the text input, submit button, and voice input button are immediately disabled with reduced opacity and not-allowed cursor

#### Scenario: Inputs re-enabled after successful submission

- **WHEN** the task creation API call completes successfully
- **THEN** the text input, submit button, and voice input button are re-enabled, the input is cleared, and normal styling is restored

#### Scenario: Inputs re-enabled after failed submission

- **WHEN** the task creation API call fails with an error
- **THEN** the text input, submit button, and voice input button are re-enabled, the input text is preserved, the error message is displayed, and normal styling is restored

#### Scenario: Double submission prevented

- **WHEN** the user presses Enter twice rapidly while the first submission is still in progress
- **THEN** only one task is created because the second keypress is ignored by the disabled input
